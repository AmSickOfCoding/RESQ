"""Multi-facility hospital selection using Dijkstra search for RESQ routing engine."""

from dataclasses import dataclass
import heapq
import math
from typing import Dict, List, Optional, Set, Tuple

from src.routing.cost import calculate_traversal_time
from src.routing.exceptions import NoAvailableHospitalError, NodeNotFoundError
from src.routing.graph import CityGraph, Edge, Node, NodeId
from src.routing.pathfinder import PathResult


@dataclass
class HospitalSelectionResult:
    """Encapsulates the selected optimal hospital and associated dispatch metrics.

    Attributes:
        hospital_node: The selected optimal Node instance (node_type="HOSPITAL").
        path_result: PathResult containing route details from incident to hospital.
        total_cost: Weighted objective score = travel_time + (occupied_beds * bed_penalty_factor).
        travel_time: Pure estimated travel time in seconds.
        occupied_beds: Count of occupied beds at the selected hospital at dispatch time.
    """

    hospital_node: Node
    path_result: PathResult
    total_cost: float
    travel_time: float
    occupied_beds: int


def find_optimal_hospital(
    graph: CityGraph,
    incident_id: NodeId,
    priority_tier: str = "CRITICAL",
    bed_penalty_factor: float = 60.0,
    ignore_full_hospitals: bool = True,
    siren_multiplier: float = 1.25,
) -> HospitalSelectionResult:
    """Evaluates all accessible hospitals from an incident using one-to-all Dijkstra search.

    Selects the hospital that minimizes total composite cost:
        total_cost = travel_time + (occupied_beds * bed_penalty_factor)

    Args:
        graph: CityGraph network instance.
        incident_id: Node ID where the emergency incident occurred.
        priority_tier: Priority tier ("CRITICAL", "STANDARD").
        bed_penalty_factor: Penalty in seconds per occupied bed (default 60.0s/bed).
        ignore_full_hospitals: If True, excludes hospitals where occupied_beds >= capacity.
        siren_multiplier: Right-of-way speed multiplier for emergency response.

    Returns:
        HospitalSelectionResult with the best hospital node, path, and score metrics.

    Raises:
        NodeNotFoundError: If incident_id does not exist in graph.
        NoAvailableHospitalError: If no accessible or capacity-available hospital exists.
    """
    incident_node = graph.get_node(incident_id)

    hospitals = graph.get_hospitals()
    if not hospitals:
        raise NoAvailableHospitalError(incident_id, message="No hospital nodes registered in graph.")

    # One-to-all Dijkstra search from incident_id
    open_heap: List[Tuple[float, int, NodeId]] = []
    counter = 0
    heapq.heappush(open_heap, (0.0, counter, incident_id))

    g_score: Dict[NodeId, float] = {incident_id: 0.0}
    came_from: Dict[NodeId, Tuple[NodeId, Edge]] = {}
    visited: Set[NodeId] = set()

    while open_heap:
        curr_dist, _, curr_id = heapq.heappop(open_heap)

        if curr_id in visited:
            continue
        visited.add(curr_id)

        neighbors = graph.get_neighbors(curr_id)
        for neighbor_id, edge in neighbors.items():
            if neighbor_id in visited:
                continue

            traversal_time = calculate_traversal_time(
                edge=edge,
                priority_tier=priority_tier,
                siren_multiplier=siren_multiplier,
            )

            if math.isinf(traversal_time):
                continue

            tentative_g = g_score[curr_id] + traversal_time
            if tentative_g < g_score.get(neighbor_id, math.inf):
                g_score[neighbor_id] = tentative_g
                came_from[neighbor_id] = (curr_id, edge)
                counter += 1
                heapq.heappush(open_heap, (tentative_g, counter, neighbor_id))

    best_hospital: Optional[Node] = None
    best_total_cost = math.inf
    best_travel_time = math.inf

    for hospital in hospitals:
        h_id = hospital.id
        if h_id not in g_score or math.isinf(g_score[h_id]):
            continue  # Unreachable hospital

        if ignore_full_hospitals and hospital.capacity is not None:
            if hospital.occupied_beds >= hospital.capacity:
                continue  # Skip full hospital

        travel_time = g_score[h_id]
        total_cost = travel_time + (hospital.occupied_beds * bed_penalty_factor)

        if total_cost < best_total_cost:
            best_total_cost = total_cost
            best_travel_time = travel_time
            best_hospital = hospital

    if best_hospital is None:
        raise NoAvailableHospitalError(
            incident_id,
            message=f"No accessible or capacity-available hospital found for incident at node '{incident_id}'.",
        )

    # Reconstruct path to best hospital
    target_id = best_hospital.id
    path_nodes: List[NodeId] = [target_id]
    path_edges: List[Tuple[NodeId, NodeId]] = []
    total_distance = 0.0

    curr = target_id
    while curr in came_from:
        prev_node, edge = came_from[curr]
        path_nodes.append(prev_node)
        path_edges.append((prev_node, curr))
        total_distance += edge.distance
        curr = prev_node

    path_nodes.reverse()
    path_edges.reverse()

    path_result = PathResult(
        nodes=path_nodes,
        edges=path_edges,
        total_distance=total_distance,
        total_time=best_travel_time,
        priority_tier=priority_tier,
    )

    return HospitalSelectionResult(
        hospital_node=best_hospital,
        path_result=path_result,
        total_cost=best_total_cost,
        travel_time=best_travel_time,
        occupied_beds=best_hospital.occupied_beds,
    )
