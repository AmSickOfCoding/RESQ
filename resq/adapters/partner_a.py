"""
RESQ - Adapter for Partner A's severity scoring.

OWNER: Partner D (System Core). The scoring itself is Huthaifa's work and is
called here unchanged; nothing in severity_scoring/ is edited or reimplemented.

WHAT HIS MODULE EXPECTS AND WHAT WE HAVE
----------------------------------------

severity_scoring works on a plain dict. Our Incident is a dataclass. He changed
the shape of that dict on 29 Aug, so the mapping below is current as of then:

  incident_id        same on both sides.

  severity           he expects an INTEGER 1-5. Our Incident has no
                     reported-severity field at all - that is a gap in MY
                     contract, not a mistake in his module, and it is item 3 on
                     the agenda. Until the team decides, triage_level_int()
                     derives one from incident type and victim count.

  people_affected    our `victims`. Straight rename. He now scores this himself
                     with a logarithmic curve, so the adapter no longer supplies
                     a normalised value for it.

  waiting_time       he works in MINUTES; we record simulation SECONDS. This is
                     agenda item 2. Converted here, at the boundary, so the
                     engine keeps its own unit and his module keeps its own.

  required_unit_type he validates against {AMBULANCE, FIRE, POLICE} - which is
                     C's document's unit list, not our UnitType. Mapped below.
                     We do NOT rename UnitType to match: that enum drives the
                     fleet, all three scenarios, B's type matching, the UI and
                     the tests, and his module is the only consumer that wants
                     different spellings.

  incident_type      the key his INCIDENT_TYPE_MAP is looked up by. Its keys are
                     {MEDICAL, FIRE, POLICE, OTHER} - a DIFFERENT vocabulary
                     from the required_unit_type he validates. Note that
                     "AMBULANCE" passes his validator but is not a key in that
                     map, so the two fields cannot share a value. Hence two
                     separate mappings below rather than one.

His validation raises on anything it does not recognise. Section 5 of our design
rules says expected conditions return a code instead, so every call into his
module is wrapped. A failure never propagates and never strands an incident: it
degrades to a usable score, prefixed DEGRADED in the rationale so it is obvious
in the audit trail. See _score_one for why that fallback is mid-scale rather
than zero - it is the fix for a real starvation bug, not a defensive habit.
"""

from __future__ import annotations

from typing import Dict, List

from severity_scoring import config as a_config
from severity_scoring import scoring as a_scoring
from severity_scoring import validation as a_validation

from ..models import Incident, IncidentType, UnitType

# ---------------------------------------------------------------------------
# BRIDGING TABLES - all of the guesswork lives here and nowhere else
# ---------------------------------------------------------------------------

# --- severity: our incident -> his 1-5 integer scale ----------------------
# Placeholder for the reported-severity field the contract is missing. Crude on
# purpose: it stands in for a FIELD, it is not a second scoring algorithm. The
# real severity ordering is Partner A's job once that field exists.
_BASE_SEVERITY = {
    IncidentType.MEDICAL: 3,
    IncidentType.ACCIDENT: 4,
    IncidentType.FIRE: 4,
    IncidentType.HAZMAT: 5,
    IncidentType.RESCUE: 4,
}

# --- required_unit_type: our UnitType -> his {AMBULANCE, FIRE, POLICE} -----
# His list has no rescue or hazmat category, so both fall to FIRE: in a real
# service both are fire-service functions, and FIRE is the closest thing his
# vocabulary has. Nothing downstream of this depends on the choice - it is only
# read by his validator - but it is a judgement, so it is written down.
_UNIT_TYPE = {
    UnitType.AMBULANCE: "AMBULANCE",
    UnitType.FIRE_TRUCK: "FIRE",
    UnitType.RESCUE_VAN: "FIRE",
    UnitType.HAZMAT_TEAM: "FIRE",
}

# --- incident_type: our IncidentType -> his INCIDENT_TYPE_MAP keys ---------
# Deliberately separate from _UNIT_TYPE above: his two fields use different
# vocabularies and "AMBULANCE" is not a valid key here.
_INCIDENT_TYPE = {
    IncidentType.MEDICAL: "MEDICAL",
    IncidentType.ACCIDENT: "MEDICAL",   # casualties are the priority in a collision
    IncidentType.FIRE: "FIRE",
    IncidentType.HAZMAT: "FIRE",        # fire-service function
    IncidentType.RESCUE: "OTHER",
}

SECONDS_PER_MINUTE = 60.0

# Where an incident lands when the scoring module cannot give us a usable
# number. Mid-scale on purpose: a failure must not decide the incident's fate
# in either direction. Zero would bury it behind everything (see _score_one),
# and 100 would let a broken input jump the queue ahead of real emergencies.
NEUTRAL_SCORE = 50.0


