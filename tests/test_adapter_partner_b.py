"""
RESQ - Integration test for Partner B's dispatch allocation.

OWNER: Partner D (System Core).

One integration test per merge, per CLAUDE.md section 6.6. This file checks the
translation, the behaviour her scorer is supposed to produce, and the two rules
the adapter must never break: it may not mutate anything, and it may not
override her score.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import allocation as b_allocation

from resq.adapters.partner_a import SeverityPrioritizer
from resq.adapters.partner_b import (
    UNIT_CAPABILITIES,
    AllocationDispatcher,
    to_incident,
    to_resource,
)
from resq.audit import AuditLog
from resq.engine import Engine, EngineConfig
from resq.models import (
    Incident,
    IncidentStatus,
    IncidentType,
    UnitStatus,
    UnitType,
)
from resq.results import ErrorCode
from resq.scenarios import ALL_SCENARIOS, collect_metrics
from resq.stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher
from resq.world import build_sample_city


def make_engine(world=None, dispatcher=None, prioritizer=None):
    return Engine(
        world=world or build_sample_city(),
        prioritizer=prioritizer or FifoPrioritizer(),
        dispatcher=dispatcher or AllocationDispatcher(),
        router=BfsRouter(),
        config=EngineConfig(tick_seconds=30.0),
        audit=AuditLog(echo=False),
    )


def medical(iid="M1", node="N05", at=0.0):
    return Incident(incident_id=iid, node_id=node,
                    incident_type=IncidentType.MEDICAL, reported_at=at,
                    required_unit=UnitType.AMBULANCE)


# ---------------------------------------------------------------------------
# THE TRANSLATION
# ---------------------------------------------------------------------------


def test_unit_becomes_a_resource_her_scorer_accepts():
    world = build_sample_city()
    unit = world.units["A1"]
    resource = to_resource(unit)

    assert resource.resource_id == "A1"
    assert resource.resource_type == "AMBULANCE"
    assert resource.status == "available"
    assert resource.location == unit.current_node
    assert isinstance(resource.workload, int)

    # her scorer must return a real score, not the -1 rejection
    score = b_allocation.calculate_resource_score(to_incident(medical()), resource)
    assert score >= 0, "translation produced a resource her scorer rejects"


def test_capabilities_are_incident_types_not_our_capability_enum():
    """She tests `incident.incident_type in capabilities`. If we passed our
    Capability enum here, nothing would ever match and no unit would dispatch."""
    resource = to_resource(build_sample_city().units["A1"])
    assert IncidentType.MEDICAL.value in resource.capabilities
    assert UNIT_CAPABILITIES[UnitType.HAZMAT_TEAM] == {IncidentType.HAZMAT.value}


def test_busy_units_are_reported_as_busy():
    world = build_sample_city()
    world.units["A1"].status = UnitStatus.EN_ROUTE
    assert to_resource(world.units["A1"]).status == "busy"


def test_created_at_is_derived_from_simulated_time_not_the_wall_clock():
    """Two conversions of the same incident must be identical, or the run
    stops reproducing."""
    call = medical(at=300.0)
    assert to_incident(call).created_at == to_incident(call).created_at


# ---------------------------------------------------------------------------
# THE DECISION
# ---------------------------------------------------------------------------


def test_picks_a_correctly_typed_available_unit():
    world = build_sample_city()
    decision = AllocationDispatcher().select_unit(
        medical(), world, BfsRouter(), 0.0)

    assert decision.ok
    assert world.units[decision.unit_id].unit_type == UnitType.AMBULANCE


def test_every_rejected_unit_is_named_with_a_reason():
    """Section 9 and the 20 decision-quality marks. Her scorer returns a bare
    -1 for three different reasons; the adapter has to say which."""
    decision = AllocationDispatcher().select_unit(
        medical(), build_sample_city(), BfsRouter(), 0.0)

    assert decision.considered, "no alternatives recorded"
    assert all(c.reason for c in decision.considered)
    reasons = " ".join(c.reason for c in decision.considered)
    assert "wrong type" in reasons


def test_no_free_unit_returns_a_code_not_an_exception():
    world = build_sample_city()
    for unit in world.units.values():
        unit.status = UnitStatus.OUT_OF_SERVICE

    decision = AllocationDispatcher().select_unit(
        medical(), world, BfsRouter(), 0.0)

    assert not decision.ok
    assert decision.unit_id is None
    assert decision.error in (ErrorCode.NO_UNIT_AVAILABLE,
                              ErrorCode.NO_SUITABLE_UNIT)
    assert decision.rationale


def test_no_unit_of_the_required_type_is_reported_as_unsuitable():
    world = build_sample_city()
    hazmat = Incident(incident_id="HZ", node_id="N05",
                      incident_type=IncidentType.HAZMAT, reported_at=0.0,
                      required_unit=UnitType.HAZMAT_TEAM)
    world.units["HZ1"].status = UnitStatus.OUT_OF_SERVICE

    decision = AllocationDispatcher().select_unit(hazmat, world, BfsRouter(), 0.0)
    assert not decision.ok
    assert decision.error == ErrorCode.NO_SUITABLE_UNIT


def test_the_adapter_mutates_nothing():
    """Only the engine changes state. If the adapter ever calls her
    dispatch_resource(), this test fails."""
    world = build_sample_city()
    before = {u.unit_id: (u.status, u.current_node, u.assigned_incident_id)
              for u in world.units.values()}
    call = medical()
    call_before = (call.status, call.assigned_unit_id)

    AllocationDispatcher().select_unit(call, world, BfsRouter(), 0.0)

    after = {u.unit_id: (u.status, u.current_node, u.assigned_incident_id)
             for u in world.units.values()}
    assert before == after, "the adapter changed a unit"
    assert (call.status, call.assigned_unit_id) == call_before, \
        "the adapter changed the incident"


def test_her_score_always_beats_the_travel_time_tiebreak():
    """
    The adapter breaks ties on distance but must never override a score she
    computed. A unit she scores higher wins even when it is further away.
    """
    world = build_sample_city()
    # A2 and A3 are both at ST2; give A3 workload so her scorer prefers A2,
    # then move A2 far away so distance would have picked A3.
    world.units["A1"].status = UnitStatus.OUT_OF_SERVICE
    world.units["A3"].total_busy_seconds = 3000.0     # workload 5 -> lower score
    world.units["A2"].current_node = "N12"

    decision = AllocationDispatcher().select_unit(
        medical(node="N09"), world, BfsRouter(), 0.0)

    a2 = b_allocation.calculate_resource_score(
        to_incident(medical(node="N09")), to_resource(world.units["A2"]))
    a3 = b_allocation.calculate_resource_score(
        to_incident(medical(node="N09")), to_resource(world.units["A3"]))
    assert a2 > a3, "test setup failed - scores are not different"
    assert decision.unit_id == "A2", \
        "the distance tiebreak overrode a score she computed"


# ---------------------------------------------------------------------------
# THE PIPELINE STILL WORKS
# ---------------------------------------------------------------------------


def test_real_dispatcher_resolves_a_scenario_end_to_end():
    scenario = ALL_SCENARIOS["rush"]()
    engine = make_engine(world=scenario.world)
    for call in scenario.incidents:
        engine.schedule_incident(call)
    engine.run()

    metrics = collect_metrics(engine, scenario.name)
    assert metrics.resolved + metrics.failed == metrics.total_incidents


def test_both_real_components_together_are_deterministic():
    """A and B wired in at once, twice, must produce identical runs."""
    logs = []
    for _ in range(2):
        scenario = ALL_SCENARIOS["disruption"]()
        engine = make_engine(world=scenario.world,
                             prioritizer=SeverityPrioritizer(),
                             dispatcher=AllocationDispatcher())
        for call in scenario.incidents:
            engine.schedule_incident(call)
        events = sorted(scenario.events, key=lambda e: e[0])
        while not engine._is_finished() and engine.tick_count < 2000:
            while events and events[0][0] <= engine.now:
                events.pop(0)[1](engine)
            engine.tick()
        logs.append([(r.sim_time, r.action, r.chosen, r.rationale)
                     for r in engine.audit.all()])

    assert logs[0] == logs[1], "two identical runs diverged"


def test_real_dispatcher_survives_a_unit_being_disabled():
    """The resilience path, with her scorer in place rather than the stub."""
    scenario = ALL_SCENARIOS["normal"]()
    engine = make_engine(world=scenario.world,
                         prioritizer=SeverityPrioritizer(),
                         dispatcher=AllocationDispatcher())
    for call in scenario.incidents:
        engine.schedule_incident(call)

    for _ in range(4):
        engine.tick()
    assigned = [i for i in engine.world.incidents.values()
                if i.assigned_unit_id]
    if assigned:
        engine.inject_disable_unit(assigned[0].assigned_unit_id)
    engine.run()

    for call in engine.world.incidents.values():
        assert call.status in (IncidentStatus.RESOLVED, IncidentStatus.FAILED), \
            f"{call.incident_id} was stranded at {call.status.value}"


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
