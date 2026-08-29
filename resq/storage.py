"""
RESQ - Persistence.

OWNER: Partner D (System Core).

SQLite through the standard library. No ORM, no third-party driver, nothing to
install - a teammate clones the repo and it works.

WHY THIS SHAPE:

The engine must not know that a database exists. It is handed an object with a
few named methods and calls them; if it is handed nothing, it behaves exactly as
it did before. That is why every method here is safe to call in any order and
why none of them raise on ordinary conditions. Swapping SQLite for anything else
later means writing one new class with the same eight methods.

WHAT IS STORED:

  runs          one row per simulation run - which scenario, which components,
                when it started and finished, and the headline results
  incidents     the latest known state of every incident in that run
  units         the latest known state of every response unit in that run
  decisions     every line of the audit log, in order - the full "why"
  world_events  every failure the operator injected, in order

Incidents and units are upserted, so those two tables answer "how did the run
end". The decisions table is append-only, so it answers "how did it get there".
That split is deliberate: the decision chain is the thing the audit screen reads
and the thing the rubric asks for, so it is the thing we never overwrite.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Bumped whenever the schema changes shape. Stored on every run so an old
# database can be recognised rather than silently misread.
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_version  INTEGER NOT NULL,
    scenario        TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,   -- real wall-clock, ISO 8601
    finished_at     TEXT,               -- NULL while the run is in progress
    prioritizer     TEXT,               -- which A implementation was wired in
    dispatcher      TEXT,               -- which B
    router          TEXT,               -- which C
    tick_seconds    REAL,
    sim_seconds     REAL,               -- simulated time reached
    ticks           INTEGER,
    resolved        INTEGER,
    failed          INTEGER,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS incidents (
    run_id               INTEGER NOT NULL,
    incident_id          TEXT    NOT NULL,
    node_id              TEXT,
    incident_type        TEXT,
    required_unit        TEXT,
    reported_at          REAL,
    victims              INTEGER,
    requires_transport   INTEGER,
    severity_score       REAL,
    priority_rank        INTEGER,
    severity_rationale   TEXT,
    status               TEXT,
    assigned_unit_id     TEXT,
    assigned_at          REAL,
    arrived_at           REAL,
    resolved_at          REAL,
    destination_hospital TEXT,
    failure_reason       TEXT,
    response_seconds     REAL,
    PRIMARY KEY (run_id, incident_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS units (
    run_id               INTEGER NOT NULL,
    unit_id              TEXT    NOT NULL,
    unit_type            TEXT,
    home_station         TEXT,
    current_node         TEXT,
    status               TEXT,
    assigned_incident_id TEXT,
    total_busy_seconds   REAL,
    sim_time             REAL,
    PRIMARY KEY (run_id, unit_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    sim_time    REAL    NOT NULL,
    component   TEXT    NOT NULL,   -- PRIORITIZER | DISPATCHER | ROUTER | ENGINE
    action      TEXT    NOT NULL,
    incident_id TEXT,
    unit_id     TEXT,
    chosen      TEXT,
    rationale   TEXT,
    error       TEXT,
    considered  TEXT,               -- JSON list of rejected options
    extra       TEXT,               -- JSON blob of anything else
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS world_events (
    event_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL,
    sim_time  REAL    NOT NULL,
    kind      TEXT    NOT NULL,     -- ROAD_CLOSED | TRAFFIC | HOSPITAL_FULL | ...
    detail    TEXT,                 -- JSON
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

-- The audit screen always asks "everything about this one incident", so that
-- lookup gets an index. Without it the query is a full scan of the run.
CREATE INDEX IF NOT EXISTS idx_decisions_incident
    ON decisions (run_id, incident_id, decision_id);
CREATE INDEX IF NOT EXISTS idx_events_run
    ON world_events (run_id, event_id);
"""


def _enum_value(value: Any) -> Any:
    """Store the string behind an enum, not its repr. Leaves plain values alone."""
    return getattr(value, "value", value)