def triage_level_int(incident: Incident) -> int:
    """
    Derive the 1-5 reported severity his module now expects.

    Replace this with a real field read once the contract has one - see
    docs/contract_agenda.md item 3.
    """
    base = _BASE_SEVERITY.get(incident.incident_type, 3)
    if incident.victims >= 5:
        return min(5, base + 2)
    if incident.victims >= 3:
        return min(5, base + 1)
    return base


def to_scoring_input(incident: Incident, now: float) -> Dict:
    """Our Incident -> the dict severity_scoring expects. Units converted here."""
    return {
        "incident_id": incident.incident_id,
        "severity": triage_level_int(incident),
        "people_affected": int(incident.victims),
        # seconds -> minutes, because his module documents minutes
        "waiting_time": max(0.0, (now - incident.reported_at) / SECONDS_PER_MINUTE),
        "required_unit_type": _UNIT_TYPE.get(incident.required_unit, "AMBULANCE"),
        "incident_type": _INCIDENT_TYPE.get(incident.incident_type, "OTHER"),
    }


class SeverityPrioritizer:
    """
    Implements the Prioritizer Protocol using Partner A's scoring module.

    Sets severity_score, priority_rank and severity_rationale on each incident -
    the only three fields A is permitted to write - and returns the list sorted
    most urgent first.
    """

    name = "Severity scoring (Partner A)"

    def prioritize(self, incidents: List[Incident], world, now: float) -> List[Incident]:
        for incident in incidents:
            score, rationale = self._score_one(incident, now)
            incident.severity_score = score
            incident.severity_rationale = rationale

        # Highest score first. Ties break on report time so the older call wins,
        # which keeps ordering deterministic - a hard requirement for the
        # before/after metrics comparison to mean anything.
        ordered = sorted(
            incidents, key=lambda i: (-i.severity_score, i.reported_at, i.incident_id)
        )
        for rank, incident in enumerate(ordered, start=1):
            incident.priority_rank = rank
        return ordered

    # ------------------------------------------------------------------

    def _score_one(self, incident: Incident, now: float):
        """
        Run A's pipeline for one incident. Never raises, and never returns a
        score that would strand the incident.
        """
        payload = to_scoring_input(incident, now)

        try:
            a_validation.validate_incident(payload)
        except a_validation.SeverityValidationError as exc:
            # Rule 2: his module raises, ours must not. The input is unusable,
            # so there is no real score to keep - but the incident still has to
            # be dispatchable, so it competes from the middle of the scale.
            return NEUTRAL_SCORE, (
                f"DEGRADED - scored neutrally ({NEUTRAL_SCORE:.1f}/100) because "
                f"the severity module rejected the input: {exc}")

        # --- the arithmetic, using his functions and his weights -----------
        try:
            contributions = self._contributions(payload, incident)
            normalised = a_scoring.calculate_final_score(contributions)
            score = round(a_scoring.convert_score_to_100(normalised), 2)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            # No usable number at all. Neutral, so it still gets a unit.
            return NEUTRAL_SCORE, (
                f"DEGRADED - scored neutrally ({NEUTRAL_SCORE:.1f}/100) because "
                f"the severity module raised {type(exc).__name__} while scoring: "
                f"{exc}")

        # --- the category, separately, so a label bug cannot cost the score --
        try:
            category = a_scoring.categorize_score(score)
        except (TypeError, ValueError) as exc:
            category = "Uncategorised"
            waited_minutes = payload["waiting_time"]
            return score, (
                f"DEGRADED - {score:.1f}/100 kept, but the severity module "
                f"raised {type(exc).__name__} categorising it: {exc}. "
                f"Ordering is unaffected; only the label is missing. "
                f"severity {payload['severity']}/5 "
                f"{incident.incident_type.value.lower()}, {incident.victims} "
                f"affected, waiting {waited_minutes:.1f} min.")

        waited_minutes = payload["waiting_time"]
        rationale = (
            f"{category} ({score:.1f}/100): "
            f"severity {payload['severity']}/5 {incident.incident_type.value.lower()}, "
            f"{incident.victims} affected, waiting {waited_minutes:.1f} min. "
            f"Weights - severity {contributions['severity']:.3f}, "
            f"people {contributions['people']:.3f}, "
            f"waiting {contributions['waiting']:.3f}, "
            f"type {contributions['type']:.3f}."
        )
        return float(score), rationale

    def _contributions(self, payload: Dict, incident: Incident) -> Dict[str, float]:
        """
        Build the four weighted factors using A's own functions and A's own weights.
        """
        severity = a_scoring.calculate_incident_severity_contribution(
            payload["severity"]
        )

        waiting_normal = a_scoring.normalize_waiting_time(payload["waiting_time"])
        waiting = a_scoring.calculate_weighted_contribution(
            waiting_normal, a_config.WEIGHT_WAITING_TIME
        )

        people = a_scoring.calculate_people_affected_contribution(
            payload["people_affected"]
        )

        type_factor = a_scoring.calculate_incident_type_contribution(
            payload["incident_type"]
        )

        return {
            "severity": severity,
            "people": people,
            "waiting": waiting,
            "type": type_factor,
        }
