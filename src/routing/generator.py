"""Synthetic grid network generator for RESQ routing simulations and benchmarks."""

import random
from typing import Optional

from src.routing.exceptions import InvalidGraphError
from src.routing.graph import CityGraph, Edge, Node, NodeId


def generate_synthetic_city_graph(
    rows: int = 5,
    cols: int = 5,
    grid_spacing: float = 500.0,
    default_speed_limit: float = 13.89,
    num_stations: int = 2,
    num_hospitals: int = 2,
    seed: Optional[int] = 42,
) -> CityGraph:
    """Generates a synthetic grid-based CityGraph network populated with stations and hospitals.

    Args:
        rows: Number of horizontal grid rows (must be >= 1).
        cols: Number of vertical grid columns (must be >= 1).
        grid_spacing: Distance in meters between adjacent grid nodes (default 500.0m).
        default_speed_limit: Default speed limit in m/s (default 13.89 m/s ~ 50 km/h).
        num_stations: Number of nodes to designate as fire/EMS STATIONS.
        num_hospitals: Number of nodes to designate as HOSPITALS.
        seed: Random seed for reproducible station/hospital placement.

    Returns:
        Populated CityGraph with nodes, types, hospital capacities, and bidirectional edges.

    Raises:
        InvalidGraphError: If dimensions or node count requirements are violated.
    """
    if rows < 1 or cols < 1:
        raise InvalidGraphError(f"Grid dimensions must be at least 1x1, got {rows}x{cols}.")

    total_nodes = rows * cols
    if num_stations + num_hospitals > total_nodes:
        raise InvalidGraphError(
            f"Requested {num_stations} stations + {num_hospitals} hospitals exceed total grid nodes ({total_nodes})."
        )

    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    graph = CityGraph()
    all_coords = [(r, c) for r in range(rows) for c in range(cols)]
    
    # Randomly select distinct grid locations for stations and hospitals
    selected_coords = rng.sample(all_coords, num_stations + num_hospitals)
    station_coords = set(selected_coords[:num_stations])
    hospital_coords = set(selected_coords[num_stations:])

    # Register nodes
    for r in range(rows):
        for c in range(cols):
            node_id: NodeId = f"N_{r}_{c}"
            x = c * grid_spacing
            y = r * grid_spacing

            if (r, c) in station_coords:
                node = Node(id=node_id, x=x, y=y, node_type="STATION")
            elif (r, c) in hospital_coords:
                node = Node(
                    id=node_id,
                    x=x,
                    y=y,
                    node_type="HOSPITAL",
                    capacity=20,
                    occupied_beds=5,
                )
            else:
                node = Node(id=node_id, x=x, y=y, node_type="INTERSECTION")

            graph.add_node(node)

    # Register bidirectional grid edges
    for r in range(rows):
        for c in range(cols):
            curr_id = f"N_{r}_{c}"
            
            # Horizontal right neighbor
            if c + 1 < cols:
                right_id = f"N_{r}_{c+1}"
                edge = Edge(
                    source_id=curr_id,
                    target_id=right_id,
                    distance=grid_spacing,
                    speed_limit=default_speed_limit,
                    congestion=0.0,
                    is_closed=False,
                )
                graph.add_edge(edge, bidirectional=True)

            # Vertical top neighbor
            if r + 1 < rows:
                top_id = f"N_{r+1}_{c}"
                edge = Edge(
                    source_id=curr_id,
                    target_id=top_id,
                    distance=grid_spacing,
                    speed_limit=default_speed_limit,
                    congestion=0.0,
                    is_closed=False,
                )
                graph.add_edge(edge, bidirectional=True)

    return graph
