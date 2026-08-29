"""
RESQ - Integration test for Partner C's routing and graph engine.

OWNER: Partner D (System Core) / Partner C (Saif).

Verifies that:
  1. The adapter translates World state into CityGraph and executes A* and Dijkstra.
  2. A* selects fastest routes taking traffic multipliers into account (beating naive hop-count).
  3. Dynamic road closures trigger alternate routes or return ErrorCode.NO_ROUTE cleanly.
  4. Hospital selection balances travel time and bed capacity, bypassing full hospitals.
  5. Full simulation pipeline resolves across all three scenarios (normal, rush, disruption).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resq.adapters.partner_a import SeverityPrioritizer
from resq.adapters.partner_b import AllocationDispatcher
from resq.adapters.partner_c import AStarRouter, DijkstraRouter, world_to_city_graph
from resq.audit import AuditLog
from resq.engine import Engine, EngineConfig
from resq.models import (
    Capability,
    Hospital,
    Incident,
    IncidentStatus,
    IncidentType,
    Node,
    NodeKind,
    UnitType,
)
from resq.results import ErrorCode
from resq.scenarios import ALL_SCENARIOS
from resq.stubs.naive import BfsRouter
from resq.world import World, build_sample_city


def make_engine(world=None, prioritizer=None, dispatcher=None, router=None):
    return Engine(
        world=world or build_sample_city(),
        prioritizer=prioritizer or SeverityPrioritizer(),
        dispatcher=dispatcher or AllocationDispatcher(),
        router=router or AStarRouter(),
        config=EngineConfig(tick_seconds=30.0),
        audit=AuditLog(echo=False),
    )


# ---------------------------------------------------------------------------
# 1. GRAPH TRANSLATION & ROUTING OPTIMALITY
# ---------------------------------------------------------------------------


def test_world_to_city_graph_populates_nodes_and_edges():
    world = build_sample_city()
    graph = world_to_city_graph(world)

    assert graph.node_count == len(world.nodes)
    assert graph.edge_count == len(world.edges)
    assert len(graph.get_hospitals()) == len(world.hospitals)
    assert len(graph.get_stations()) == len(world.stations)


def test_a_star_beats_naive_bfs_under_traffic():
    """
    Graph topology:
      Origin (A) ---> Destination (C) via direct road with 5.0x traffic (cost = 500s)
      Origin (A) -> Intermediate (B) -> Destination (C) with clear road (cost = 100s + 100s = 200s)
    
    BFS picks 1-hop path (500s) because it ignores traffic.
    A* picks 2-hop path (200s) because it minimizes actual travel time.
    """
    world = World()
    world.add_node(Node(node_id="A", name="Start", x=0.0, y=0.0))
    world.add_node(Node(node_id="B", name="Mid", x=50.0, y=50.0))
    world.add_node(Node(node_id="C", name="Goal", x=100.0, y=0.0))

    world.add_road("A", "C", base_seconds=100.0)
    world.edges["A->C"].traffic_multiplier = 5.0  # 500s

    world.add_road("A", "B", base_seconds=100.0)  # 100s
    world.add_road("B", "C", base_seconds=100.0)  # 100s

    bfs_res = BfsRouter().find_route("A", "C", world)
    astar_res = AStarRouter().find_route("A", "C", world)

    assert bfs_res.route.node_path == ["A", "C"], "BFS should have picked 1 hop"
    assert bfs_res.route.total_seconds == 500.0

    assert astar_res.route.node_path == ["A", "B", "C"], "A* should have picked the faster 2-hop route"
    assert astar_res.route.total_seconds == 200.0


def test_road_closure_triggers_detour():
    world = build_sample_city()
    # N01 -> N02 is a direct road. If closed, router must find alternate path.
    world.close_road("N01", "N02", both_ways=True)

    result = AStarRouter().find_route("N01", "N02", world)
    assert result.ok
    assert result.route.node_path != ["N01", "N02"]
    assert result.route.node_path[0] == "N01"
    assert result.route.node_path[-1] == "N02"


def test_disconnected_graph_returns_no_route_error():
    world = World()
    world.add_node(Node("A", "A"))
    world.add_node(Node("B", "B"))
    # No edges between A and B

    result = AStarRouter().find_route("A", "B", world)
    assert not result.ok
    assert result.error == ErrorCode.NO_ROUTE
    assert result.route is None


# ---------------------------------------------------------------------------
# 2. MULTI-HOSPITAL DESTINATION OPTIMIZATION
# ---------------------------------------------------------------------------


def test_multi_hospital_optimization_penalizes_occupied_beds():
    world = World()
    world.add_node(Node("INC", "Incident", x=0.0, y=0.0))
    world.add_node(Node("H1", "Busy Hospital", x=100.0, y=0.0, kind=NodeKind.HOSPITAL))
    world.add_node(Node("H2", "Empty Hospital", x=300.0, y=0.0, kind=NodeKind.HOSPITAL))

    world.hospitals["H1"] = Hospital(node_id="H1", name="Busy Hospital", capacity=20, occupied=10)
    world.hospitals["H2"] = Hospital(node_id="H2", name="Empty Hospital", capacity=20, occupied=0)

    world.add_road("INC", "H1", base_seconds=100.0)  # 100s travel + (10 * 60s) = 700s score
    world.add_road("INC", "H2", base_seconds=300.0)  # 300s travel + (0 * 60s) = 300s score

    decision = AStarRouter(bed_penalty_seconds=60.0).best_destination("INC", world)
    assert decision.ok
    assert decision.node_id == "H2", "Should have selected H2 due to lower composite cost"
    assert len(decision.considered) == 1
    assert decision.considered[0].option_id == "H1"


def test_full_hospital_is_bypassed():
    world = World()
    world.add_node(Node("INC", "Incident", x=0.0, y=0.0))
    world.add_node(Node("H1", "Full Hospital", x=50.0, y=0.0, kind=NodeKind.HOSPITAL))
    world.add_node(Node("H2", "Available Hospital", x=200.0, y=0.0, kind=NodeKind.HOSPITAL))

    world.hospitals["H1"] = Hospital(node_id="H1", name="Full Hospital", capacity=5, occupied=5)
    world.hospitals["H2"] = Hospital(node_id="H2", name="Available Hospital", capacity=10, occupied=1)

    world.add_road("INC", "H1", base_seconds=50.0)
    world.add_road("INC", "H2", base_seconds=200.0)

    decision = AStarRouter().best_destination("INC", world)
    assert decision.ok
    assert decision.node_id == "H2"
    rejected_h1 = [c for c in decision.considered if c.option_id == "H1"][0]
    assert "at full capacity" in rejected_h1.reason


def test_all_hospitals_full_returns_no_destination_available():
    world = World()
    world.add_node(Node("INC", "Incident"))
    world.add_node(Node("H1", "Hospital 1", kind=NodeKind.HOSPITAL))
    world.hospitals["H1"] = Hospital("H1", "Hospital 1", capacity=5, occupied=5)
    world.add_road("INC", "H1", base_seconds=50.0)

    decision = AStarRouter().best_destination("INC", world)
    assert not decision.ok
    assert decision.error == ErrorCode.NO_DESTINATION_AVAILABLE
    assert decision.node_id is None


# ---------------------------------------------------------------------------
# 3. END-TO-END SYSTEM PIPELINE INTEGRATION
# ---------------------------------------------------------------------------


def test_real_router_runs_all_three_scenarios_to_completion():
    for key in ("normal", "rush", "disruption"):
        scenario = ALL_SCENARIOS[key]()
        engine = make_engine(world=scenario.world)
        for call in scenario.incidents:
            engine.schedule_incident(call)
        events = sorted(scenario.events, key=lambda e: e[0])
        while not engine._is_finished() and engine.tick_count < 2000:
            while events and events[0][0] <= engine.now:
                events.pop(0)[1](engine)
            engine.tick()

        for call in engine.world.incidents.values():
            assert call.status in (IncidentStatus.RESOLVED, IncidentStatus.FAILED), (
                f"{key}/{call.incident_id} stuck at {call.status.value}"
            )


def test_router_is_deterministic():
    logs = []
    for _ in range(2):
        scenario = ALL_SCENARIOS["disruption"]()
        engine = make_engine(world=scenario.world)
        for call in scenario.incidents:
            engine.schedule_incident(call)
        events = sorted(scenario.events, key=lambda e: e[0])
        while not engine._is_finished() and engine.tick_count < 2000:
            while events and events[0][0] <= engine.now:
                events.pop(0)[1](engine)
            engine.tick()
        logs.append([r.as_line() for r in engine.audit.all()])

    assert logs[0] == logs[1], "Simulation with Partner C router was not deterministic"
