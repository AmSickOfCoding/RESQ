"""Custom exception classes for the RESQ routing module."""

from typing import Any


class RoutingError(Exception):
    """Base class for all exceptions in the RESQ routing module."""
    pass


class NodeNotFoundError(RoutingError):
    """Raised when a requested node does not exist in the graph."""

    def __init__(self, node_id: Any) -> None:
        self.node_id = node_id
        super().__init__(f"Node '{node_id}' was not found in the graph.")


class EdgeNotFoundError(RoutingError):
    """Raised when a requested edge does not exist in the graph."""

    def __init__(self, source_id: Any, target_id: Any) -> None:
        self.source_id = source_id
        self.target_id = target_id
        super().__init__(f"Edge from '{source_id}' to '{target_id}' was not found in the graph.")


class DuplicateNodeError(RoutingError):
    """Raised when attempting to add a node with an ID that already exists."""

    def __init__(self, node_id: Any) -> None:
        self.node_id = node_id
        super().__init__(f"Node '{node_id}' already exists in the graph.")


class PathNotFoundError(RoutingError):
    """Raised when no valid path exists between source and target nodes."""

    def __init__(self, source_id: Any, target_id: Any, message: str = "") -> None:
        self.source_id = source_id
        self.target_id = target_id
        msg = message or f"No valid path found between node '{source_id}' and node '{target_id}'."
        super().__init__(msg)


class NoAvailableHospitalError(RoutingError):
    """Raised when no reachable or capacity-available hospital is found."""

    def __init__(self, incident_id: Any, message: str = "") -> None:
        self.incident_id = incident_id
        msg = message or f"No reachable or available hospital found for incident at node '{incident_id}'."
        super().__init__(msg)


class InvalidGraphError(RoutingError):
    """Raised when graph structural or state invariants are violated."""
    pass


class InvalidCostParametersError(RoutingError):
    """Raised when cost or congestion modeling parameters are out of valid bounds."""
    pass
