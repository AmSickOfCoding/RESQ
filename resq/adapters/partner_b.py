"""
RESQ - Adapter for Partner B's dispatch allocation.

OWNER: Partner D (System Core). The allocation scoring is Layan's work and is
called here unchanged; nothing in allocation.py is edited or reimplemented.

WHAT HER MODULE EXPECTS AND WHAT WE HAVE
----------------------------------------

allocation.py works on two small classes of its own (models.Resource and
models.Incident). Ours are the shared dataclasses. The bridging:

  Resource.resource_id     unit.unit_id
  Resource.resource_type   unit.unit_type.value - must match the incident's
                           required_resource_type exactly, so both sides use
                           the same enum string
  Resource.status          "available" / "busy". Hers is a lowercase string,
                           ours is a UnitStatus enum (agenda items 4 and 5)
  Resource.location        unit.current_node. She compares locations with ==,
                           so node ids work directly
  Resource.capabilities    she tests `incident.incident_type in capabilities`,
                           so this is the set of INCIDENT TYPES a unit can
                           serve - not our Capability enum, which means
                           something different. Table below.
  Resource.workload        an integer she penalises. We hold total_busy_seconds,
                           so it is bucketed - see WORKLOAD_BUCKET_SECONDS.

  Incident.created_at      she stores a real datetime. Our clock is simulated
                           seconds (agenda item 2). We pass a datetime derived
                           from the simulated clock purely to satisfy the shape;
                           allocate_resource never reads it.

TWO THINGS THIS ADAPTER DELIBERATELY DOES NOT DO
------------------------------------------------

1. It never calls dispatch_resource() or release_resource(). Both of those
   mutate the resource and the incident, and in this system only the engine
   changes state. We use allocation.py for the decision and let the engine
   apply it, which is what keeps the audit log truthful.

2. It does not alter her score. See the note on TIE-BREAKING below - the router
   is consulted only to choose between candidates she has already scored
   equally, never to override a score she computed.

TIE-BREAKING, AND WHY IT IS HONEST
----------------------------------

calculate_resource_score awards +50 when the unit is already standing on the
incident's node and otherwise judges only workload. It never measures travel
time, so in a city where units are rarely on top of an incident, most eligible
units tie on the same score and allocate_resource returns whichever happens to
come first in the list.

CLAUDE.md section 6.6 flags exactly this risk. Rather than quietly adding
distance into her formula - which would be rewriting her graded work and
misreporting it as hers - the adapter keeps her score as the primary key and
breaks ties on travel time from Partner C's router. A unit she scores higher
always wins. The rationale says which of the two decided it, so the demo can
show the difference rather than hide it.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from typing import List, Optional

# PR #5 moved Partner B's module from the repository root into src/engine/, so
# `import allocation` no longer resolves. Her files import each other by bare
# name (dispatch.py does `from models import ...`), which means the folder has
# to be ON the path - importing it as `src.engine.allocation` would break her
# module's own internal imports.
#
# pyproject's pythonpath covers pytest, but not `python main.py` or the UI, so
# the folder is added here as well. Kept next to the import that needs it, and
# deliberately not in her code: relocating a teammate's module is not a reason
# to edit it.
_PARTNER_B_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src", "engine",
)
if os.path.isdir(_PARTNER_B_DIR) and _PARTNER_B_DIR not in sys.path:
    sys.path.insert(0, _PARTNER_B_DIR)

import allocation as b_allocation
import models as b_models

from ..models import Incident, IncidentType, ResponseUnit, UnitStatus, UnitType
from ..results import Candidate, DispatchDecision, ErrorCode

# Which incident types each kind of unit is equipped to answer. This is the set
# her scorer checks against; our Capability enum is a different concept and is
# not interchangeable with it.
UNIT_CAPABILITIES = {
    UnitType.AMBULANCE: {IncidentType.MEDICAL.value, IncidentType.ACCIDENT.value},
    UnitType.FIRE_TRUCK: {IncidentType.FIRE.value, IncidentType.ACCIDENT.value},
    UnitType.RESCUE_VAN: {IncidentType.RESCUE.value, IncidentType.ACCIDENT.value},
    UnitType.HAZMAT_TEAM: {IncidentType.HAZMAT.value},
}

# Her workload is a small integer. Ours is accumulated busy seconds. Ten
# simulated minutes of work counts as one unit of workload, which puts a normal
# run inside the 0-4 range her formula reacts to.
WORKLOAD_BUCKET_SECONDS = 600.0

# Arbitrary but fixed origin for the datetime her Incident wants. Fixed, not
# datetime.now(), because the run has to reproduce exactly.
_EPOCH = datetime(2026, 1, 1)


def to_resource(unit: ResponseUnit) -> "b_models.Resource":
    """Our ResponseUnit -> her Resource."""
    return b_models.Resource(
        resource_id=unit.unit_id,
        resource_type=unit.unit_type.value,
        status="available" if unit.status == UnitStatus.AVAILABLE else "busy",
        location=unit.current_node,
        capabilities=set(UNIT_CAPABILITIES.get(unit.unit_type, set())),
        workload=int(unit.total_busy_seconds // WORKLOAD_BUCKET_SECONDS),
    )


def to_incident(incident: Incident) -> "b_models.Incident":
    """Our Incident -> her Incident."""
    return b_models.Incident(
        incident_id=incident.incident_id,
        location=incident.node_id,
        priority=incident.severity_score,
        required_resource_type=incident.required_unit.value,
        incident_type=incident.incident_type.value,
        created_at=_EPOCH + timedelta(seconds=incident.reported_at),
    )


class AllocationDispatcher:
    """
    Implements the Dispatcher Protocol using Partner B's allocation module.

    Returns a DispatchDecision. Never mutates anything.
    """

    name = "Allocation scoring (Partner B)"

    def select_unit(self, incident: Incident, world, router,
                    now: float) -> DispatchDecision:
        # Sorted so the candidate list is stable between runs; her scorer walks
        # the list in order and determinism is a hard requirement for us.
        units = sorted(world.units.values(), key=lambda u: u.unit_id)
        if not units:
            return DispatchDecision(
                unit_id=None, error=ErrorCode.NO_UNIT_AVAILABLE,
                rationale="There are no response units in this city at all.")

        b_incident = to_incident(incident)
        scored = []
        considered: List[Candidate] = []

        for unit in units:
            resource = to_resource(unit)
            score = b_allocation.calculate_resource_score(b_incident, resource)

            if score < 0:
                considered.append(Candidate(
                    option_id=unit.unit_id, score=float(score),
                    reason=self._rejection_reason(unit, incident, resource)))
                continue

            # Travel time is used for tie-breaking only - never to change her
            # score. None means the router could not reach the incident.
            travel = router.travel_seconds(unit.current_node, incident.node_id,
                                           world, now)
            if travel is None:
                considered.append(Candidate(
                    option_id=unit.unit_id, score=float(score),
                    reason="eligible, but no open route to the incident"))
                continue

            scored.append((score, travel, unit))

        if not scored:
            error = (ErrorCode.NO_UNIT_AVAILABLE
                     if not any(u.status == UnitStatus.AVAILABLE for u in units)
                     else ErrorCode.NO_SUITABLE_UNIT)
            return DispatchDecision(
                unit_id=None, error=error, considered=considered,
                rationale=(f"No unit could take {incident.incident_id}: "
                           f"{len(considered)} rejected, "
                           f"{self._summarise(considered)}."))

        # Her score is the primary key; travel time only separates equals.
        best_score = max(entry[0] for entry in scored)
        tied = [entry for entry in scored if entry[0] == best_score]
        tied.sort(key=lambda entry: (entry[1], entry[2].unit_id))
        chosen_score, chosen_travel, chosen = tied[0]

        for score, travel, unit in sorted(scored, key=lambda e: (-e[0], e[1])):
            if unit.unit_id == chosen.unit_id:
                continue
            if score < best_score:
                reason = (f"scored {score} against {best_score} "
                          f"(workload {to_resource(unit).workload})")
            else:
                reason = (f"tied on {score} but {travel:.0f}s away versus "
                          f"{chosen_travel:.0f}s")
            considered.append(Candidate(option_id=unit.unit_id,
                                        score=float(score), reason=reason))

        return DispatchDecision(
            unit_id=chosen.unit_id,
            score=float(chosen_score),
            considered=considered,
            rationale=self._rationale(chosen, chosen_score, chosen_travel,
                                      tied, b_incident),
        )

    # ------------------------------------------------------------------

    def _rationale(self, chosen, score, travel, tied, b_incident) -> str:
        """One sentence a non-programmer can read, naming what actually
        decided it - her score, or the tie-break."""
        reasons = b_allocation.get_allocation_reason(b_incident,
                                                     to_resource(chosen))
        detail = "; ".join(reasons)
        if len(tied) > 1:
            decided = (f"Tied on allocation score {score} with "
                       f"{len(tied) - 1} other unit(s); "
                       f"{chosen.unit_id} chosen as the closest at {travel:.0f}s")
        else:
            decided = (f"{chosen.unit_id} had the highest allocation score "
                       f"({score}), {travel:.0f}s away")
        return f"{decided}. {detail}."

    def _rejection_reason(self, unit: ResponseUnit, incident: Incident,
                          resource) -> str:
        """Her scorer returns a bare -1 for three different reasons. Say which."""
        if resource.status != "available":
            return f"not available ({unit.status.value})"
        if resource.resource_type != incident.required_unit.value:
            return (f"wrong type - {resource.resource_type}, "
                    f"incident needs {incident.required_unit.value}")
        if incident.incident_type.value not in resource.capabilities:
            return (f"cannot handle {incident.incident_type.value} "
                    f"(handles {', '.join(sorted(resource.capabilities)) or 'nothing'})")
        return "rejected by the allocation scorer"

    def _summarise(self, considered: List[Candidate]) -> str:
        busy = sum(1 for c in considered if "not available" in c.reason)
        wrong = sum(1 for c in considered if "wrong type" in c.reason)
        parts = []
        if busy:
            parts.append(f"{busy} busy")
        if wrong:
            parts.append(f"{wrong} of the wrong type")
        return ", ".join(parts) or "none eligible"
