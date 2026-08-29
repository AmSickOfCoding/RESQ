"""
RESQ - Naive stub implementations.

OWNER: Partner D, but ONLY until A, B and C deliver.

These exist so the whole pipeline runs from day one. They are intentionally
poor. Each one carries a TODO naming the owner who replaces it. Do not improve
these stubs - improving them is the other members' graded work.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from ..models import Capability, Incident, Route
from ..results import (
    Candidate,
    DestinationDecision,
    DispatchDecision,
    ErrorCode,
    RouteResult,
)
from ..world import World


# ---------------------------------------------------------------------------
# PARTNER A's SLOT
# ---------------------------------------------------------------------------


class FifoPrioritizer:
    """
    TODO(Partner A): replace with real severity scoring.

    This stub is first-come-first-served. It ignores severity entirely, which
    means a cardiac arrest reported at t=100 waits behind a fender bender
    reported at t=90. That is exactly the behaviour your scoring must beat, and
    it is a useful baseline to compare against in the metrics report.
    """

    name = "FIFO (stub)"

    def prioritize(self, incidents: List[Incident], world: World,
                   now: float) -> List[Incident]:
        ordered = sorted(incidents, key=lambda i: i.reported_at)
        for rank, incident in enumerate(ordered, start=1):
            incident.severity_score = 0.0
            incident.priority_rank = rank
            incident.severity_rationale = (
                f"Stub ordering: position {rank} by report time, severity ignored."
            )
        return ordered


# ---------------------------------------------------------------------------
# PARTNER B's SLOT
# ---------------------------------------------------------------------------


class FirstFreeDispatcher:
    """
    TODO(Partner B): replace with multi-factor unit selection.

    This stub takes the first idle unit of the right type in dictionary order.
    No travel time, no capability weighting, no coverage protection.
    """

    name = "First-free (stub)"

    def select_unit(self, incident: Incident, world: World, router,
                    now: float) -> DispatchDecision:
        candidates = world.free_units(incident.required_unit)

        if not candidates:
            return DispatchDecision(
                unit_id=None,
                error=ErrorCode.NO_UNIT_AVAILABLE,
                rationale=(
                    f"No idle {incident.required_unit.value} anywhere in the city."
                ),
            )

        considered = [
            Candidate(option_id=u.unit_id, score=0.0,
                      reason="not evaluated by stub")
            for u in candidates[1:]
        ]
        chosen = candidates[0]
        return DispatchDecision(
            unit_id=chosen.unit_id,
            score=0.0,
            rationale=(
                f"Stub picked {chosen.unit_id} because it was the first free "
                f"{incident.required_unit.value} in the list."
            ),
            considered=considered,
        )


# ---------------------------------------------------------------------------
# PARTNER C's SLOT
# ---------------------------------------------------------------------------


class BfsRouter:
    """
    TODO(Partner C): replace with Dijkstra or A*, plus alternatives and
    mid-route recomputation.

    This stub finds the path with the FEWEST HOPS, not the fastest one. It skips
    closed roads (so the simulation does not break) but it completely ignores
    traffic multipliers, so a gridlocked two-hop road beats a clear four-hop
    detour. That is the weakness your version fixes.
    """

    name = "BFS hop-count (stub)"

    def _bfs(self, start: str, goal: str, world: World) -> Optional[List[str]]:
        if start == goal:
            return [start]
        seen = {start}
        queue = deque([[start]])
        while queue:
            path = queue.popleft()
            for nxt in world.neighbours(path[-1]):
                if nxt in seen:
                    continue
                if nxt == goal:
                    return path + [nxt]
                seen.add(nxt)
                queue.append(path + [nxt])
        return None

    def _cost(self, path: List[str], world: World) -> float:
        total = 0.0
        for i in range(len(path) - 1):
            edge = world.edge_between(path[i], path[i + 1])
            total += edge.cost_seconds if edge else float("inf")
        return total

    def find_route(self, from_node: str, to_node: str, world: World,
                   now: float = 0.0) -> RouteResult:
        path = self._bfs(from_node, to_node, world)
        if path is None:
            return RouteResult(
                route=None,
                error=ErrorCode.NO_ROUTE,
                rationale=f"No open road connects {from_node} to {to_node}.",
            )
        return RouteResult(
            route=Route(
                node_path=path,
                total_seconds=self._cost(path, world),
                computed_at=now,
                notes="Stub route: fewest hops, traffic ignored.",
            ),
            rationale=f"Fewest-hop path with {len(path) - 1} segments.",
        )

    def travel_seconds(self, from_node: str, to_node: str, world: World,
                       now: float = 0.0) -> Optional[float]:
        result = self.find_route(from_node, to_node, world, now)
        return result.route.total_seconds if result.ok else None

    def best_destination(self, from_node: str, world: World,
                         required: Optional[Set[Capability]] = None,
                         now: float = 0.0) -> DestinationDecision:
        considered: List[Candidate] = []
        best: Optional[Tuple[float, str, Route]] = None

        for hospital in world.hospitals.values():
            if not hospital.has_space:
                considered.append(Candidate(hospital.node_id, float("inf"),
                                            "at full capacity"))
                continue
            if required and not required.issubset(hospital.capabilities):
                missing = ", ".join(c.value for c in required - hospital.capabilities)
                considered.append(Candidate(hospital.node_id, float("inf"),
                                            f"missing capability: {missing}"))
                continue

            result = self.find_route(from_node, hospital.node_id, world, now)
            if not result.ok:
                considered.append(Candidate(hospital.node_id, float("inf"),
                                            "unreachable"))
                continue

            seconds = result.route.total_seconds
            considered.append(Candidate(hospital.node_id, seconds,
                                        f"{seconds:.0f}s away, "
                                        f"{hospital.free_beds} beds free"))
            if best is None or seconds < best[0]:
                best = (seconds, hospital.node_id, result.route)

        if best is None:
            return DestinationDecision(
                node_id=None,
                error=ErrorCode.NO_DESTINATION_AVAILABLE,
                rationale="Every hospital is full, unsuitable or unreachable.",
                considered=considered,
            )

        seconds, node_id, route = best
        return DestinationDecision(
            node_id=node_id,
            route=route,
            rationale=(f"Stub picked {world.hospitals[node_id].name}: nearest "
                       f"hospital with free beds ({seconds:.0f}s)."),
            considered=[c for c in considered if c.option_id != node_id],
        )
