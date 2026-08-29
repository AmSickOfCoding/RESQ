"""Comprehensive Pytest test suite for the RESQ spatial routing package."""

import math
import pytest

from src.routing import (
    CityGraph,
    DuplicateNodeError,
    Edge,
    EdgeNotFoundError,
    HospitalSelectionResult,
    InvalidCostParametersError,
    InvalidGraphError,
    NoAvailableHospitalError,
    Node,
    NodeNotFoundError,
    PathNotFoundError,
    PathResult,
    calculate_traversal_time,
    find_fastest_path,
    find_optimal_hospital,
    generate_synthetic_city_graph,
    reroute_path,
)


class TestDataStructures:
    """Tests for Node, Edge, and CityGraph data structures and validations."""

    def test_node_creation_and_validation(self):
        node = Node(id="N1", x=10.0, y=20.0, node_type="HOSPITAL", capacity=50, occupied_beds=10)
        assert node.id == "N1"
        assert node.x == 10.0
        assert node.y == 20.0
        assert node.node_type == "HOSPITAL"
        assert node.capacity == 50
        assert node.occupied_beds == 10

        # Distance calculation
        node2 = Node(id="N2", x=13.0, y=24.0)
        assert pytest.approx(node.distance_to(node2), 1e-5) == 5.0

    def test_invalid_node_type(self):
        with pytest.raises(InvalidGraphError, match="Invalid node_type"):
            Node(id="N1", x=0, y=0, node_type="INVALID_TYPE")

    def test_invalid_node_capacity(self):
        with pytest.raises(InvalidGraphError, match="capacity cannot be negative"):
            Node(id="N1", x=0, y=0, capacity=-5)

        with pytest.raises(InvalidGraphError, match="occupied_beds cannot be negative"):
            Node(id="N1", x=0, y=0, occupied_beds=-1)

    def test_edge_creation_and_validation(self):
        edge = Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0, congestion=0.2)
        assert edge.source_id == "A"
        assert edge.target_id == "B"
        assert edge.distance == 100.0
        assert edge.speed_limit == 10.0
        assert edge.congestion == 0.2
        assert not edge.is_closed

    def test_invalid_edge_parameters(self):
        with pytest.raises(InvalidCostParametersError, match="distance must be strictly positive"):
            Edge(source_id="A", target_id="B", distance=0.0, speed_limit=10.0)

        with pytest.raises(InvalidCostParametersError, match="speed_limit must be strictly positive"):
            Edge(source_id="A", target_id="B", distance=100.0, speed_limit=-5.0)

        with pytest.raises(InvalidCostParametersError, match="congestion must be in range"):
            Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0, congestion=1.5)

    def test_city_graph_operations(self):
        graph = CityGraph()
        n1 = Node(id=1, x=0.0, y=0.0)
        n2 = Node(id=2, x=100.0, y=0.0)
        graph.add_node(n1)
        graph.add_node(n2)

        assert graph.node_count == 2
        assert graph.get_node(1) == n1

        # Duplicate node error
        with pytest.raises(DuplicateNodeError):
            graph.add_node(Node(id=1, x=5.0, y=5.0))

        # Overwrite node
        n1_new = Node(id=1, x=10.0, y=10.0)
        graph.add_node(n1_new, overwrite=True)
        assert graph.get_node(1).x == 10.0

        # Edge additions
        e12 = Edge(source_id=1, target_id=2, distance=100.0, speed_limit=20.0)
        graph.add_edge(e12, bidirectional=True)
        assert graph.edge_count == 2
        assert graph.has_edge(1, 2)
        assert graph.has_edge(2, 1)

    def test_city_graph_missing_nodes_and_edges(self):
        graph = CityGraph()
        graph.add_node(Node(id="A", x=0, y=0))

        with pytest.raises(NodeNotFoundError):
            graph.get_node("NON_EXISTENT")

        with pytest.raises(NodeNotFoundError):
            graph.add_edge(Edge(source_id="A", target_id="B", distance=10, speed_limit=10))

        graph.add_node(Node(id="B", x=10, y=0))
        with pytest.raises(EdgeNotFoundError):
            graph.get_edge("A", "B")

    def test_node_and_edge_removal(self):
        graph = CityGraph()
        n1 = Node(id="A", x=0, y=0)
        n2 = Node(id="B", x=10, y=0)
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(Edge(source_id="A", target_id="B", distance=10, speed_limit=10), bidirectional=True)

        graph.remove_edge("A", "B")
        assert not graph.has_edge("A", "B")
        assert graph.has_edge("B", "A")

        graph.remove_node("A")
        assert not graph.has_node("A")
        assert not graph.has_edge("B", "A")


