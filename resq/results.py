"""
RESQ - Shared result and error shapes.

OWNER: Partner D (System Core).

Every component returns a result object, never a bare value and never None on
failure. The reason is auditability: a failure has to carry an explanation the
same way a success does, otherwise the UI has nothing to show the reviewer.

RULE FOR A, B, C: never raise an exception for an expected condition such as
"no unit free" or "no path exists". Return the matching result with an error
code. Exceptions are for real bugs only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .models import Route


class ErrorCode(str, Enum):
    """The complete list of expected failure conditions. Agreed by all four."""

    NONE = "NONE"
    NO_UNIT_AVAILABLE = "NO_UNIT_AVAILABLE"          # B: nothing free right now
    NO_SUITABLE_UNIT = "NO_SUITABLE_UNIT"            # B: free units exist, none match
    NO_ROUTE = "NO_ROUTE"                            # C: graph is disconnected
    NO_DESTINATION_AVAILABLE = "NO_DESTINATION_AVAILABLE"  # C: every hospital full
    UNIT_UNREACHABLE = "UNIT_UNREACHABLE"            # C: unit cannot get there at all


@dataclass
class Candidate:
    """
    One option that was considered but not necessarily chosen.

    This is what turns "the system picked unit A3" into "the system picked A3
    over A1 and A7 because ...". Populate it. The rubric gives 20 marks for
    decision quality and this is the evidence.
    """

    option_id: str
    score: float
    reason: str = ""


@dataclass
class DispatchDecision:
    """
    Returned by Partner B's select_unit().

    unit_id is None when nothing could be assigned; error explains why.
    rationale is one human sentence, shown directly in the audit screen.
    """

    unit_id: Optional[str]
    rationale: str = ""
    score: float = 0.0
    error: ErrorCode = ErrorCode.NONE
    considered: List[Candidate] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.unit_id is not None and self.error == ErrorCode.NONE


@dataclass
class RouteResult:
    """
    Returned by Partner C's find_route().

    route is None when no path exists; error explains why.
    """

    route: Optional[Route]
    error: ErrorCode = ErrorCode.NONE
    rationale: str = ""

    @property
    def ok(self) -> bool:
        return self.route is not None and self.error == ErrorCode.NONE


@dataclass
class DestinationDecision:
    """
    Returned by Partner C's best_destination().

    node_id is the chosen hospital node. considered shows the ones that were
    rejected and why - this is how we demonstrate the "hospital full" condition.
    """

    node_id: Optional[str]
    route: Optional[Route] = None
    rationale: str = ""
    error: ErrorCode = ErrorCode.NONE
    considered: List[Candidate] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.node_id is not None and self.error == ErrorCode.NONE
