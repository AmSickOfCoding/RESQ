"""
RESQ - Persistence tests.

OWNER: Partner D (System Core).

Run with:  python -m pytest tests -q      (or python tests/test_persistence.py)

The acceptance criterion for the whole persistence increment is one sentence:
run a scenario, exit the process, start again, and the full decision chain for a
given incident is still readable. test_decision_chain_survives_a_real_restart
does exactly that, in a genuinely separate interpreter, so nothing can be
passing because an object happened to still be in memory.
"""

from __future__ import annotations

import os
import subprocess
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resq.audit import AuditLog
from resq.engine import Engine, EngineConfig
from resq.models import IncidentStatus
from resq.scenarios import ALL_SCENARIOS
from resq.storage import Repository
from resq.stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_scenario(key, repository=None, max_ticks=2000):
    """Drive one scenario to completion, exactly the way main.py does."""
    scenario = ALL_SCENARIOS[key]()
    engine = Engine(
        world=scenario.world,
        prioritizer=FifoPrioritizer(),
        dispatcher=FirstFreeDispatcher(),
        router=BfsRouter(),
        config=EngineConfig(tick_seconds=30.0),
        audit=AuditLog(echo=False),
        repository=repository,
    )
    for incident in scenario.incidents:
        engine.schedule_incident(incident)

    events = sorted(scenario.events, key=lambda e: e[0])
    while not engine._is_finished() and engine.tick_count < max_ticks:
        while events and events[0][0] <= engine.now:
            events.pop(0)[1](engine)
        engine.tick()
    return engine


def temp_db():
    handle, path = tempfile.mkstemp(suffix=".db", prefix="resq_test_")
    os.close(handle)
    os.remove(path)  # we want the filename, not the empty file
    return path


# ---------------------------------------------------------------------------
# THE ACCEPTANCE TEST
# ---------------------------------------------------------------------------


def test_decision_chain_survives_a_real_restart():
    """
    Write a run in one process, read it back in another.

    The child process is a fresh interpreter with its own memory, so if this
    passes, the data genuinely came off the disk.
    """
    path = temp_db()
    try:
        # --- process 1: run and save --------------------------------------
        writer = (
            "import sys; sys.path.insert(0, %r)\n"
            "sys.path.insert(0, %r)\n"
            "from tests.test_persistence import run_scenario\n"
            "from resq.storage import Repository\n"
            "repo = Repository(%r)\n"
            "run_id = repo.start_run('disruption', prioritizer='FIFO',\n"
            "                        dispatcher='FirstFree', router='BFS')\n"
            "engine = run_scenario('disruption', repository=repo)\n"
            "repo.finish_run(sim_seconds=engine.now, ticks=engine.tick_count)\n"
            "repo.close()\n"
            "print(run_id)\n"
        ) % (REPO_ROOT, REPO_ROOT, path)

        result = subprocess.run([sys.executable, "-c", writer],
                                capture_output=True, text=True, cwd=REPO_ROOT)
        assert result.returncode == 0, f"writer process failed:\n{result.stderr}"
        run_id = int(result.stdout.strip().splitlines()[-1])

        # --- process 2 (this one): reopen and read ------------------------
        repo = Repository(path)
        runs = repo.list_runs()
        assert runs, "no runs found after restart"
        assert runs[0]["run_id"] == run_id
        assert runs[0]["scenario"] == "disruption"
        assert runs[0]["finished_at"] is not None, "run was never closed"

        loaded = repo.load_run(run_id)
        assert loaded["incidents"], "no incidents persisted"

        # every incident must have reached a terminal state and been stored
        terminal = {IncidentStatus.RESOLVED.value, IncidentStatus.FAILED.value}
        for row in loaded["incidents"]:
            assert row["status"] in terminal, \
                f"{row['incident_id']} stored mid-flight as {row['status']}"

        # the headline requirement: one incident's full chain, off the disk
        first = loaded["incidents"][0]["incident_id"]
        chain = repo.decisions_for_incident(run_id, first)
        assert len(chain) >= 3, f"chain for {first} is only {len(chain)} records"

        actions = [r["action"] for r in chain]
        assert "INCIDENT_REPORTED" in actions
        assert any(a in ("RESOLVED", "FAILED") for a in actions), \
            f"chain never reaches a terminal action: {actions}"

        # and it must still explain itself, not just list events
        assert any(r["rationale"] for r in chain), \
            "no rationale survived the round trip"
        repo.close()
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# SUPPORTING TESTS
# ---------------------------------------------------------------------------


