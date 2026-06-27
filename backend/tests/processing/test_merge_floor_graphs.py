"""
Tests for merge_floor_graphs() and find_multifloor_route_in_graph() — pure functions.
"""

import pytest
import networkx as nx

from app.processing.nav_graph import (
    FloorGraphData,
    merge_floor_graphs,
    find_multifloor_route_in_graph,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def floor1_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("room_1", type="room", pos=(10.0, 50.0), room_name="101")
    G.add_node("corridor_1", type="corridor_node", pos=(50.0, 50.0))
    G.add_node("room_2", type="room", pos=(90.0, 50.0), room_name="102")
    G.add_edge("room_1", "corridor_1", weight=40.0, type="room_to_door")
    G.add_edge("corridor_1", "room_2", weight=40.0, type="room_to_door")
    return G


@pytest.fixture
def floor2_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("room_1", type="room", pos=(10.0, 50.0), room_name="201")
    G.add_node("corridor_1", type="corridor_node", pos=(50.0, 50.0))
    G.add_node("room_2", type="room", pos=(90.0, 50.0), room_name="202")
    G.add_edge("room_1", "corridor_1", weight=40.0, type="room_to_door")
    G.add_edge("corridor_1", "room_2", weight=40.0, type="room_to_door")
    return G


@pytest.fixture
def floor_meta() -> dict:
    return {"mask_width": 100, "mask_height": 100, "scale_factor": 0.02}


@pytest.fixture
def floor1_data(floor1_graph, floor_meta) -> FloorGraphData:
    return FloorGraphData(
        graph=floor1_graph,
        metadata=floor_meta,
        reconstruction_id=1,
        floor_number=1,
        floor_name="Floor 1",
    )


@pytest.fixture
def floor2_data(floor2_graph, floor_meta) -> FloorGraphData:
    return FloorGraphData(
        graph=floor2_graph,
        metadata=floor_meta,
        reconstruction_id=2,
        floor_number=2,
        floor_name="Floor 2",
    )


@pytest.fixture
def sample_transition() -> dict:
    return {
        "id": 10,
        "name": "Лестница А",
        "type": "stairs",
        # merge_floor_graphs() consumes normalised x/y per point (the centroid
        # production extracts from a transition's geometry — see nav_service.py).
        "points": [
            {
                "id": 101,
                "reconstruction_id": 1,
                "x": 0.5,
                "y": 0.5,
            },
            {
                "id": 102,
                "reconstruction_id": 2,
                "x": 0.5,
                "y": 0.5,
            },
        ],
    }


# ---------------------------------------------------------------------------
# merge_floor_graphs tests
# ---------------------------------------------------------------------------

def test_merge_floor_graphs_two_floors_no_node_collision(floor1_data, floor2_data):
    # Arrange
    floor_data = [floor1_data, floor2_data]

    # Act
    merged, _ = merge_floor_graphs(floor_data, [])

    # Assert — all node ids are prefixed, no collision
    node_ids = list(merged.nodes())
    floor1_nodes = [n for n in node_ids if str(n).startswith("1:")]
    floor2_nodes = [n for n in node_ids if str(n).startswith("2:")]
    assert len(floor1_nodes) > 0, "Floor 1 nodes must be present"
    assert len(floor2_nodes) > 0, "Floor 2 nodes must be present"
    assert set(floor1_nodes).isdisjoint(set(floor2_nodes)), "Node ids must not collide"


def test_merge_floor_graphs_contains_all_nodes(floor1_data, floor2_data):
    # Arrange
    floor_data = [floor1_data, floor2_data]

    # Act
    merged, _ = merge_floor_graphs(floor_data, [])

    # Assert — 3 nodes per floor = 6 total
    assert merged.number_of_nodes() == 6


def test_merge_floor_graphs_transition_edge_created(
    floor1_data, floor2_data, sample_transition
):
    # Arrange
    floor_data = [floor1_data, floor2_data]

    # Act
    merged, _ = merge_floor_graphs(floor_data, [sample_transition])

    # Assert — floor_transition edge exists
    transition_edges = [
        (u, v) for u, v, d in merged.edges(data=True)
        if d.get("type") == "floor_transition"
    ]
    assert len(transition_edges) >= 1, "At least one floor_transition edge must be created"


def test_merge_floor_graphs_transition_is_bidirectional(
    floor1_data, floor2_data, sample_transition
):
    # Arrange
    floor_data = [floor1_data, floor2_data]

    # Act
    merged, _ = merge_floor_graphs(floor_data, [sample_transition])

    # Assert — nx.Graph is undirected so edge is accessible both ways.
    # Teleport nodes are named teleport_{group_id}_pt_{point_id}.
    teleport_from = "teleport_10_pt_101"
    teleport_to = "teleport_10_pt_102"
    assert merged.has_edge(teleport_from, teleport_to)
    assert merged.has_edge(teleport_to, teleport_from)


def test_merge_floor_graphs_no_transitions_no_teleport_nodes(floor1_data, floor2_data):
    # Arrange
    floor_data = [floor1_data, floor2_data]

    # Act
    merged, _ = merge_floor_graphs(floor_data, [])

    # Assert — no teleport nodes
    teleport_nodes = [n for n in merged.nodes() if str(n).startswith("teleport_")]
    assert len(teleport_nodes) == 0


def test_merge_floor_graphs_single_floor_returns_same(floor1_data):
    # Arrange
    floor_data = [floor1_data]

    # Act
    merged, by_recon = merge_floor_graphs(floor_data, [])

    # Assert — same node count, prefixed
    assert merged.number_of_nodes() == floor1_data.graph.number_of_nodes()
    assert 1 in by_recon


# ---------------------------------------------------------------------------
# find_multifloor_route_in_graph tests
# ---------------------------------------------------------------------------

def test_find_multifloor_same_floor_finds_path(floor1_data):
    # Arrange
    merged, by_recon = merge_floor_graphs([floor1_data], [])

    # Act
    result = find_multifloor_route_in_graph(merged, by_recon, 1, "1", 1, "2")

    # Assert
    assert result is not None
    assert result["status"] == "success"
    assert len(result["path_segments"]) >= 1


def test_find_multifloor_two_floors_path_through_transition(
    floor1_data, floor2_data, sample_transition
):
    # Arrange
    merged, by_recon = merge_floor_graphs(
        [floor1_data, floor2_data], [sample_transition]
    )

    # Act
    result = find_multifloor_route_in_graph(merged, by_recon, 1, "1", 2, "2")

    # Assert
    assert result is not None
    assert result["status"] == "success"


def test_find_multifloor_no_transitions_returns_none(floor1_data, floor2_data):
    # Arrange — no transitions, graphs are disconnected
    merged, by_recon = merge_floor_graphs([floor1_data, floor2_data], [])

    # Act
    result = find_multifloor_route_in_graph(merged, by_recon, 1, "1", 2, "2")

    # Assert
    assert result is None


def test_find_multifloor_unknown_room_returns_none(floor1_data, floor2_data, sample_transition):
    # Arrange
    merged, by_recon = merge_floor_graphs(
        [floor1_data, floor2_data], [sample_transition]
    )

    # Act — room_id "999" does not exist
    result = find_multifloor_route_in_graph(merged, by_recon, 1, "999", 2, "2")

    # Assert
    assert result is None


def test_find_multifloor_segments_count_matches_floors(
    floor1_data, floor2_data, sample_transition
):
    # Arrange
    merged, by_recon = merge_floor_graphs(
        [floor1_data, floor2_data], [sample_transition]
    )

    # Act
    result = find_multifloor_route_in_graph(merged, by_recon, 1, "1", 2, "2")

    # Assert — path crosses two floors → two segments
    assert result is not None
    assert len(result["path_segments"]) == 2, (
        "Cross-floor route must produce one segment per floor"
    )


def test_find_multifloor_transitions_used_populated(
    floor1_data, floor2_data, sample_transition
):
    # Arrange
    merged, by_recon = merge_floor_graphs(
        [floor1_data, floor2_data], [sample_transition]
    )

    # Act
    result = find_multifloor_route_in_graph(merged, by_recon, 1, "1", 2, "2")

    # Assert
    assert result is not None
    assert len(result["transitions_used"]) >= 1
    assert result["transitions_used"][0]["name"] == "Лестница А"


def test_find_multifloor_floor_number_in_segments(
    floor1_data, floor2_data, sample_transition
):
    # Arrange
    merged, by_recon = merge_floor_graphs(
        [floor1_data, floor2_data], [sample_transition]
    )

    # Act
    result = find_multifloor_route_in_graph(merged, by_recon, 1, "1", 2, "2")

    # Assert — floor numbers match FloorGraphData
    assert result is not None
    floor_numbers = {seg["floor_number"] for seg in result["path_segments"]}
    assert 1 in floor_numbers
    assert 2 in floor_numbers