class TestDynamicDisruptions:
    """Tests for dynamic road closures, congestion updates, and hospital capacity updates."""

    @pytest.fixture
    def setup_graph(self):
        graph = CityGraph()
        n1 = Node(id="A", x=0, y=0)
        n2 = Node(id="B", x=100, y=0)
        h1 = Node(id="H1", x=200, y=0, node_type="HOSPITAL", capacity=10, occupied_beds=2)
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_node(h1)

        e1 = Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0)
        graph.add_edge(e1, bidirectional=True)
        return graph

    def test_set_road_closure(self, setup_graph):
        graph = setup_graph
        graph.set_road_closure("A", "B", is_closed=True, bidirectional=True)
        assert graph.get_edge("A", "B").is_closed
        assert graph.get_edge("B", "A").is_closed

        graph.set_road_closure("A", "B", is_closed=False)
        assert not graph.get_edge("A", "B").is_closed

    def test_set_congestion(self, setup_graph):
        graph = setup_graph
        graph.set_congestion("A", "B", level=0.5, bidirectional=True)
        assert graph.get_edge("A", "B").congestion == 0.5
        assert graph.get_edge("B", "A").congestion == 0.5

        with pytest.raises(InvalidCostParametersError):
            graph.set_congestion("A", "B", level=1.5)

    def test_update_hospital_capacity(self, setup_graph):
        graph = setup_graph
        graph.update_hospital_capacity(hospital_id="H1", occupied_beds=8, capacity=15)
        h = graph.get_node("H1")
        assert h.occupied_beds == 8
        assert h.capacity == 15

        with pytest.raises(InvalidGraphError):
            graph.update_hospital_capacity(hospital_id="A", occupied_beds=5)


class TestCostModeling:
    """Tests for traversal cost and emergency priority calculations."""

    def test_standard_traversal_cost(self):
        edge = Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0, congestion=0.0)
        # 100m / (10m/s * (1 - 0)) = 10s
        assert calculate_traversal_time(edge, priority_tier="STANDARD") == 10.0

    def test_congestion_traversal_cost(self):
        # 50% congestion: speed limit becomes 10 * 0.5 = 5 m/s -> 100m / 5m/s = 20s
        edge = Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0, congestion=0.5)
        assert calculate_traversal_time(edge, priority_tier="STANDARD") == 20.0

    def test_critical_siren_multiplier(self):
        # Critical tier: effective speed = 10 * 1.25 = 12.5 m/s -> 100 / 12.5 = 8s
        edge = Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0, congestion=0.0)
        cost_critical = calculate_traversal_time(edge, priority_tier="CRITICAL", siren_multiplier=1.25)
        assert cost_critical == 8.0

    def test_closed_or_gridlocked_road(self):
        closed_edge = Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0, is_closed=True)
        assert math.isinf(calculate_traversal_time(closed_edge))

        gridlock_edge = Edge(source_id="A", target_id="B", distance=100.0, speed_limit=10.0, congestion=1.0)
        assert math.isinf(calculate_traversal_time(gridlock_edge))


class TestPathfinder:
    """Tests for A* pathfinding and mid-transit dynamic rerouting."""

    @pytest.fixture
    def linear_graph(self):
        # Network: A --(100m)--> B --(100m)--> C
        # Bypass:  A --------(300m)----------> C
        graph = CityGraph()
        n_a = Node("A", 0.0, 0.0)
        n_b = Node("B", 100.0, 0.0)
        n_c = Node("C", 200.0, 0.0)
        n_d = Node("D", 100.0, 100.0)
        for n in [n_a, n_b, n_c, n_d]:
            graph.add_node(n)

        # Standard speed = 10 m/s
        graph.add_edge(Edge("A", "B", 100.0, 10.0))
        graph.add_edge(Edge("B", "C", 100.0, 10.0))
        graph.add_edge(Edge("A", "D", 100.0, 10.0))
        graph.add_edge(Edge("D", "C", 100.0, 10.0))
        return graph

    def test_a_star_fastest_path(self, linear_graph):
        res = find_fastest_path(linear_graph, "A", "C", priority_tier="STANDARD")
        assert res.nodes == ["A", "B", "C"]
        assert res.total_distance == 200.0
        assert res.total_time == 20.0

    def test_a_star_same_source_target(self, linear_graph):
        res = find_fastest_path(linear_graph, "A", "A")
        assert res.nodes == ["A"]
        assert res.edges == []
        assert res.total_distance == 0.0
        assert res.total_time == 0.0

    def test_a_star_unreachable_path(self, linear_graph):
        # Close all outgoing edges to C
        linear_graph.set_road_closure("B", "C", is_closed=True)
        linear_graph.set_road_closure("D", "C", is_closed=True)

        with pytest.raises(PathNotFoundError):
            find_fastest_path(linear_graph, "A", "C")

    def test_dynamic_rerouting(self, linear_graph):
        # Vehicle is at B heading to C, but B -> C road closes!
        linear_graph.set_road_closure("B", "C", is_closed=True)
        # Add connection B -> D
        linear_graph.add_edge(Edge("B", "D", 50.0, 10.0))

        reroute_res = reroute_path(linear_graph, current_node_id="B", target_id="C", priority_tier="CRITICAL")
        assert reroute_res.nodes == ["B", "D", "C"]
        assert reroute_res.total_distance == 150.0


