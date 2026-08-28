"""
RESQ - Integration test for Partner A's severity scoring.

OWNER: Partner D (System Core).

The rule from CLAUDE.md section 6.6: every teammate merge adds at least one
integration test, and their real implementation must satisfy the same tests the
stub does. So this file checks two things:

  1. the adapter genuinely calls Huthaifa's module and produces ordering that
     reacts to severity, victims and waiting time
  2. the full pipeline still behaves - swapping the stub for the real scorer
     must not break resolution, the audit trail, or determinism
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resq.adapters.partner_a import (
    SeverityPrioritizer,
    to_scoring_input,
    triage_level,
)
from resq.audit import AuditLog
from resq.engine import Engine, EngineConfig
from resq.models import Incident, IncidentStatus, IncidentType, UnitType
from resq.scenarios import ALL_SCENARIOS, collect_metrics
from resq.stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher
from resq.world import build_sample_city


def make_engine(prioritizer=None, world=None):
    return Engine(
        world=world or build_sample_city(),
        prioritizer=prioritizer or SeverityPrioritizer(),
        dispatcher=FirstFreeDispatcher(),
        router=BfsRouter(),
        config=EngineConfig(tick_seconds=30.0),
        audit=AuditLog(echo=False),
    )


def incident(iid, itype, victims=1, at=0.0, unit=UnitType.AMBULANCE):
    return Incident(incident_id=iid, node_id="N05", incident_type=itype,
                    reported_at=at, required_unit=unit, victims=victims)


# ---------------------------------------------------------------------------
# THE TRANSLATION ITSELF
# ---------------------------------------------------------------------------


def test_seconds_are_converted_to_the_minutes_his_module_expects():
    """Agenda item 2. The engine holds seconds; his module documents minutes.
    If this conversion is ever dropped, every call looks maximally urgent."""
    call = incident("X1", IncidentType.MEDICAL, at=0.0)
    payload = to_scoring_input(call, now=600.0)   # 600 simulated seconds
    assert payload["waiting_time"] == 10.0, "600s should arrive as 10 minutes"


def test_payload_has_exactly_the_keys_his_validator_requires():
    from severity_scoring.validation import REQUIRED_FIELDS, validate_incident

    payload = to_scoring_input(incident("X2", IncidentType.FIRE), now=0.0)
    assert REQUIRED_FIELDS <= payload.keys()
    assert validate_incident(payload) is True


def test_triage_level_escalates_with_victims():
    """Stand-in for the reported-severity field our contract is missing."""
    assert triage_level(incident("A", IncidentType.MEDICAL, victims=1)) == "Medium"
    assert triage_level(incident("B", IncidentType.MEDICAL, victims=3)) == "High"
    assert triage_level(incident("C", IncidentType.MEDICAL, victims=5)) == "Critical"
    assert triage_level(incident("D", IncidentType.HAZMAT, victims=1)) == "Critical"


# ---------------------------------------------------------------------------
# THE SCORING BEHAVIOUR
# ---------------------------------------------------------------------------


def test_more_victims_outrank_fewer_of_the_same_type():
    ordered = SeverityPrioritizer().prioritize(
        [incident("SMALL", IncidentType.MEDICAL, victims=1),
         incident("BIG", IncidentType.MEDICAL, victims=6)],
        build_sample_city(), now=0.0,
    )
    assert ordered[0].incident_id == "BIG"
    assert ordered[0].priority_rank == 1
    assert ordered[1].priority_rank == 2


def test_waiting_eventually_lifts_an_older_lower_severity_call():
    """Starvation check. A quiet call that has waited must be able to overtake
    a fresh one of the same kind, or the queue never drains fairly."""
    old = incident("OLD", IncidentType.MEDICAL, victims=1, at=0.0)
    fresh = incident("FRESH", IncidentType.MEDICAL, victims=1, at=900.0)

    at_once = SeverityPrioritizer().prioritize([old, fresh], build_sample_city(), 900.0)
    assert at_once[0].incident_id == "OLD", \
        "the older call should score higher once it has waited"


def test_every_incident_gets_a_readable_rationale():
    """Section 9 - a reviewer must see why, without reading code."""
    scenario = ALL_SCENARIOS["rush"]()
    ordered = SeverityPrioritizer().prioritize(
        list(scenario.incidents), scenario.world, now=600.0)

    for call in ordered:
        assert call.severity_rationale, f"{call.incident_id} has no rationale"
        assert "/100" in call.severity_rationale
        assert "Weights" in call.severity_rationale, \
            "rationale should show what each factor contributed"


def test_a_rejected_input_scores_zero_instead_of_raising():
    """
    His validator raises; our design rules forbid exceptions for expected
    conditions. A negative victim count is nonsense his module will refuse,
    and the run must survive it with an explanation.
    """
    broken = incident("BROKEN", IncidentType.MEDICAL, victims=-4)
    ordered = SeverityPrioritizer().prioritize([broken], build_sample_city(), 0.0)

    assert ordered[0].severity_score == 0.0
    assert "rejected the input" in ordered[0].severity_rationale


# ---------------------------------------------------------------------------
# THE PIPELINE STILL WORKS
# ---------------------------------------------------------------------------


def test_real_scorer_resolves_a_scenario_end_to_end():
    scenario = ALL_SCENARIOS["rush"]()
    engine = make_engine(world=scenario.world)
    for call in scenario.incidents:
        engine.schedule_incident(call)
    engine.run()

    metrics = collect_metrics(engine, scenario.name)
    assert metrics.total_incidents == len(scenario.incidents)
    assert metrics.resolved + metrics.failed == metrics.total_incidents


def test_real_scorer_is_deterministic():
    """Two identical runs must produce identical audit logs, or the stub-versus-
    real metrics comparison proves nothing."""
    logs = []
    for _ in range(2):
        scenario = ALL_SCENARIOS["rush"]()
        engine = make_engine(world=scenario.world)
        for call in scenario.incidents:
            engine.schedule_incident(call)
        engine.run()
        logs.append([(r.sim_time, r.action, r.chosen, r.rationale)
                     for r in engine.audit.all()])

    assert logs[0] == logs[1], "the same scenario produced two different runs"


def test_real_scorer_changes_the_order_the_stub_produced():
    """
    If the real implementation produced the same order as FIFO, integrating it
    would have achieved nothing. This is the evidence that it did something.
    """
    scenario = ALL_SCENARIOS["rush"]()
    calls = list(scenario.incidents)

    fifo = [c.incident_id for c in
            FifoPrioritizer().prioritize(list(calls), scenario.world, 600.0)]
    real = [c.incident_id for c in
            SeverityPrioritizer().prioritize(list(calls), scenario.world, 600.0)]

    assert sorted(fifo) == sorted(real), "an incident was lost or duplicated"
    assert fifo != real, "the real scorer ordered the queue exactly like FIFO"


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
