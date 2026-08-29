"""
RESQ - Integration tests.

OWNER: Partner D (System Core).

Run with:  python -m pytest tests -q      (or python tests/test_integration.py)

These tests run a full incident through all four components. Add one test per
merge: when A, B or C swaps in their real implementation, these must still pass
before the pull request is approved. That is our regression safety net and it is
what Section 10 asks for.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resq.engine import Engine, EngineConfig
from resq.models import (
    Capability,
    Incident,
    IncidentStatus,
    IncidentType,
    UnitStatus,
    UnitType,
)
from resq.scenarios import ALL_SCENARIOS, collect_metrics
from resq.stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher
from resq.world import build_sample_city


def make_engine(world=None, **cfg):
    """Build an engine with whatever components are currently wired in."""
    return Engine(
        world=world or build_sample_city(),
        prioritizer=FifoPrioritizer(),
        dispatcher=FirstFreeDispatcher(),
        router=BfsRouter(),
        config=EngineConfig(**cfg),
    )


def test_single_incident_resolves_end_to_end():
    """The core happy path: report -> prioritize -> dispatch -> route -> resolve."""
    engine = make_engine()
    engine.schedule_incident(Incident(
        incident_id="T1", node_id="N06", incident_type=IncidentType.MEDICAL,
        reported_at=30, required_unit=UnitType.AMBULANCE, requires_transport=True,
    ))
    engine.run()

    incident = engine.world.incidents["T1"]
    assert incident.status == IncidentStatus.RESOLVED
    assert incident.assigned_unit_id is not None
    assert incident.response_seconds is not None and incident.response_seconds > 0
    assert incident.destination_hospital is not None


def test_every_decision_is_logged_with_a_reason():
    """Auditability: no decision may be recorded without an explanation."""
    engine = make_engine()
    engine.schedule_incident(Incident(
        incident_id="T2", node_id="N11", incident_type=IncidentType.FIRE,
        reported_at=30, required_unit=UnitType.FIRE_TRUCK,
    ))
    engine.run()

    chain = engine.audit.for_incident("T2")
    assert chain, "no audit records were written"
    assert any(r.component == "DISPATCHER" for r in chain)
    assert any(r.component == "ROUTER" for r in chain)
    for record in chain:
        assert record.rationale or record.error != "NONE", \
            f"{record.action} was logged with no explanation"


def test_road_closure_triggers_a_reroute():
    """Resilience: closing a road under a moving unit must produce a new route."""
    engine = make_engine()
    engine.schedule_incident(Incident(
        incident_id="T3", node_id="N08", incident_type=IncidentType.MEDICAL,
        reported_at=30, required_unit=UnitType.AMBULANCE,
    ))
    engine.tick()  # spawn and dispatch
    engine.tick()  # start moving

    before = list(engine.world.units["A1"].route.node_path) \
        if engine.world.units["A1"].route else None

    # close whichever road the assigned unit is currently using
    unit = next(u for u in engine.world.units.values() if u.route is not None)
    first_edge = unit.route.node_path[0], unit.route.node_path[1]
    engine.inject_close_road(*first_edge)

    assert any(r.action == "REROUTE" for r in engine.audit.all()), \
        "closing an in-use road did not trigger a reroute"


def test_no_route_is_reported_not_crashed():
    """An isolated incident must fail cleanly with NO_ROUTE, never throw."""
    world = build_sample_city()
    # cut the eastern hospital off completely
    for neighbour in ("N03", "N04"):
        world.close_road("H1", neighbour)

    engine = make_engine(world=world)
    engine.schedule_incident(Incident(
        incident_id="T4", node_id="H1", incident_type=IncidentType.MEDICAL,
        reported_at=30, required_unit=UnitType.AMBULANCE,
    ))
    engine.run(until=2000)

    incident = engine.world.incidents["T4"]
    assert incident.status in (IncidentStatus.QUEUED, IncidentStatus.FAILED)
    assert any(r.error == "NO_ROUTE" for r in engine.audit.all())


def test_disabling_a_unit_returns_its_incident_to_the_queue():
    """Failure injection: losing a unit must not lose the incident."""
    engine = make_engine()
    engine.schedule_incident(Incident(
        incident_id="T5", node_id="N06", incident_type=IncidentType.MEDICAL,
        reported_at=30, required_unit=UnitType.AMBULANCE,
    ))
    engine.tick()

    assigned = engine.world.incidents["T5"].assigned_unit_id
    assert assigned is not None
    engine.inject_disable_unit(assigned)

    incident = engine.world.incidents["T5"]
    assert incident.status == IncidentStatus.QUEUED
    assert incident.assigned_unit_id is None
    assert engine.world.units[assigned].status == UnitStatus.OUT_OF_SERVICE


def test_full_hospital_forces_an_alternative_destination():
    """Changing condition: a saturated hospital must be skipped, with a reason."""
    world = build_sample_city()
    world.fill_hospital("H1")

    engine = make_engine(world=world)
    engine.schedule_incident(Incident(
        incident_id="T6", node_id="N03", incident_type=IncidentType.MEDICAL,
        reported_at=30, required_unit=UnitType.AMBULANCE, requires_transport=True,
    ))
    engine.run()

    incident = engine.world.incidents["T6"]
    assert incident.destination_hospital == "H2", "did not divert away from full H1"
    rejections = [
        c for r in engine.audit.for_incident("T6") for c in r.considered
    ]
    assert any(c["option_id"] == "H1" for c in rejections), \
        "the rejected hospital was not recorded in the audit trail"


def test_all_three_scenarios_complete():
    """Every required simulation mode must run to completion without error."""
    for key, builder in ALL_SCENARIOS.items():
        scenario = builder()
        engine = make_engine(world=scenario.world)
        for incident in scenario.incidents:
            engine.schedule_incident(incident)

        events = sorted(scenario.events, key=lambda e: e[0])
        while not engine._is_finished() and engine.tick_count < 2000:
            while events and events[0][0] <= engine.now:
                events.pop(0)[1](engine)
            engine.tick()

        metrics = collect_metrics(engine, scenario.name)
        assert metrics.total_incidents == len(scenario.incidents)
        assert metrics.resolved + metrics.failed == metrics.total_incidents, \
            f"{key}: some incidents never reached a terminal state"


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
