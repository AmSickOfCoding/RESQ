"""
RESQ - The world state.

OWNER: Partner D (System Core), except where noted.

The World is the single mutable object every component reads. Partner C owns the
ROUTING over this graph, but D owns the container itself so that failure
injection, persistence and the UI all have one place to look.

READ FREELY. WRITE ONLY THROUGH THE ENGINE. If a component mutates the world
directly, the audit log will not match reality and we lose marks on Section 9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .models import (
    Capability,
    Edge,
    Hospital,
    Incident,
    Node,
    NodeKind,
    ResponseUnit,
    Station,
    UnitType,
)


@dataclass
class World:
    """Everything that exists in the simulated city right now."""

    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)          # keyed "A->B"
    adjacency: Dict[str, List[str]] = field(default_factory=dict)  # node -> neighbours
    hospitals: Dict[str, Hospital] = field(default_factory=dict)   # keyed by node_id
    stations: Dict[str, Station] = field(default_factory=dict)     # keyed by node_id
    units: Dict[str, ResponseUnit] = field(default_factory=dict)
    incidents: Dict[str, Incident] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # BUILDING THE MAP
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        self.nodes[node.node_id] = node
        self.adjacency.setdefault(node.node_id, [])

    def add_road(self, a: str, b: str, base_seconds: float) -> None:
        """
        Add a two-way road. We store two Edge objects so that one direction can
        be closed independently of the other (a one-way closure is realistic and
        it makes Partner C's routing work harder, which is the point).
        """
        for src, dst in ((a, b), (b, a)):
            edge = Edge(from_node=src, to_node=dst, base_seconds=base_seconds)
            self.edges[edge.key] = edge
            self.adjacency.setdefault(src, []).append(dst)

    # ------------------------------------------------------------------
    # QUERIES  (Partner C will lean on these)
    # ------------------------------------------------------------------

    def edge_between(self, a: str, b: str) -> Optional[Edge]:
        return self.edges.get(f"{a}->{b}")

    def neighbours(self, node_id: str) -> List[str]:
        """Only neighbours reachable through an OPEN road."""
        out = []
        for other in self.adjacency.get(node_id, []):
            edge = self.edge_between(node_id, other)
            if edge is not None and edge.is_open:
                out.append(other)
        return out

    def free_units(self, unit_type: Optional[UnitType] = None) -> List[ResponseUnit]:
        """All idle units, optionally filtered by type. Used by Partner B."""
        return [
            u
            for u in self.units.values()
            if u.is_free and (unit_type is None or u.unit_type == unit_type)
        ]

    def open_hospitals(self) -> List[Hospital]:
        return [h for h in self.hospitals.values() if h.has_space]

    # ------------------------------------------------------------------
    # FAILURE INJECTION  (called live during the demo)
    # ------------------------------------------------------------------

    def close_road(self, a: str, b: str, both_ways: bool = True) -> List[str]:
        """Close a road. Returns the edge keys that changed, so the engine can
        invalidate any route currently using them."""
        changed = []
        pairs = [(a, b), (b, a)] if both_ways else [(a, b)]
        for src, dst in pairs:
            edge = self.edge_between(src, dst)
            if edge is not None and edge.is_open:
                edge.is_open = False
                changed.append(edge.key)
        return changed

    def open_road(self, a: str, b: str, both_ways: bool = True) -> List[str]:
        changed = []
        pairs = [(a, b), (b, a)] if both_ways else [(a, b)]
        for src, dst in pairs:
            edge = self.edge_between(src, dst)
            if edge is not None and not edge.is_open:
                edge.is_open = True
                changed.append(edge.key)
        return changed

    def set_traffic(self, a: str, b: str, multiplier: float,
                    both_ways: bool = True) -> List[str]:
        """Congestion. 1.0 = free flow, 3.0 = gridlock."""
        changed = []
        pairs = [(a, b), (b, a)] if both_ways else [(a, b)]
        for src, dst in pairs:
            edge = self.edge_between(src, dst)
            if edge is not None:
                edge.traffic_multiplier = multiplier
                changed.append(edge.key)
        return changed

    def fill_hospital(self, node_id: str) -> bool:
        """Mark a hospital as completely full."""
        hospital = self.hospitals.get(node_id)
        if hospital is None:
            return False
        hospital.occupied = hospital.capacity
        return True


# ---------------------------------------------------------------------------
# SAMPLE CITY
# ---------------------------------------------------------------------------


def build_sample_city() -> World:
    """
    A small hand-built city so the team has something to run against on day one.

    Shape: a rough 4x4 grid of intersections with three stations and two
    hospitals hanging off it. Deliberately contains a bottleneck (N06<->N07)
    so that closing one road during the demo forces a visible detour rather
    than a silent one.

    Replace this later with a loader that reads a JSON map file.
    """
    w = World()

    # --- intersections -------------------------------------------------
    grid = [
        ("N01", 0, 0), ("N02", 1, 0), ("N03", 2, 0), ("N04", 3, 0),
        ("N05", 0, 1), ("N06", 1, 1), ("N07", 2, 1), ("N08", 3, 1),
        ("N09", 0, 2), ("N10", 1, 2), ("N11", 2, 2), ("N12", 3, 2),
    ]
    for node_id, x, y in grid:
        w.add_node(Node(node_id=node_id, name=f"Junction {node_id[1:]}", x=x, y=y))

    # --- stations ------------------------------------------------------
    for node_id, name, x, y in [
        ("ST1", "Central Fire Station", 0.5, 0.5),
        ("ST2", "East Ambulance Base", 3.5, 1.0),
        ("ST3", "North Rescue Depot", 1.5, 2.5),
    ]:
        w.add_node(Node(node_id=node_id, name=name, kind=NodeKind.STATION, x=x, y=y))
        w.stations[node_id] = Station(node_id=node_id, name=name)

    # --- hospitals -----------------------------------------------------
    w.add_node(Node("H1", "Al-Madinah General", NodeKind.HOSPITAL, x=2.5, y=-0.5))
    w.hospitals["H1"] = Hospital(
        node_id="H1",
        name="Al-Madinah General",
        capacity=4,
        capabilities={Capability.TRAUMA, Capability.CARDIAC},
    )

    w.add_node(Node("H2", "Northside Clinic", NodeKind.HOSPITAL, x=0.5, y=2.5))
    w.hospitals["H2"] = Hospital(
        node_id="H2",
        name="Northside Clinic",
        capacity=2,
        capabilities={Capability.PEDIATRIC},
    )

    # --- roads: horizontal rows ---------------------------------------
    for row in (("N01", "N02", "N03", "N04"),
                ("N05", "N06", "N07", "N08"),
                ("N09", "N10", "N11", "N12")):
        for i in range(len(row) - 1):
            w.add_road(row[i], row[i + 1], base_seconds=120)

    # --- roads: vertical columns --------------------------------------
    for col in (("N01", "N05", "N09"),
                ("N02", "N06", "N10"),
                ("N03", "N07", "N11"),
                ("N04", "N08", "N12")):
        for i in range(len(col) - 1):
            w.add_road(col[i], col[i + 1], base_seconds=150)

    # --- connect stations and hospitals to the grid --------------------
    w.add_road("ST1", "N01", base_seconds=60)
    w.add_road("ST1", "N05", base_seconds=60)
    w.add_road("ST2", "N08", base_seconds=60)
    w.add_road("ST2", "N04", base_seconds=90)
    w.add_road("ST3", "N10", base_seconds=60)
    w.add_road("H1", "N03", base_seconds=90)
    w.add_road("H1", "N04", base_seconds=110)
    w.add_road("H2", "N09", base_seconds=80)
    w.add_road("H2", "N10", base_seconds=90)

    # --- the fleet -----------------------------------------------------
    fleet = [
        ("A1", UnitType.AMBULANCE, "ST1", {Capability.TRAUMA}),
        ("A2", UnitType.AMBULANCE, "ST2", {Capability.CARDIAC}),
        ("A3", UnitType.AMBULANCE, "ST2", {Capability.PEDIATRIC}),
        ("F1", UnitType.FIRE_TRUCK, "ST1", {Capability.HEAVY_LIFT}),
        ("F2", UnitType.FIRE_TRUCK, "ST3", set()),
        ("R1", UnitType.RESCUE_VAN, "ST3", {Capability.HEAVY_LIFT}),
        ("HZ1", UnitType.HAZMAT_TEAM, "ST1", {Capability.CHEMICAL}),
    ]
    for unit_id, unit_type, station, caps in fleet:
        w.units[unit_id] = ResponseUnit(
            unit_id=unit_id,
            unit_type=unit_type,
            home_station=station,
            current_node=station,
            capabilities=set(caps),
        )

    return w