def _json(value: Any) -> str:
    """Serialise loosely - persistence must never crash a running simulation."""
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


class Repository:
    """
    The narrow persistence API the engine is allowed to see.

    Typical life cycle:

        repo = Repository("resq.db")
        repo.start_run("disruption", prioritizer="FIFO", ...)
        ...                                  # engine calls save_* as it runs
        repo.finish_run(sim_seconds=..., ticks=...)
        repo.close()

    Every save_* method is a no-op when no run is open, so wiring the repository
    in half-way through a session cannot corrupt anything.
    """

    def __init__(self, path: str = "resq.db") -> None:
        self.path = path
        # check_same_thread=False so the Tk operator UI can drive the engine
        # from its own callback thread without a second connection.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self.run_id: Optional[int] = None

    # ------------------------------------------------------------------
    # RUN LIFECYCLE
    # ------------------------------------------------------------------

    def start_run(
        self,
        scenario: str,
        prioritizer: str = "",
        dispatcher: str = "",
        router: str = "",
        tick_seconds: float = 30.0,
        notes: str = "",
    ) -> int:
        """Open a new run and return its id. Everything saved afterwards
        belongs to it until finish_run is called."""
        cur = self._conn.execute(
            "INSERT INTO runs (schema_version, scenario, started_at, prioritizer,"
            " dispatcher, router, tick_seconds, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (SCHEMA_VERSION, scenario,
             datetime.now(timezone.utc).isoformat(timespec="seconds"),
             prioritizer, dispatcher, router, tick_seconds, notes),
        )
        self._conn.commit()
        self.run_id = int(cur.lastrowid)
        return self.run_id

    def finish_run(
        self,
        sim_seconds: float = 0.0,
        ticks: int = 0,
        resolved: int = 0,
        failed: int = 0,
    ) -> None:
        """Stamp the run as complete. Safe to call twice."""
        if self.run_id is None:
            return
        self._conn.execute(
            "UPDATE runs SET finished_at = ?, sim_seconds = ?, ticks = ?,"
            " resolved = ?, failed = ? WHERE run_id = ?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             sim_seconds, ticks, resolved, failed, self.run_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # WRITES  (called by the engine, which knows none of the SQL below)
    # ------------------------------------------------------------------

    def save_incident(self, incident, sim_time: float = 0.0) -> None:
        """Upsert one incident's current state."""
        if self.run_id is None:
            return
        self._conn.execute(
            "INSERT INTO incidents (run_id, incident_id, node_id, incident_type,"
            " required_unit, reported_at, victims, requires_transport,"
            " severity_score, priority_rank, severity_rationale, status,"
            " assigned_unit_id, assigned_at, arrived_at, resolved_at,"
            " destination_hospital, failure_reason, response_seconds)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(run_id, incident_id) DO UPDATE SET"
            "   status = excluded.status,"
            "   severity_score = excluded.severity_score,"
            "   priority_rank = excluded.priority_rank,"
            "   severity_rationale = excluded.severity_rationale,"
            "   assigned_unit_id = excluded.assigned_unit_id,"
            "   assigned_at = excluded.assigned_at,"
            "   arrived_at = excluded.arrived_at,"
            "   resolved_at = excluded.resolved_at,"
            "   destination_hospital = excluded.destination_hospital,"
            "   failure_reason = excluded.failure_reason,"
            "   response_seconds = excluded.response_seconds",
            (
                self.run_id,
                incident.incident_id,
                incident.node_id,
                _enum_value(incident.incident_type),
                _enum_value(incident.required_unit),
                incident.reported_at,
                incident.victims,
                int(bool(incident.requires_transport)),
                incident.severity_score,
                incident.priority_rank,
                incident.severity_rationale,
                _enum_value(incident.status),
                incident.assigned_unit_id,
                incident.assigned_at,
                incident.arrived_at,
                incident.resolved_at,
                incident.destination_hospital,
                incident.failure_reason,
                incident.response_seconds,
            ),
        )

    def save_unit_state(self, unit, sim_time: float = 0.0) -> None:
        """Upsert one unit's current state."""
        if self.run_id is None:
            return
        self._conn.execute(
            "INSERT INTO units (run_id, unit_id, unit_type, home_station,"
            " current_node, status, assigned_incident_id, total_busy_seconds,"
            " sim_time) VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(run_id, unit_id) DO UPDATE SET"
            "   current_node = excluded.current_node,"
            "   status = excluded.status,"
            "   assigned_incident_id = excluded.assigned_incident_id,"
            "   total_busy_seconds = excluded.total_busy_seconds,"
            "   sim_time = excluded.sim_time",
            (
                self.run_id,
                unit.unit_id,
                _enum_value(unit.unit_type),
                unit.home_station,
                unit.current_node,
                _enum_value(unit.status),
                unit.assigned_incident_id,
                unit.total_busy_seconds,
                sim_time,
            ),
        )

    def save_decision(self, record) -> None:
        """Append one audit record. This table is never overwritten."""
        if self.run_id is None:
            return
        self._conn.execute(
            "INSERT INTO decisions (run_id, sim_time, component, action,"
            " incident_id, unit_id, chosen, rationale, error, considered, extra)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.run_id,
                record.sim_time,
                record.component,
                record.action,
                record.incident_id,
                record.unit_id,
                record.chosen,
                record.rationale,
                record.error,
                _json(record.considered),
                _json(record.extra),
            ),
        )

    def save_world_event(self, sim_time: float, kind: str,
                         detail: Optional[Dict[str, Any]] = None) -> None:
        """Append one operator-injected failure."""
        if self.run_id is None:
            return
        self._conn.execute(
            "INSERT INTO world_events (run_id, sim_time, kind, detail)"
            " VALUES (?,?,?,?)",
            (self.run_id, sim_time, kind, _json(detail or {})),
        )

    def commit(self) -> None:
        """Flush pending writes. The engine calls this once per tick so a run
        that is killed mid-simulation still leaves everything up to that tick."""
        self._conn.commit()

    # ------------------------------------------------------------------
    # READS  (used by --runs, the audit screen, and the tests)
    # ------------------------------------------------------------------

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY run_id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def load_run(self, run_id: int) -> Dict[str, Any]:
        """Everything about one run: the header, its incidents and its units."""
        run = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run is None:
            return {}
        incidents = self._conn.execute(
            "SELECT * FROM incidents WHERE run_id = ? ORDER BY reported_at,"
            " incident_id", (run_id,)
        ).fetchall()
        units = self._conn.execute(
            "SELECT * FROM units WHERE run_id = ? ORDER BY unit_id", (run_id,)
        ).fetchall()
        events = self._conn.execute(
            "SELECT * FROM world_events WHERE run_id = ? ORDER BY event_id",
            (run_id,)
        ).fetchall()
        return {
            "run": dict(run),
            "incidents": [dict(r) for r in incidents],
            "units": [dict(r) for r in units],
            "events": [dict(r) for r in events],
        }

    def decisions_for_incident(self, run_id: int,
                               incident_id: str) -> List[Dict[str, Any]]:
        """
        The full decision chain for one call, oldest first.

        This is the acceptance test for the whole persistence increment: run a
        scenario, exit the process, start again, and this still answers "why did
        it send that unit".
        """
        rows = self._conn.execute(
            "SELECT * FROM decisions WHERE run_id = ? AND incident_id = ?"
            " ORDER BY decision_id", (run_id, incident_id)
        ).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["considered"] = json.loads(record["considered"] or "[]")
            record["extra"] = json.loads(record["extra"] or "{}")
            out.append(record)
        return out

    def decisions_for_run(self, run_id: int) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM decisions WHERE run_id = ? ORDER BY decision_id",
            (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    # Allow `with Repository(...) as repo:` in tests and short scripts.
    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
