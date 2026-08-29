"""
RESQ - Adapter for Partner A's severity scoring.

OWNER: Partner D (System Core). The scoring itself is Huthaifa's work and is
called here unchanged; nothing in severity_scoring/ is edited or reimplemented.

WHAT HIS MODULE EXPECTS AND WHAT WE HAVE
----------------------------------------

severity_scoring works on a plain dict with five keys. Our Incident is a
dataclass. The gaps, and how each is bridged:

  incident_id        same on both sides.

  incident_severity  he expects "Low"/"Medium"/"High"/"Critical". Our Incident
                     has no reported-severity field at all - that is a gap in
                     MY contract, not a mistake in his module, and it is item 3
                     on the agenda. Until the team decides, this adapter derives
                     a triage level from incident type and victim count. The
                     mapping is right below, in one table, so it is easy to
                     point at and easy to delete once a real field exists.

  people_affected    our `victims`. Straight rename.

  waiting_time       he works in MINUTES; we record simulation SECONDS. This is
                     agenda item 2. Converted here, at the boundary, so the
                     engine keeps its own unit and his module keeps its own.

  incident_type      he has INCIDENT_TYPE_MAP = None, so the type factor is not
                     implemented yet. Rather than skip the factor and quietly
                     compress everyone's score, we supply a normalised value for
                     it and let HIS weight apply. Same for people_affected,
                     whose formula is also still None. Both are marked TBD in
                     his config; when he fills them in, the two blocks below
                     come out.

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

from ..models import Incident, IncidentType

# ---------------------------------------------------------------------------
# BRIDGING TABLES - all of the guesswork lives here and nowhere else
# ---------------------------------------------------------------------------

# Stand-in for the reported-severity field our contract is missing. A baseline
# per incident type, escalated by how many people are involved. Deliberately
# crude: it is a placeholder for a field, not a second scoring algorithm, and
# the real severity ordering is Partner A's job once the field exists.
_BASE_TRIAGE = {
    IncidentType.MEDICAL: "Medium",
    IncidentType.ACCIDENT: "High",
    IncidentType.FIRE: "High",
    IncidentType.HAZMAT: "Critical",
    IncidentType.RESCUE: "High",
}
_ESCALATION = ["Low", "Medium", "High", "Critical"]

# How much of "the worst case" each incident type represents, for the factor
# his INCIDENT_TYPE_MAP will eventually own. Values are 0..1.
_TYPE_SEVERITY = {
    IncidentType.MEDICAL: 0.55,
    IncidentType.ACCIDENT: 0.70,
    IncidentType.FIRE: 0.85,
    IncidentType.HAZMAT: 1.00,
    IncidentType.RESCUE: 0.75,
}

# Victim count treated as "this many is as bad as it gets", for the factor his
# PEOPLE_AFFECTED_FORMULA will eventually own.
_VICTIMS_REFERENCE = 10

SECONDS_PER_MINUTE = 60.0

# Where an incident lands when the scoring module cannot give us a usable
# number. Mid-scale on purpose: a failure must not decide the incident's fate
# in either direction. Zero would bury it behind everything (see _score_one),
# and 100 would let a broken input jump the queue ahead of real emergencies.
NEUTRAL_SCORE = 50.0


def _escalate(level: str, steps: int) -> str:
    """Move a triage level up the scale, stopping at Critical."""
    index = min(len(_ESCALATION) - 1, _ESCALATION.index(level) + steps)
    return _ESCALATION[index]


def triage_level(incident: Incident) -> str:
    """
    Derive the reported-severity string Partner A's module needs.

    Replace this with a real field read once the contract has one - see
    docs/contract_agenda.md item 3.
    """
    base = _BASE_TRIAGE.get(incident.incident_type, "Medium")
    if incident.victims >= 5:
        return _escalate(base, 2)
    if incident.victims >= 3:
        return _escalate(base, 1)
    return base


def to_scoring_input(incident: Incident, now: float) -> Dict:
    """Our Incident -> the dict severity_scoring expects. Units converted here."""
    return {
        "incident_id": incident.incident_id,
        "incident_severity": triage_level(incident),
        "people_affected": int(incident.victims),
        # seconds -> minutes, because his module documents minutes
        "waiting_time": max(0.0, (now - incident.reported_at) / SECONDS_PER_MINUTE),
        "incident_type": incident.incident_type.value,
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

        WHY THE FALLBACK IS NEUTRAL AND NOT ZERO
        ----------------------------------------

        An earlier version returned 0.0 when the scoring module raised. That
        looked safe - the tick continued, the failure was written down - but it
        was not, and it produced a real bug worth remembering.

        Waiting time is one of the scored factors, and it is capped at ten
        minutes. So an incident whose score happens to trip a bug in the module
        keeps tripping it on every subsequent tick, because after ten minutes
        its inputs stop changing. Scored 0.0 every time, it sits permanently at
        the bottom of the queue while every new arrival overtakes it. The factor
        that exists to prevent starvation caused permanent starvation.

        A neutral score cannot do that. The incident competes on equal terms,
        gets dispatched, and the failure is still recorded in the rationale for
        anyone reading the audit trail.

        The two failure modes are also separated below. Almost always it is the
        CATEGORY lookup that fails while the arithmetic is fine - in that case
        the real number is kept and only the label is missing, so ordering stays
        correct. Falling back to neutral is the last resort, for when the
        arithmetic itself could not be completed.
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
                f"{payload['incident_severity'].lower()} "
                f"{incident.incident_type.value.lower()}, {incident.victims} "
                f"affected, waiting {waited_minutes:.1f} min.")

        waited_minutes = payload["waiting_time"]
        rationale = (
            f"{category} ({score:.1f}/100): "
            f"{payload['incident_severity'].lower()} {incident.incident_type.value.lower()}, "
            f"{incident.victims} affected, waiting {waited_minutes:.1f} min. "
            f"Weights - severity {contributions['severity']:.3f}, "
            f"people {contributions['people']:.3f}, "
            f"waiting {contributions['waiting']:.3f}, "
            f"type {contributions['type']:.3f}."
        )
        return float(score), rationale

    def _contributions(self, payload: Dict, incident: Incident) -> Dict[str, float]:
        """
        Build the four weighted factors using A's own functions and A's own
        weights. Two of the four have no formula in his config yet, so the
        normalised value is supplied here and his weight is applied to it.
        """
        severity = a_scoring.calculate_incident_severity_contribution(
            payload["incident_severity"]
        )

        waiting_normal = a_scoring.normalize_waiting_time(payload["waiting_time"])
        waiting = a_scoring.calculate_weighted_contribution(
            waiting_normal, a_config.WEIGHT_WAITING_TIME
        )

        # --- TBD in his config: PEOPLE_AFFECTED_FORMULA is None -----------
        people_normal = min(payload["people_affected"] / _VICTIMS_REFERENCE, 1.0)
        people = a_scoring.calculate_weighted_contribution(
            people_normal, a_config.WEIGHT_PEOPLE_AFFECTED
        )

        # --- TBD in his config: INCIDENT_TYPE_MAP is None -----------------
        type_normal = _TYPE_SEVERITY.get(incident.incident_type, 0.5)
        type_factor = a_scoring.calculate_weighted_contribution(
            type_normal, a_config.WEIGHT_INCIDENT_TYPE
        )

        return {
            "severity": severity,
            "people": people,
            "waiting": waiting,
            "type": type_factor,
        }
