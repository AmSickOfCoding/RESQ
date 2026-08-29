"""Dynamic traversal cost and congestion calculations for RESQ routing engine."""

import math
from typing import Literal

from src.routing.exceptions import InvalidCostParametersError
from src.routing.graph import Edge

PriorityTier = Literal["STANDARD", "NORMAL", "CRITICAL", "HIGH"]


def calculate_traversal_time(
    edge: Edge,
    priority_tier: str = "STANDARD",
    siren_multiplier: float = 1.25,
) -> float:
    """Calculates dynamic travel time in seconds over a given road edge.

    Base traversal time formula:
        travel_time = distance / (speed_limit * (1.0 - congestion) * (siren_multiplier if CRITICAL))

    Args:
        edge: Edge instance containing distance, speed_limit, congestion, and closure status.
        priority_tier: Priority classification ("STANDARD", "CRITICAL", etc.).
        siren_multiplier: Right-of-way speed multiplier for emergency response (default 1.25).

    Returns:
        Traversal time in seconds, or float('inf') if road is closed or in total gridlock.

    Raises:
        InvalidCostParametersError: If siren_multiplier is <= 0.
    """
    if siren_multiplier <= 0:
        raise InvalidCostParametersError(
            f"siren_multiplier must be strictly positive, got: {siren_multiplier}"
        )

    if edge.is_closed:
        return math.inf

    congestion = max(0.0, min(1.0, edge.congestion))
    speed_factor = 1.0 - congestion

    # Total gridlock threshold
    if speed_factor <= 1e-6:
        return math.inf

    effective_speed = edge.speed_limit * speed_factor

    if priority_tier.upper() in {"CRITICAL", "HIGH"}:
        effective_speed *= siren_multiplier

    return edge.distance / effective_speed
