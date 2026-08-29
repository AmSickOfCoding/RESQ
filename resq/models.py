"""
RESQ - Shared data models.

OWNER: Partner D (System Core).

This is the single source of truth for every object that moves between our four
components. Nobody redefines these classes locally. If you need a new field,
ask D to add it here so all four components see the same shape.

Everything is a plain dataclass on purpose: easy to print, easy to persist,
easy to compare in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------


class IncidentType(str, Enum):
    """What kind of emergency this is. Drives which unit types can respond."""

    MEDICAL = "MEDICAL"
    FIRE = "FIRE"
    ACCIDENT = "ACCIDENT"      # traffic collision - may need both medical + fire
    HAZMAT = "HAZMAT"
    RESCUE = "RESCUE"


class IncidentStatus(str, Enum):
    """Lifecycle of an incident. The engine is the ONLY thing that changes this."""

    REPORTED = "REPORTED"        # exists, not yet prioritized
    QUEUED = "QUEUED"            # prioritized, waiting for a free unit
    ASSIGNED = "ASSIGNED"        # a unit has been chosen and is travelling
    ON_SCENE = "ON_SCENE"        # unit arrived, working the incident
    TRANSPORTING = "TRANSPORTING"  # unit is taking a patient to a hospital
    RESOLVED = "RESOLVED"        # finished successfully
    FAILED = "FAILED"            # could not be served (no route / no unit / timeout)


class UnitType(str, Enum):
    """Category of response unit. Must match what an incident requires."""

    AMBULANCE = "AMBULANCE"
    FIRE_TRUCK = "FIRE_TRUCK"
    RESCUE_VAN = "RESCUE_VAN"
    HAZMAT_TEAM = "HAZMAT_TEAM"


class UnitStatus(str, Enum):
    """Lifecycle of a response unit. Only the engine changes this."""

    AVAILABLE = "AVAILABLE"          # idle at a station or a node
    EN_ROUTE = "EN_ROUTE"            # travelling to an incident
    ON_SCENE = "ON_SCENE"            # working at the incident location
    TRANSPORTING = "TRANSPORTING"    # travelling to a hospital
    RETURNING = "RETURNING"          # heading back to its home station
    OUT_OF_SERVICE = "OUT_OF_SERVICE"  # broken down or disabled by failure injection


class NodeKind(str, Enum):
    """What a graph node represents."""

    INTERSECTION = "INTERSECTION"
    STATION = "STATION"
    HOSPITAL = "HOSPITAL"


class Capability(str, Enum):
    """
    Special abilities. Used in two places:
      - a unit may HAVE capabilities
      - an incident or a hospital may REQUIRE / OFFER them
    Partner A and Partner C both read these, so keep the list stable.
    """

    TRAUMA = "TRAUMA"
    BURN = "BURN"
    CARDIAC = "CARDIAC"
    PEDIATRIC = "PEDIATRIC"
    HEAVY_LIFT = "HEAVY_LIFT"
    CHEMICAL = "CHEMICAL"


# ---------------------------------------------------------------------------
# WORLD / MAP OBJECTS
# ---------------------------------------------------------------------------


@dataclass
class Node:
    """
    A single point on the city map.

    node_id is the shared identifier format we agreed on: short uppercase string
    such as "N01", "ST1", "H2". Every component refers to locations by this id
    and never by name or by index.
    """

    node_id: str
    name: str
    kind: NodeKind = NodeKind.INTERSECTION
    x: float = 0.0  # only for drawing the map in the UI, never for routing
    y: float = 0.0


@dataclass
class Edge:
    """
    A road between two nodes. Treated as bidirectional by the world loader,
    which stores one Edge object per direction.

    OWNER OF THE COST FORMULA: Partner C.
    base_seconds is the free-flow travel time. traffic_multiplier is how much
    slower it currently is (1.0 = normal, 2.5 = heavy congestion). is_open is
    flipped by failure injection during the demo.
    """

    from_node: str
    to_node: str
    base_seconds: float
    traffic_multiplier: float = 1.0
    is_open: bool = True

    @property
    def cost_seconds(self) -> float:
        """Current effective travel time. Closed roads are infinitely expensive."""
        if not self.is_open:
            return float("inf")
        return self.base_seconds * self.traffic_multiplier

    @property
    def key(self) -> str:
        """Stable id for logging, e.g. 'N01->N02'."""
        return f"{self.from_node}->{self.to_node}"


@dataclass
class Hospital:
    """
    A destination for patient transport.

    Partner C's best_destination() ranks these. Capacity matters: a full hospital
    must be skipped and the reason recorded, which is one of our three required
    changing conditions.
    """

    node_id: str
    name: str
    capacity: int
    occupied: int = 0
    capabilities: Set[Capability] = field(default_factory=set)

    @property
    def has_space(self) -> bool:
        return self.occupied < self.capacity

    @property
    def free_beds(self) -> int:
        return max(0, self.capacity - self.occupied)


@dataclass
class Station:
    """Home base for response units. Units return here when idle."""

    node_id: str
    name: str


# ---------------------------------------------------------------------------
# ROUTING OBJECTS  (produced by Partner C, consumed by the engine and by B)
# ---------------------------------------------------------------------------


@dataclass
class Route:
    """
    A concrete path through the graph.

    node_path includes both the origin and the destination.
    total_seconds is the sum of edge costs at the moment the route was computed.
    alternatives is optional but strongly recommended: it is what lets the audit
    screen show that we CONSIDERED other options instead of taking the first one.
    """

    node_path: List[str]
    total_seconds: float
    computed_at: float = 0.0           # simulation timestamp when this was built
    alternatives: List[List[str]] = field(default_factory=list)
    notes: str = ""                    # free text from C, shown in the audit view

    @property
    def edge_keys(self) -> List[str]:
        """The edges this route uses, so the engine can invalidate it on closure."""
        return [
            f"{self.node_path[i]}->{self.node_path[i + 1]}"
            for i in range(len(self.node_path) - 1)
        ]

    @property
    def destination(self) -> str:
        return self.node_path[-1]


# ---------------------------------------------------------------------------
# CORE ENTITIES
# ---------------------------------------------------------------------------


@dataclass
class Incident:
    """
    One emergency call.

    FIELDS PARTNER A OWNS: severity_score, priority_rank, severity_rationale.
    A must not modify anything else on this object; the engine controls status
    and the timestamps.
    """

    incident_id: str
    node_id: str
    incident_type: IncidentType
    reported_at: float                       # simulation seconds
    required_unit: UnitType
    required_capabilities: Set[Capability] = field(default_factory=set)
    requires_transport: bool = False         # does a patient need a hospital?
    service_seconds: float = 300.0           # how long the unit works on scene
    victims: int = 1

    # --- filled in by Partner A -------------------------------------------
    severity_score: float = 0.0              # higher = more severe
    priority_rank: Optional[int] = None      # 1 = handled first
    severity_rationale: str = ""             # human-readable "why this score"

    # --- controlled by the engine only ------------------------------------
    status: IncidentStatus = IncidentStatus.REPORTED
    assigned_unit_id: Optional[str] = None
    assigned_at: Optional[float] = None
    arrived_at: Optional[float] = None
    resolved_at: Optional[float] = None
    destination_hospital: Optional[str] = None
    failure_reason: str = ""

    @property
    def response_seconds(self) -> Optional[float]:
        """Time from report to a unit arriving on scene. Our headline metric."""
        if self.arrived_at is None:
            return None
        return self.arrived_at - self.reported_at


@dataclass
class ResponseUnit:
    """
    One dispatchable vehicle/crew.

    FIELDS PARTNER B READS: everything. Partner B must not mutate this object -
    it returns a decision and the engine applies it. That rule is what keeps the
    audit trail honest.
    """

    unit_id: str
    unit_type: UnitType
    home_station: str
    current_node: str
    capabilities: Set[Capability] = field(default_factory=set)
    speed_factor: float = 1.0  # <1.0 is slower than the road's base time

    # --- controlled by the engine only ------------------------------------
    status: UnitStatus = UnitStatus.AVAILABLE
    assigned_incident_id: Optional[str] = None
    route: Optional[Route] = None
    seconds_into_route: float = 0.0
    busy_until: Optional[float] = None   # used while ON_SCENE
    total_busy_seconds: float = 0.0      # for the utilization metric

    @property
    def is_free(self) -> bool:
        return self.status == UnitStatus.AVAILABLE
