"""
RESQ - Adapter for Partner C's Dynamic Graph Modeling & Routing.

OWNER: Partner C (Saif) / Partner D (System Core).
This adapter bridges the shared World and simulation contract to Partner C's
spatial CityGraph, A* search, and Dijkstra multi-hospital destination optimizer.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from src.routing.cost import calculate_traversal_time
from src.routing.exceptions import (
    EdgeNotFoundError,
    NoAvailableHospitalError,
    NodeNotFoundError,
    PathNotFoundError,
    RoutingError,
)
from src.routing.facility import find_optimal_hospital
from src.routing.graph import CityGraph, Edge as RoutingEdge, Node as RoutingNode
from src.routing.pathfinder import PathResult, find_fastest_path

from ..interfaces import Router
from ..models import Capability, Hospital, Node, Route
from ..results import Candidate, DestinationDecision, ErrorCode, RouteResult
from ..world import World


def world_to_city_graph(world: World) -> CityGraph:
    """
    Constructs a CityGraph instance from the current World state.
    Preserves dynamic road closures, traffic multipliers, and hospital occupancies.
    """
    graph = CityGraph()

    # 1. Populate nodes
    for node_id, node in world.nodes.items():
        node_type = "INTERSECTION"
        capacity = None
        occupied_beds = 0

        if node_id in world.hospitals:
            h = world.hospitals[node_id]
            node_type = "HOSPITAL"
            capacity = h.capacity
            occupied_beds = h.occupied
        elif node_id in world.stations:
            node_type = "STATION"

        graph.add_node(
            RoutingNode(
                id=node_id,
                x=node.x,
                y=node.y,
                node_type=node_type,
                capacity=capacity,
                occupied_beds=occupied_beds,
            ),
            overwrite=True,
        )

    # 2. Populate edges
    for edge_key, edge in world.edges.items():
        if edge.traffic_multiplier > 1.0:
            congestion = max(0.0, min(0.99, 1.0 - (1.0 / edge.traffic_multiplier)))
        else:
            congestion = 0.0

        r_edge = RoutingEdge(
            source_id=edge.from_node,
            target_id=edge.to_node,
            distance=float(edge.base_seconds),
            speed_limit=1.0,
            congestion=congestion,
            is_closed=not edge.is_open,
        )
        if graph.has_node(edge.from_node) and graph.has_node(edge.to_node):
            graph.add_edge(r_edge, bidirectional=False)

    return graph


class AStarRouter:
    """
    Implements the Router Protocol using Partner C's routing package.

    - find_route(): A* search with Euclidean heuristic and alternative path generation.
    - travel_seconds(): Fast cost lookup for unit dispatch comparison.
    - best_destination(): Dijkstra multi-hospital optimization balancing ETA and capacity.
    """

    name = "A* Routing & Multi-Hospital Optimizer (Partner C)"

    def __init__(self, bed_penalty_seconds: float = 60.0):
        self.bed_penalty_seconds = bed_penalty_seconds

    def find_route(
        self,
        from_node: str,
        to_node: str,
        world: World,
        now: float = 0.0,
    ) -> RouteResult:
        if from_node == to_node:
            route = Route(
                node_path=[from_node],
                total_seconds=0.0,
                computed_at=now,
                notes="Origin and destination are identical.",
            )
            return RouteResult(
                route=route,
                error=ErrorCode.NONE,
                rationale=f"Already at destination {from_node}.",
            )

        if from_node not in world.nodes or to_node not in world.nodes:
            return RouteResult(
                route=None,
                error=ErrorCode.NO_ROUTE,
                rationale=f"Unknown node {from_node} or {to_node}.",
            )

        graph = world_to_city_graph(world)

        try:
            path_res: PathResult = find_fastest_path(
                graph=graph,
                source_id=from_node,
                target_id=to_node,
                priority_tier="STANDARD",
                siren_multiplier=1.0,
            )
        except (PathNotFoundError, NodeNotFoundError, EdgeNotFoundError, RoutingError):
            return RouteResult(
                route=None,
                error=ErrorCode.NO_ROUTE,
                rationale=f"No open road connects {from_node} to {to_node}.",
            )

        # Check for alternative paths if possible
        alternatives: List[List[str]] = []
        if len(path_res.nodes) > 2:
            alt_graph = world_to_city_graph(world)
            mid_src, mid_dst = path_res.nodes[0], path_res.nodes[1]
            if alt_graph.has_edge(mid_src, mid_dst):
                alt_graph.set_road_closure(mid_src, mid_dst, is_closed=True)
                try:
                    alt_res = find_fastest_path(
                        alt_graph, from_node, to_node, priority_tier="STANDARD"
                    )
                    if alt_res.nodes != path_res.nodes:
                        alternatives.append(alt_res.nodes)
                except (PathNotFoundError, RoutingError):
                    pass

        route = Route(
            node_path=path_res.nodes,
            total_seconds=path_res.total_time,
            computed_at=now,
            alternatives=alternatives,
            notes=f"A* path ({len(path_res.nodes) - 1} hops, {path_res.total_time:.0f}s).",
        )

        return RouteResult(
            route=route,
            error=ErrorCode.NONE,
            rationale=f"A* fastest path with {len(path_res.nodes) - 1} segments ({path_res.total_time:.0f}s).",
        )

    def travel_seconds(
        self,
        from_node: str,
        to_node: str,
        world: World,
        now: float = 0.0,
    ) -> Optional[float]:
        result = self.find_route(from_node, to_node, world, now)
        return result.route.total_seconds if result.ok and result.route else None

    def best_destination(
        self,
        from_node: str,
        world: World,
        required: Optional[Set[Capability]] = None,
        now: float = 0.0,
    ) -> DestinationDecision:
        considered: List[Candidate] = []
        valid_candidates: List[Tuple[float, str, Route, Hospital]] = []

        for hospital in world.hospitals.values():
            if not hospital.has_space:
                considered.append(
                    Candidate(
                        option_id=hospital.node_id,
                        score=float("inf"),
                        reason="at full capacity",
                    )
                )
                continue

            if required and not required.issubset(hospital.capabilities):
                missing = ", ".join(c.value for c in (required - hospital.capabilities))
                considered.append(
                    Candidate(
                        option_id=hospital.node_id,
                        score=float("inf"),
                        reason=f"missing capability: {missing}",
                    )
                )
                continue

            route_res = self.find_route(from_node, hospital.node_id, world, now)
            if not route_res.ok or not route_res.route:
                considered.append(
                    Candidate(
                        option_id=hospital.node_id,
                        score=float("inf"),
                        reason="unreachable",
                    )
                )
                continue

            travel_time = route_res.route.total_seconds
            composite_score = travel_time + (hospital.occupied * self.bed_penalty_seconds)

            considered.append(
                Candidate(
                    option_id=hospital.node_id,
                    score=composite_score,
                    reason=f"{travel_time:.0f}s travel, {hospital.free_beds} beds free (score: {composite_score:.0f})",
                )
            )
            valid_candidates.append((composite_score, hospital.node_id, route_res.route, hospital))

        if not valid_candidates:
            return DestinationDecision(
                node_id=None,
                error=ErrorCode.NO_DESTINATION_AVAILABLE,
                rationale="Every hospital is full, unsuitable or unreachable.",
                considered=considered,
            )

        valid_candidates.sort(key=lambda item: item[0])
        best_score, best_node_id, best_route, best_hospital = valid_candidates[0]

        rationale = (
            f"Partner C optimizer selected {best_hospital.name}: "
            f"optimal balance of travel ETA ({best_route.total_seconds:.0f}s) "
            f"and capacity ({best_hospital.free_beds} beds free, composite score {best_score:.0f})."
        )

        return DestinationDecision(
            node_id=best_node_id,
            route=best_route,
            rationale=rationale,
            error=ErrorCode.NONE,
            considered=[c for c in considered if c.option_id != best_node_id],
        )


DijkstraRouter = AStarRouter
