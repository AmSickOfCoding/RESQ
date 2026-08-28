"""
RESQ - Failure injection tests.

OWNER: Partner D (System Core).

Covers the two controls added for the operator console: restore-a-road and
spawn-an-incident. Section 9 of the brief asks for seven controls; with these
the engine now has all seven.

These are engine-level tests on purpose. The console itself is a Tk window and
CI runs headless, so what CI must guarantee is that every button has a real,
working engine method behind it. The window is verified by hand before a demo.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resq.audit import AuditLog
from resq.engine import Engine, EngineConfig
from resq.models import IncidentStatus, IncidentType, UnitStatus, UnitType
from resq.stubs.naive import BfsRouter, FifoPrioritizer, FirstFreeDispatcher
from resq.world import build_sample_city


def make_engine(**cfg):
    return Engine(
        world=build_sample_city(),
        prioritizer=FifoPrioritizer(),
        dispatcher=FirstFreeDispatcher(),
        router=BfsRouter(),
        config=EngineConfig(**cfg) if cfg else EngineConfig(),
        audit=AuditLog(echo=False),
    )


# ---------------------------------------------------------------------------
# RESTORE A ROAD
# ---------------------------------------------------------------------------


def test_restoring_a_road_reopens_both_directions():
    engine = make_engine()
    engine.inject_close_road("N06", "N07")
    assert not engine.world.edge_between("N06", "N07").is_open
    assert not engine.world.edge_between("N07", "N06").is_open

    engine.inject_restore_road("N06", "N07")
    assert engine.world.edge_between("N06", "N07").is_open
    assert engine.world.edge_between("N07", "N06").is_open


def test_restoring_a_road_is_logged_with_a_reason():
    """Every world change has to be explainable afterwards, including the
    recoveries - otherwise the audit trail only tells half the story."""
    engine = make_engine()
    engine.inject_close_road("N06", "N07")
    engine.inject_restore_road("N06", "N07")

    restores = [r for r in engine.audit.all()
                if r.action == "INJECT_ROAD_RESTORED"]
    assert len(restores) == 1
    assert "re-opened" in restores[0].rationale.lower()
    assert restores[0].extra["edges"], "restore recorded no changed edges"


def test_restoring_an_already_open_road_is_harmless():
    """The instructor will click this out of order. It must not raise and it
    must say plainly that nothing changed."""
    engine = make_engine()
    engine.inject_restore_road("N06", "N07")

    record = [r for r in engine.audit.all()
              if r.action == "INJECT_ROAD_RESTORED"][-1]
    assert record.extra["edges"] == []
    assert "already open" in record.rationale.lower()


def test_a_closed_road_can_be_reopened_and_used_again():
    """The point of the control: close the bottleneck, see routing avoid it,
    re-open it, and confirm the graph is genuinely whole again."""
    engine = make_engine()
    world = engine.world

    before = engine.router.find_route("N05", "N08", world, 0.0)
    assert before.ok

    engine.inject_close_road("N06", "N07")
    during = engine.router.find_route("N05", "N08", world, 0.0)

    engine.inject_restore_road("N06", "N07")
    after = engine.router.find_route("N05", "N08", world, 0.0)

    assert after.ok
    assert after.route.node_path == before.route.node_path, \
        "route did not return to its original path after restore"
    if during.ok:
        assert during.route.node_path != before.route.node_path, \
            "closing the bottleneck changed nothing - test city is wrong"


# ---------------------------------------------------------------------------
# SPAWN AN INCIDENT
# ---------------------------------------------------------------------------


def test_spawned_incident_enters_the_normal_pipeline():
    """A hand-spawned call must be indistinguishable from a scripted one."""
    engine = make_engine()
    engine.tick()  # get the clock off zero

    incident = engine.inject_spawn_incident(
        node_id="N10", incident_type=IncidentType.MEDICAL,
        required_unit=UnitType.AMBULANCE, victims=3,
    )
    assert incident.reported_at == engine.now

    engine.tick()
    assert incident.incident_id in engine.world.incidents
    stored = engine.world.incidents[incident.incident_id]
    assert stored.status != IncidentStatus.REPORTED, \
        "spawned incident was never picked up by the pipeline"


def test_spawned_incidents_get_stable_sequential_ids():
    """Ids have to be predictable so the audit screen can be opened on one."""
    engine = make_engine()
    first = engine.inject_spawn_incident(
        node_id="N01", incident_type=IncidentType.FIRE,
        required_unit=UnitType.FIRE_TRUCK)
    second = engine.inject_spawn_incident(
        node_id="N02", incident_type=IncidentType.MEDICAL,
        required_unit=UnitType.AMBULANCE)

    assert first.incident_id == "INJ-01"
    assert second.incident_id == "INJ-02"


def test_spawned_incident_is_resolved_end_to_end():
    engine = make_engine()
    incident = engine.inject_spawn_incident(
        node_id="N02", incident_type=IncidentType.MEDICAL,
        required_unit=UnitType.AMBULANCE, requires_transport=True)

    engine.run()
    stored = engine.world.incidents[incident.incident_id]
    assert stored.status in (IncidentStatus.RESOLVED, IncidentStatus.FAILED)
    assert engine.audit.for_incident(incident.incident_id), \
        "spawned incident produced no audit trail"


def test_a_burst_exhausts_units_and_queues_the_rest():
    """
    The 'demand exceeds resources' step from the brief.

    Spawning more ambulance calls than there are ambulances must leave the
    surplus QUEUED with a stated reason - not crash, and not silently drop.
    """
    engine = make_engine()
    ambulances = [u for u in engine.world.units.values()
                  if u.unit_type == UnitType.AMBULANCE]

    for index in range(len(ambulances) + 3):
        engine.inject_spawn_incident(
            node_id="N05", incident_type=IncidentType.MEDICAL,
            required_unit=UnitType.AMBULANCE, requires_transport=True)

    engine.tick()
    engine.tick()

    queued = [i for i in engine.world.incidents.values()
              if i.status == IncidentStatus.QUEUED]
    assert queued, "nothing queued despite more calls than ambulances"

    refusals = [r for r in engine.audit.all()
                if r.action == "SELECT_UNIT" and r.error != "NONE"]
    assert refusals, "no dispatcher refusal was recorded"
    assert all(r.rationale for r in refusals), \
        "a refusal was recorded with no explanation"


def test_every_brief_required_control_exists():
    """Section 9 lists seven controls. This is the checklist, in code, so a
    missing one fails the build rather than being noticed during the demo."""
    engine = make_engine()
    for method in ("inject_close_road", "inject_restore_road", "inject_traffic",
                   "inject_disable_unit", "inject_fill_hospital",
                   "inject_spawn_incident"):
        assert callable(getattr(engine, method, None)), f"missing {method}"


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
