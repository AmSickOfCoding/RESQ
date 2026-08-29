"""Spatial Graph data structures for the RESQ digital twin routing module."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Set, Tuple, Union

from src.routing.exceptions import (
    DuplicateNodeError,
    EdgeNotFoundError,
    InvalidCostParametersError,
    InvalidGraphError,
    NodeNotFoundError,
)

NodeId = Union[int, str]
VALID_NODE_TYPES: Set[str] = {"INTERSECTION", "STATION", "HOSPITAL", "INCIDENT"}


@dataclass
class Node:
    """Represents a spatial node (intersection, station, hospital, or incident) in the city topology.

    Attributes:
        id: Unique identifier for the node (int or str).
        x: X-coordinate (e.g., spatial longitude or Cartesian offset in meters).
        y: Y-coordinate (e.g., spatial latitude or Cartesian offset in meters).
        node_type: Functional type ("INTERSECTION", "STATION", "HOSPITAL", "INCIDENT").
        capacity: Optional maximum bed/patient capacity (primarily for HOSPITAL nodes).
        occupied_beds: Current number of occupied beds (primarily for HOSPITAL nodes).
    """

    id: NodeId
    x: float
    y: float
    node_type: str = "INTERSECTION"
    capacity: Optional[int] = None
    occupied_beds: int = 0

    def __post_init__(self) -> None:
        self.node_type = self.node_type.upper()
        if self.node_type not in VALID_NODE_TYPES:
            raise InvalidGraphError(
                f"Invalid node_type '{self.node_type}'. Must be one of {sorted(VALID_NODE_TYPES)}."
            )
        if self.capacity is not None and self.capacity < 0:
            raise InvalidGraphError(f"Node capacity cannot be negative: {self.capacity}")
        if self.occupied_beds < 0:
            raise InvalidGraphError(f"Node occupied_beds cannot be negative: {self.occupied_beds}")

    def distance_to(self, other: "Node") -> float:
        """Calculates Euclidean distance between this node and another spatial node."""
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass
class Edge:
    """Represents a directed road segment connecting two nodes in the city graph.

    Attributes:
        source_id: Node ID of the segment origin.
        target_id: Node ID of the segment destination.
        distance: Physical length of the road segment in meters (must be > 0).
        speed_limit: Speed limit in meters per second (must be > 0).
        congestion: Dynamic congestion factor ranging from 0.0 (free flow) to 1.0 (gridlock).
        is_closed: Flag indicating whether the road segment is blocked/closed to traffic.
    """

    source_id: NodeId
    target_id: NodeId
    distance: float
    speed_limit: float
    congestion: float = 0.0
    is_closed: bool = False

    def __post_init__(self) -> None:
        if self.distance <= 0:
            raise InvalidCostParametersError(f"Edge distance must be strictly positive: {self.distance}")
        if self.speed_limit <= 0:
            raise InvalidCostParametersError(f"Edge speed_limit must be strictly positive: {self.speed_limit}")
        if not (0.0 <= self.congestion <= 1.0):
            raise InvalidCostParametersError(
                f"Edge congestion must be in range [0.0, 1.0], got: {self.congestion}"
            )


class CityGraph:
    """Directed spatial graph maintaining city road network topology and dynamic state."""

    def __init__(self) -> None:
        self._nodes: Dict[NodeId, Node] = {}
        self._adj: Dict[NodeId, Dict[NodeId, Edge]] = {}

    @property
    def node_count(self) -> int:
        """Returns total number of nodes in the graph."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Returns total number of directed edges in the graph."""
        return sum(len(neighbors) for neighbors in self._adj.values())

    def add_node(self, node: Node, overwrite: bool = False) -> None:
        """Adds a node to the graph.

        Args:
            node: The Node instance to register.
            overwrite: If True, existing node with the same ID will be replaced.

        Raises:
            DuplicateNodeError: If node already exists and overwrite is False.
        """
        if node.id in self._nodes and not overwrite:
            raise DuplicateNodeError(node.id)

        self._nodes[node.id] = node
        if node.id not in self._adj:
            self._adj[node.id] = {}

    def add_edge(self, edge: Edge, bidirectional: bool = False) -> None:
        """Adds a directed edge (and optionally reverse edge) to the graph.

        Args:
            edge: The Edge instance to insert.
            bidirectional: If True, also adds a reverse edge from target to source.

        Raises:
            NodeNotFoundError: If either source or target node is missing from graph.
        """
        if edge.source_id not in self._nodes:
            raise NodeNotFoundError(edge.source_id)
        if edge.target_id not in self._nodes:
            raise NodeNotFoundError(edge.target_id)

        self._adj[edge.source_id][edge.target_id] = edge

        if bidirectional:
            reverse_edge = Edge(
                source_id=edge.target_id,
                target_id=edge.source_id,
                distance=edge.distance,
                speed_limit=edge.speed_limit,
                congestion=edge.congestion,
                is_closed=edge.is_closed,
            )
            self._adj[edge.target_id][edge.source_id] = reverse_edge

    def get_node(self, node_id: NodeId) -> Node:
        """Retrieves a node by ID.

        Raises:
            NodeNotFoundError: If node_id is not registered in graph.
        """
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)
        return self._nodes[node_id]

    def get_edge(self, source_id: NodeId, target_id: NodeId) -> Edge:
        """Retrieves a directed edge by source and target node IDs.

        Raises:
            NodeNotFoundError: If source or target node is missing.
            EdgeNotFoundError: If direct edge does not exist.
        """
        if source_id not in self._nodes:
            raise NodeNotFoundError(source_id)
        if target_id not in self._nodes:
            raise NodeNotFoundError(target_id)

        if target_id not in self._adj[source_id]:
            raise EdgeNotFoundError(source_id, target_id)

        return self._adj[source_id][target_id]

    def has_node(self, node_id: NodeId) -> bool:
        """Returns True if node_id exists in the graph."""
        return node_id in self._nodes

    def has_edge(self, source_id: NodeId, target_id: NodeId) -> bool:
        """Returns True if directed edge from source_id to target_id exists."""
        return source_id in self._adj and target_id in self._adj[source_id]

    def get_neighbors(self, node_id: NodeId) -> Dict[NodeId, Edge]:
        """Returns outgoing adjacent edges mapping target_node_id -> Edge.

        Raises:
            NodeNotFoundError: If node_id is missing from graph.
        """
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)
        return self._adj.get(node_id, {})

    def set_road_closure(
        self, source_id: NodeId, target_id: NodeId, is_closed: bool, bidirectional: bool = False
    ) -> None:
        """Dynamically marks a road segment as closed or open.

        Args:
            source_id: Origin node ID.
            target_id: Destination node ID.
            is_closed: Closure flag (True = closed, False = open).
            bidirectional: If True, also updates reverse edge if present.
        """
        edge = self.get_edge(source_id, target_id)
        edge.is_closed = is_closed

        if bidirectional and self.has_edge(target_id, source_id):
            rev_edge = self.get_edge(target_id, source_id)
            rev_edge.is_closed = is_closed

    def set_congestion(
        self, source_id: NodeId, target_id: NodeId, level: float, bidirectional: bool = False
    ) -> None:
        """Dynamically updates congestion level for a road segment.

        Args:
            source_id: Origin node ID.
            target_id: Destination node ID.
            level: Congestion ratio in range [0.0, 1.0].
            bidirectional: If True, also updates reverse edge if present.

        Raises:
            InvalidCostParametersError: If level is outside [0.0, 1.0].
        """
        if not (0.0 <= level <= 1.0):
            raise InvalidCostParametersError(f"Congestion level must be in range [0.0, 1.0], got {level}")

        edge = self.get_edge(source_id, target_id)
        edge.congestion = level

        if bidirectional and self.has_edge(target_id, source_id):
            rev_edge = self.get_edge(target_id, source_id)
            rev_edge.congestion = level

    def update_hospital_capacity(
        self, hospital_id: NodeId, occupied_beds: int, capacity: Optional[int] = None
    ) -> None:
        """Dynamically updates occupancy and capacity metrics for a hospital node.

        Args:
            hospital_id: Hospital node ID.
            occupied_beds: Current count of occupied beds (>= 0).
            capacity: Optional new total bed capacity (>= 0).

        Raises:
            NodeNotFoundError: If hospital_id does not exist.
            InvalidGraphError: If node is not a HOSPITAL or values are invalid.
        """
        node = self.get_node(hospital_id)
        if node.node_type != "HOSPITAL":
            raise InvalidGraphError(f"Node '{hospital_id}' is of type '{node.node_type}', expected 'HOSPITAL'.")

        if occupied_beds < 0:
            raise InvalidGraphError(f"occupied_beds cannot be negative: {occupied_beds}")

        if capacity is not None:
            if capacity < 0:
                raise InvalidGraphError(f"capacity cannot be negative: {capacity}")
            node.capacity = capacity

        node.occupied_beds = occupied_beds

    def get_hospitals(self) -> List[Node]:
        """Returns list of all hospital nodes registered in the graph."""
        return [node for node in self._nodes.values() if node.node_type == "HOSPITAL"]

    def get_stations(self) -> List[Node]:
        """Returns list of all emergency station nodes registered in the graph."""
        return [node for node in self._nodes.values() if node.node_type == "STATION"]

    def max_speed_limit(self) -> float:
        """Finds the maximum speed limit across all active edges in the graph.

        Returns:
            Max speed limit in m/s (defaults to 30.0 if no edges exist).
        """
        max_speed = 0.0
        for neighbors in self._adj.values():
            for edge in neighbors.values():
                if edge.speed_limit > max_speed:
                    max_speed = edge.speed_limit
        return max_speed if max_speed > 0 else 30.0

    def remove_edge(self, source_id: NodeId, target_id: NodeId) -> None:
        """Removes a directed edge from the graph."""
        if self.has_edge(source_id, target_id):
            del self._adj[source_id][target_id]

    def remove_node(self, node_id: NodeId) -> None:
        """Removes a node and all incoming/outgoing connected edges."""
        if node_id not in self._nodes:
            raise NodeNotFoundError(node_id)

        del self._nodes[node_id]
        if node_id in self._adj:
            del self._adj[node_id]

        for source in self._adj:
            if node_id in self._adj[source]:
                del self._adj[source][node_id]

    def clear(self) -> None:
        """Clears all nodes and edges from the graph."""
        self._nodes.clear()
        self._adj.clear()
