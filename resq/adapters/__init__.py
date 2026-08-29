"""
RESQ - Integration adapters.

OWNER: Partner D (System Core).

One thin translation layer per teammate. Each adapter implements a Protocol from
resq/interfaces.py, and inside it converts our shared objects into whatever shape
that teammate's module actually expects, calls their code unchanged, and
converts the answer back.

WHY ADAPTERS RATHER THAN ASKING THEM TO CHANGE:

Their modules were written against their own understanding of the contract -
different field names, different units, different types. All of those
differences are recorded in docs/contract_comparison.md and the eleven that need
a team decision are in docs/contract_agenda.md. None of them are resolved here.

Until the team rules, the cost of the mismatch is paid on this side, in these
files, where it is visible and tested. That way their work integrates today
without anyone rewriting anything the night before a deadline, and the eventual
decision changes an adapter rather than four people's code.

RULES EVERY ADAPTER FOLLOWS:

  1. Never mutate the world, an Incident or a ResponseUnit. Read, decide,
     return a result object. The engine applies it.
  2. Never let a teammate's exception escape. Their modules raise on inputs they
     do not recognise; ours must return a result carrying an ErrorCode instead,
     because "no unit free" and "unknown severity value" are ordinary events in
     a simulation, not bugs.
  3. Always fill rationale and considered, including when the underlying module
     provides neither. Explaining the decision is our requirement, not theirs.
"""

from .partner_a import SeverityPrioritizer
from .partner_b import AllocationDispatcher
from .partner_c import AStarRouter, DijkstraRouter

__all__ = [
    "SeverityPrioritizer",
    "AllocationDispatcher",
    "AStarRouter",
    "DijkstraRouter",
]
