"""
RESQ - Audit trail.

OWNER: Partner D (System Core).

Section 9 of the brief: a reviewer must be able to see WHY the system did what
it did, without reading code. Every decision and every world change lands here.
Later this table is written straight to the database and rendered as the audit
screen in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DecisionRecord:
    """One line in the "why did it do that" log."""

    sim_time: float
    component: str                 # "PRIORITIZER" | "DISPATCHER" | "ROUTER" | "ENGINE"
    action: str                    # short verb, e.g. "SELECT_UNIT", "REROUTE"
    incident_id: Optional[str] = None
    unit_id: Optional[str] = None
    chosen: Optional[str] = None   # what was picked, if anything
    rationale: str = ""            # the human sentence
    error: str = "NONE"
    considered: List[Dict[str, Any]] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_line(self) -> str:
        """One-line rendering used by the console runner."""
        stamp = f"[{self.sim_time:8.0f}s]"
        who = f"{self.component:<11}"
        target = self.incident_id or self.unit_id or "-"
        tail = self.rationale or self.error
        return f"{stamp} {who} {self.action:<18} {target:<8} {tail}"


class AuditLog:
    """In-memory decision log. Partner D swaps the backing store for the
    database in the persistence increment; the interface stays identical."""

    def __init__(self, echo: bool = False) -> None:
        self._records: List[DecisionRecord] = []
        self.echo = echo  # print as we go, useful while developing

    def log(self, record: DecisionRecord) -> DecisionRecord:
        self._records.append(record)
        if self.echo:
            print(record.as_line())
        return record

    def all(self) -> List[DecisionRecord]:
        return list(self._records)

    def for_incident(self, incident_id: str) -> List[DecisionRecord]:
        """The full decision chain for one call - this is the audit screen."""
        return [r for r in self._records if r.incident_id == incident_id]

    def count(self) -> int:
        return len(self._records)
