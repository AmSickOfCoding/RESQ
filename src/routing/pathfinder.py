"""A* pathfinding algorithm and dynamic mid-transit rerouting engine for RESQ."""

from dataclasses import dataclass
import heapq
import math
from typing import Dict, List, Optional, Set, Tuple

from src.routing.cost import calculate_traversal_time
from src.routing.exceptions import NodeNotFoundError, PathNotFoundError
from src.routing.graph import CityGraph, Edge, Node, NodeId


@dataclass
class PathResult:
    """Encapsulates the optimal path resulting from spatial pathfinding.

    Attributes:
        nodes: Sequential list of node IDs from source to target.
        edges: Sequential list of directed (source_id, target_id) edge tuples.
        total_distance: Total path distance in meters.
        total_time: Total estimated traversal time in seconds.
        priority_tier: Priority classification used for path calculation.
    """

    nodes: List[NodeId]
    edges: List[Tuple[NodeId, NodeId]]
    total_distance: float
    total_time: float
    priority_tier: str = "STANDARD"


def _euclidean_heuristic(
    curr_node: Node,
    target_node: Node,
    max_speed_limit: float,
    priority_tier: str,
    siren_multiplier: float,
) -> float:
    """Calculates admissible Euclidean distance travel time lower bound in seconds.

    Heuristic formula:
        h(n) = EuclideanDistance(curr, target) / (max_speed_limit * siren_factor)
    """
    spatial_dist = curr_node.distance_to(target_node)
    effective_max_speed = max_speed_limit
    if priority_tier.upper() in {"CRITICAL", "HIGH"}:
        effective_max_speed *= siren_multiplier

    if effective_max_speed <= 0:
        return 0.0

    return spatial_dist / effective_max_speed


def find_fastest_path(
    graph: CityGraph,
    source_id: NodeId,
    target_id: NodeId,
    priority_tier: str = "STANDARD",
    siren_multiplier: float = 1.25,
) -> PathResult:
    """Finds the fastest travel route between source and target nodes using A* search.

    Args:
        graph: CityGraph network instance.
        source_id: Starting node ID.
        target_id: Destination node ID.
        priority_tier: Priority tier ("STANDARD", "CRITICAL").
        siren_multiplier: Speed multiplier applied if priority_tier is CRITICAL.

    Returns:
        PathResult containing ordered node list, edges, total distance, and travel time.

    Raises:
        NodeNotFoundError: If source_id or target_id does not exist in graph.
        PathNotFoundError: If target is unreachable due to closures or graph partitioning.
    """
    source_node = graph.get_node(source_id)
    target_node = graph.get_node(target_id)

    if source_id == target_id:
        return PathResult(
            nodes=[source_id],
            edges=[],
            total_distance=0.0,
            total_time=0.0,
            priority_tier=priority_tier,
        )

    max_speed = graph.max_speed_limit()

    # Min-heap queue elements: (f_score, counter, current_node_id)
    counter = 0
    open_heap: List[Tuple[float, int, NodeId]] = []
    
    h_start = _euclidean_heuristic(source_node, target_node, max_speed, priority_tier, siren_multiplier)
    heapq.heappush(open_heap, (h_start, counter, source_id))

    g_score: Dict[NodeId, float] = {source_id: 0.0}
    came_from: Dict[NodeId, Tuple[NodeId, Edge]] = {}
    visited: Set[NodeId] = set()

    while open_heap:
        _, _, curr_id = heapq.heappop(open_heap)

        if curr_id in visited:
            continue
        visited.add(curr_id)

        if curr_id == target_id:
            # Path reconstruction
            path_nodes: List[NodeId] = [target_id]
            path_edges: List[Tuple[NodeId, NodeId]] = []
            total_distance = 0.0
            total_time = g_score[target_id]

            curr = target_id
            while curr in came_from:
                prev_node, edge = came_from[curr]
                path_nodes.append(prev_node)
                path_edges.append((prev_node, curr))
                total_distance += edge.distance
                curr = prev_node

            path_nodes.reverse()
            path_edges.reverse()

            return PathResult(
                nodes=path_nodes,
                edges=path_edges,
                total_distance=total_distance,
                total_time=total_time,
                priority_tier=priority_tier,
            )

        curr_node = graph.get_node(curr_id)
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
                neighbor_node = graph.get_node(neighbor_id)
                h_cost = _euclidean_heuristic(
                    neighbor_node, target_node, max_speed, priority_tier, siren_multiplier
                )
                f_score = tentative_g + h_cost
                counter += 1
                heapq.heappush(open_heap, (f_score, counter, neighbor_id))

    raise PathNotFoundError(source_id, target_id)


def reroute_path(
    graph: CityGraph,
    current_node_id: NodeId,
    target_id: NodeId,
    priority_tier: str = "STANDARD",
    siren_multiplier: float = 1.25,
) -> PathResult:
    """Recalculates active vehicle path starting from its current node location.

    Used when dynamic disruptions (road closures or high congestion) invalidate
    or degrade the active route.

    Args:
        graph: Updated CityGraph network instance.
        current_node_id: Current position of the emergency response vehicle.
        target_id: Destination node ID.
        priority_tier: Priority tier ("STANDARD", "CRITICAL").
        siren_multiplier: Emergency speed multiplier.

    Returns:
        New PathResult from current position to target destination.
    """
    return find_fastest_path(
        graph=graph,
        source_id=current_node_id,
        target_id=target_id,
        priority_tier=priority_tier,
        siren_multiplier=siren_multiplier,
    )