def test_all_five_tables_are_populated():
    """runs, incidents, units, decisions and world_events must all get rows.
    The disruption scenario injects failures, so world_events is non-empty."""
    path = temp_db()
    try:
        repo = Repository(path)
        run_id = repo.start_run("disruption")
        engine = run_scenario("disruption", repository=repo)
        repo.finish_run(sim_seconds=engine.now, ticks=engine.tick_count)
        repo.close()

        conn = sqlite3.connect(path)
        for table in ("runs", "incidents", "units", "decisions", "world_events"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count > 0, f"{table} is empty"
        conn.close()
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_saved_decisions_match_the_in_memory_audit_log():
    """Persistence must record the audit log faithfully - same count, same
    order. If these ever diverge, the audit screen is lying."""
    path = temp_db()
    try:
        repo = Repository(path)
        run_id = repo.start_run("normal")
        engine = run_scenario("normal", repository=repo)
        repo.finish_run()

        stored = repo.decisions_for_run(run_id)
        live = engine.audit.all()
        assert len(stored) == len(live), \
            f"{len(stored)} rows stored vs {len(live)} logged"
        for row, record in zip(stored, live):
            assert row["action"] == record.action
            assert row["component"] == record.component
            assert row["rationale"] == record.rationale
        repo.close()
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_rejected_alternatives_survive_the_round_trip():
    """The `considered` list is where the decision-quality marks live, so it
    has to come back as structured data, not as a flattened string."""
    path = temp_db()
    try:
        repo = Repository(path)
        run_id = repo.start_run("rush")
        run_scenario("rush", repository=repo)
        repo.finish_run()

        with_alternatives = [
            row for row in repo.decisions_for_run(run_id)
            if row["considered"] not in ("[]", None, "")
        ]
        assert with_alternatives, "nothing recorded any rejected alternative"

        sample = repo.decisions_for_incident(
            run_id, with_alternatives[0]["incident_id"]
        )
        parsed = [r for r in sample if r["considered"]]
        assert parsed, "considered list did not survive as structured data"
        assert isinstance(parsed[0]["considered"], list)
        repo.close()
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_engine_without_a_repository_is_unchanged():
    """
    The safety net for the original seven tests: persistence must be invisible
    when it is switched off. Same scenario, with and without a repository, must
    produce an identical audit log.
    """
    path = temp_db()
    try:
        plain = run_scenario("disruption")

        repo = Repository(path)
        repo.start_run("disruption")
        saved = run_scenario("disruption", repository=repo)
        repo.finish_run()
        repo.close()

        assert plain.tick_count == saved.tick_count
        assert plain.now == saved.now
        assert plain.audit.count() == saved.audit.count()
        for a, b in zip(plain.audit.all(), saved.audit.all()):
            assert (a.sim_time, a.action, a.chosen, a.rationale) == \
                   (b.sim_time, b.action, b.chosen, b.rationale)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_two_runs_in_one_database_stay_separate():
    """The demo will run several scenarios into the same file. Their decision
    chains must not bleed into each other."""
    path = temp_db()
    try:
        repo = Repository(path)

        first = repo.start_run("normal")
        run_scenario("normal", repository=repo)
        repo.finish_run()

        second = repo.start_run("rush")
        run_scenario("rush", repository=repo)
        repo.finish_run()

        assert first != second
        assert len(repo.list_runs()) == 2

        first_rows = repo.decisions_for_run(first)
        second_rows = repo.decisions_for_run(second)
        assert first_rows and second_rows
        assert all(r["run_id"] == first for r in first_rows)
        assert all(r["run_id"] == second for r in second_rows)

        assert repo.load_run(first)["run"]["scenario"] == "normal"
        assert repo.load_run(second)["run"]["scenario"] == "rush"
        repo.close()
    finally:
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
                passed += 1
            except AssertionError as exc:
                print(f"FAIL  {name}: {exc}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
