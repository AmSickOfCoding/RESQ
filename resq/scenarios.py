"""
RESQ - Scenarios and metrics.

OWNER: Partner D (System Core).

Section 6 of the brief requires three simulation modes. Each builder returns a
fresh world plus the incident timeline, so runs are reproducible and comparable.

The metrics function at the bottom is what lets us prove that A's scoring and
B's dispatch logic actually beat the naive stubs. Run the same scenario twice,
once with stubs and once with real logic, and compare the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .models import Capability, Incident, IncidentStatus, IncidentType, UnitType
from .world import World, build_sample_city


@dataclass
class Scenario:
    """A named, reproducible run configuration."""

    name: str
    description: str
    world: World
    incidents: List[Incident]
    # actions applied at a given simulation time: (time, function(engine))
    events: List[Tuple[float, Callable]]


def _incident(iid: str, node: str, itype: IncidentType, at: float,
              unit: UnitType, victims: int = 1, transport: bool = False,
              service: float = 300.0, caps=None) -> Incident:
    """Small helper so the scenario lists stay readable."""
    return Incident(
        incident_id=iid,
        node_id=node,
        incident_type=itype,
        reported_at=at,
        required_unit=unit,
        victims=victims,
        requires_transport=transport,
        service_seconds=service,
        required_capabilities=set(caps or []),
    )


# ---------------------------------------------------------------------------
# MODE 1 - NORMAL OPERATIONS
# ---------------------------------------------------------------------------


def normal_operations() -> Scenario:
    """Calls arrive slowly, resources comfortably exceed demand. This is the
    baseline: response times here should be low and nothing should queue."""
    return Scenario(
        name="Normal Operations",
        description="Low call volume, full fleet, no disruptions.",
        world=build_sample_city(),
        incidents=[
            _incident("INC-01", "N03", IncidentType.MEDICAL, 60,
                      UnitType.AMBULANCE, transport=True,
                      caps=[Capability.CARDIAC]),
            _incident("INC-02", "N11", IncidentType.FIRE, 900,
                      UnitType.FIRE_TRUCK, service=900),
            _incident("INC-03", "N06", IncidentType.MEDICAL, 1800,
                      UnitType.AMBULANCE, transport=True),
            _incident("INC-04", "N12", IncidentType.ACCIDENT, 2700,
                      UnitType.AMBULANCE, victims=2, transport=True,
                      caps=[Capability.TRAUMA]),
        ],
        events=[],
    )


# ---------------------------------------------------------------------------
# MODE 2 - HIGH DEMAND
# ---------------------------------------------------------------------------


def high_demand() -> Scenario:
    """
    More simultaneous calls than we have units. This is where Partner A's
    prioritization earns its marks: with FIFO stubs, severe calls will visibly
    wait behind trivial ones.
    """
    incidents = [
        _incident("RUSH-01", "N01", IncidentType.MEDICAL, 30,
                  UnitType.AMBULANCE, transport=True),
        _incident("RUSH-02", "N04", IncidentType.MEDICAL, 45,
                  UnitType.AMBULANCE, transport=True, caps=[Capability.TRAUMA]),
        _incident("RUSH-03", "N09", IncidentType.MEDICAL, 60,
                  UnitType.AMBULANCE, victims=3, transport=True),
        _incident("RUSH-04", "N12", IncidentType.MEDICAL, 90,
                  UnitType.AMBULANCE, transport=True),
        _incident("RUSH-05", "N07", IncidentType.FIRE, 120,
                  UnitType.FIRE_TRUCK, service=1200),
        _incident("RUSH-06", "N02", IncidentType.FIRE, 150,
                  UnitType.FIRE_TRUCK, service=900),
        _incident("RUSH-07", "N10", IncidentType.RESCUE, 180,
                  UnitType.RESCUE_VAN, victims=2, service=600),
        _incident("RUSH-08", "N05", IncidentType.MEDICAL, 240,
                  UnitType.AMBULANCE, victims=1, transport=True,
                  caps=[Capability.PEDIATRIC]),
    ]
    return Scenario(
        name="High Demand",
        description="Eight calls in four minutes against a seven-unit fleet.",
        world=build_sample_city(),
        incidents=incidents,
        events=[],
    )


# ---------------------------------------------------------------------------
# MODE 3 - DISRUPTION  (at least two infrastructure failures, per the brief)
# ---------------------------------------------------------------------------


def disruption() -> Scenario:
    """
    Moderate call volume, but the city breaks underneath it:
      1. the N06<->N07 bottleneck closes
      2. heavy congestion on the northern row
      3. the larger hospital fills up
      4. an ambulance goes out of service mid-call
    """
    events: List[Tuple[float, Callable]] = [
        (300.0, lambda e: e.inject_close_road("N06", "N07")),
        (600.0, lambda e: e.inject_traffic("N09", "N10", 3.0)),
        (900.0, lambda e: e.inject_fill_hospital("H1")),
        (1200.0, lambda e: e.inject_disable_unit("A2")),
    ]
    return Scenario(
        name="Disruption",
        description="Road closure, congestion, hospital saturation, unit loss.",
        world=build_sample_city(),
        incidents=[
            _incident("DIS-01", "N08", IncidentType.MEDICAL, 60,
                      UnitType.AMBULANCE, transport=True),
            _incident("DIS-02", "N05", IncidentType.ACCIDENT, 420,
                      UnitType.AMBULANCE, victims=2, transport=True,
                      caps=[Capability.TRAUMA]),
            _incident("DIS-03", "N11", IncidentType.FIRE, 660,
                      UnitType.FIRE_TRUCK, service=900),
            _incident("DIS-04", "N02", IncidentType.MEDICAL, 1020,
                      UnitType.AMBULANCE, transport=True),
            _incident("DIS-05", "N12", IncidentType.MEDICAL, 1260,
                      UnitType.AMBULANCE, victims=2, transport=True),
        ],
        events=events,
    )


ALL_SCENARIOS: Dict[str, Callable[[], Scenario]] = {
    "normal": normal_operations,
    "rush": high_demand,
    "disruption": disruption,
}


# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------


@dataclass
class Metrics:
    """Outcome summary for one run. Comparable across configurations."""

    scenario: str
    total_incidents: int
    resolved: int
    failed: int
    avg_response_seconds: Optional[float]
    worst_response_seconds: Optional[float]
    avg_total_seconds: Optional[float]
    unit_utilization: Dict[str, float]
    decisions_logged: int

    def as_text(self) -> str:
        lines = [
            f"Scenario            : {self.scenario}",
            f"Incidents           : {self.total_incidents}",
            f"Resolved / Failed   : {self.resolved} / {self.failed}",
        ]
        if self.avg_response_seconds is not None:
            lines.append(f"Avg response time   : {self.avg_response_seconds:.0f}s")
            lines.append(f"Worst response time : {self.worst_response_seconds:.0f}s")
        if self.avg_total_seconds is not None:
            lines.append(f"Avg time to close   : {self.avg_total_seconds:.0f}s")
        lines.append(f"Decisions logged    : {self.decisions_logged}")
        busiest = sorted(self.unit_utilization.items(),
                         key=lambda kv: kv[1], reverse=True)[:3]
        lines.append("Busiest units       : " +
                     ", ".join(f"{u} {p:.0%}" for u, p in busiest))
        return "\n".join(lines)


def collect_metrics(engine, scenario_name: str) -> Metrics:
    """Read the finished world and produce the comparison numbers."""
    incidents = list(engine.world.incidents.values())
    resolved = [i for i in incidents if i.status == IncidentStatus.RESOLVED]
    failed = [i for i in incidents if i.status == IncidentStatus.FAILED]

    responses = [i.response_seconds for i in incidents
                 if i.response_seconds is not None]
    totals = [i.resolved_at - i.reported_at for i in resolved
              if i.resolved_at is not None]

    elapsed = max(engine.now, 1.0)
    utilization = {
        u.unit_id: min(1.0, u.total_busy_seconds / elapsed)
        for u in engine.world.units.values()
    }

    return Metrics(
        scenario=scenario_name,
        total_incidents=len(incidents),
        resolved=len(resolved),
        failed=len(failed),
        avg_response_seconds=(sum(responses) / len(responses)) if responses else None,
        worst_response_seconds=max(responses) if responses else None,
        avg_total_seconds=(sum(totals) / len(totals)) if totals else None,
        unit_utilization=utilization,
        decisions_logged=engine.audit.count(),
    )