class TestFacilitySelection:
    """Tests for Dijkstra multi-hospital evaluation and selection."""

    def test_find_optimal_hospital(self):
        graph = CityGraph()
        inc = Node("INC", 0.0, 0.0, node_type="INCIDENT")
        graph.add_node(inc)

        # Hospital 1: Near (100m -> 10s travel time), but highly occupied (10 occupied beds)
        # total_cost = 10s + (10 beds * 60s/bed) = 610s
        h1 = Node("H1", 100.0, 0.0, node_type="HOSPITAL", capacity=20, occupied_beds=10)

        # Hospital 2: Further (300m -> 30s travel time), but empty (0 occupied beds)
        # total_cost = 30s + (0 beds * 60s/bed) = 30s
        h2 = Node("H2", 300.0, 0.0, node_type="HOSPITAL", capacity=20, occupied_beds=0)

        graph.add_node(h1)
        graph.add_node(h2)

        graph.add_edge(Edge("INC", "H1", 100.0, 10.0))
        graph.add_edge(Edge("INC", "H2", 300.0, 10.0))

        selection: HospitalSelectionResult = find_optimal_hospital(
            graph, incident_id="INC", priority_tier="STANDARD", bed_penalty_factor=60.0
        )

        assert selection.hospital_node.id == "H2"
        assert selection.total_cost == 30.0
        assert selection.travel_time == 30.0

    def test_ignore_full_hospitals(self):
        graph = CityGraph()
        inc = Node("INC", 0.0, 0.0, node_type="INCIDENT")
        h1 = Node("H1", 100.0, 0.0, node_type="HOSPITAL", capacity=5, occupied_beds=5)  # FULL!
        h2 = Node("H2", 200.0, 0.0, node_type="HOSPITAL", capacity=10, occupied_beds=1)

        graph.add_node(inc)
        graph.add_node(h1)
        graph.add_node(h2)
        graph.add_edge(Edge("INC", "H1", 100.0, 10.0))
        graph.add_edge(Edge("INC", "H2", 200.0, 10.0))

        selection = find_optimal_hospital(graph, incident_id="INC", ignore_full_hospitals=True)
        assert selection.hospital_node.id == "H2"

    def test_no_available_hospitals_exception(self):
        graph = CityGraph()
        inc = Node("INC", 0.0, 0.0, node_type="INCIDENT")
        h1 = Node("H1", 100.0, 0.0, node_type="HOSPITAL", capacity=5, occupied_beds=5)
        graph.add_node(inc)
        graph.add_node(h1)
        # Edge is closed
        graph.add_edge(Edge("INC", "H1", 100.0, 10.0, is_closed=True))

        with pytest.raises(NoAvailableHospitalError):
            find_optimal_hospital(graph, incident_id="INC")


class TestGenerator:
    """Tests for synthetic city grid generator."""

    def test_grid_generation(self):
        graph = generate_synthetic_city_graph(
            rows=4, cols=4, grid_spacing=500.0, num_stations=2, num_hospitals=2, seed=123
        )

        assert graph.node_count == 16
        assert graph.edge_count == 48

        stations = graph.get_stations()
        hospitals = graph.get_hospitals()
        assert len(stations) == 2
        assert len(hospitals) == 2

    def test_invalid_generator_params(self):
        with pytest.raises(InvalidGraphError):
            generate_synthetic_city_graph(rows=0, cols=5)

        with pytest.raises(InvalidGraphError):
            generate_synthetic_city_graph(rows=2, cols=2, num_stations=3, num_hospitals=2)
