"""
RESQ - Component interfaces.

OWNER: Partner D (System Core).

THIS FILE IS THE INTEGRATION CONTRACT. Sections 8 and 7 of the project brief are
graded on it. Each of A, B and C writes ONE class that implements ONE of these
protocols. The engine never imports your module directly - it receives your
object through the constructor, so we can swap a stub for a real implementation
without editing engine code.

RULES FOR ALL THREE:
  1. Do not mutate the World or any Incident/ResponseUnit. Read, decide, return.
     The engine applies the decision. This is what keeps the audit log truthful.
  2. Never raise for an expected condition. Return the result object with an
     ErrorCode (see results.py).
  3. Always fill the `rationale` string and the `considered` list. That text is
     printed directly in the audit screen and is where the 20 marks for
     decision quality come from.
  4. Be deterministic. If you need randomness, take a seeded Random from the
     engine, otherwise our three scenarios will not be reproducible.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, Set

from .models import Capability, Incident, ResponseUnit
from .results import DestinationDecision, DispatchDecision, RouteResult
from .world import World


class Prioritizer(Protocol):
    """
    PARTNER A - Severity scoring, explainable scoring, incident prioritization.

    You decide the ORDER incidents are handled in. You do not choose units and
    you do not choose routes.
    """

    def prioritize(
        self,
        incidents: List[Incident],
        world: World,
        now: float,
    ) -> List[Incident]:
        """
        Score every incident, then return them sorted most-urgent first.

        You are expected to SET on each incident:
          - severity_score      (float, higher = worse)
          - priority_rank       (1 = first)
          - severity_rationale  (one sentence a non-programmer can read)

        These three fields are the only ones you may write to.

        Things worth weighing, so this is not just "severity descending":
        incident type, number of victims, how long it has already waited
        (an old low-severity call must eventually beat a fresh mid-severity
        one, or we get starvation), and whether resources even exist for it.
        """
        ...


class Dispatcher(Protocol):
    """
    PARTNER B - Resource allocation, unit selection, dispatch logic.

    You decide WHICH unit goes. You do not decide the order of incidents and you
    do not compute paths yourself.

    IMPORTANT: to compare units by travel time, call the router you are given -
    never estimate distance yourself. If B measures straight-line distance while
    C measures road time, the demo will contradict itself.
    """

    def select_unit(
        self,
        incident: Incident,
        world: World,
        router: "Router",
        now: float,
    ) -> DispatchDecision:
        """
        Choose the best available unit for this incident, or return a decision
        with unit_id=None plus an ErrorCode explaining why.

        The brief explicitly says nearest-unit-wins is NOT enough. Weigh at
        least: travel time from the router, capability match, unit type match,
        how much coverage the city loses if this unit leaves its area, and
        whether a closer unit should be saved for a likely worse call.

        Fill `considered` with the units you rejected and the reason.
        """
        ...


class Router(Protocol):
    """
    PARTNER C - Dynamic graph modelling, routing, destination optimization.

    You own every question of the form "how do I get from X to Y and how long
    does it take". Both the engine and Partner B call you.
    """

    def find_route(
        self,
        from_node: str,
        to_node: str,
        world: World,
        now: float = 0.0,
    ) -> RouteResult:
        """
        Shortest path by CURRENT travel cost, respecting closed roads and
        traffic multipliers. Return RouteResult(route=None,
        error=ErrorCode.NO_ROUTE) when the graph is disconnected.

        Populate route.alternatives when a second reasonable path exists.
        """
        ...

    def travel_seconds(
        self,
        from_node: str,
        to_node: str,
        world: World,
        now: float = 0.0,
    ) -> Optional[float]:
        """
        Cost only, no path. This is the cheap call Partner B uses inside the
        unit-scoring loop. Return None when unreachable.
        """
        ...

    def best_destination(
        self,
        from_node: str,
        world: World,
        required: Optional[Set[Capability]] = None,
        now: float = 0.0,
    ) -> DestinationDecision:
        """
        Pick the hospital to transport to. Rank by travel time, free capacity
        and capability match - not just nearest.

        When every hospital is full or unreachable, return node_id=None with
        ErrorCode.NO_DESTINATION_AVAILABLE and list what you rejected. That
        rejection list is how we demonstrate the "hospital full" condition in
        the demo.
        """
        ...
