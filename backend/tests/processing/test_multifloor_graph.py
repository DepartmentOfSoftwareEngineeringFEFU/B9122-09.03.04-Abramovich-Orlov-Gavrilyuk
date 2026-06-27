"""Unit tests for the PURE cross-floor routing/matching (D).

 (Processing
section, 18 tests): projection (incl. the differing-``k`` reconciliation),
matching (tolerance, mutual-nearest, stair gates, elevator exclusions, type
isolation), metric merge + overrides, metric A* (two-floor route, A*≡Dijkstra
admissibility, no_path, unknown room). Synthetic ``nx.Graph``s with hand-set ``pos``.
"""

import math

import networkx as nx
import pytest

from app.core.floor_stitching_constants import TRANSITION_COST_M
from app.processing.multifloor_graph import (
    FloorRouteEntry,
    TransitionLink,
    TransitionNode,
    find_multifloor_route_by_id,
    match_cross_floor_transitions,
    merge_floor_graphs_by_id,
    project_to_building_frame,
)


def _tn(floor_id, number, node_id, rtype, x, y, **meta) -> TransitionNode:
    return TransitionNode(
        floor_id=floor_id,
        floor_number=number,
        node_id=node_id,
        room_type=rtype,
        x_m=x,
        y_m=y,
        floor_from=meta.get("floor_from"),
        floor_to=meta.get("floor_to"),
        floors_excluded=meta.get("floors_excluded", []),
        connects_up=meta.get("connects_up", True),
        connects_down=meta.get("connects_down", True),
    )


def _entry(floor_id, number, graph, *, scale_factor=0.1, mask=200, transform=None,
           elevation=0.0) -> FloorRouteEntry:
    return FloorRouteEntry(
        floor_id=floor_id,
        floor_number=number,
        graph=graph,
        scale_factor=scale_factor,
        nav_mask_w=mask,
        nav_mask_h=mask,
        floor_mask_w=mask,
        floor_mask_h=mask,
        building_transform=transform,
        elevation_m=elevation,
    )


# project_to_building_frame


def test_project_reference_floor_identity_returns_metric_pos():
    """Identity transform on the reference floor → pos / k / ppm."""
    x, y = project_to_building_frame((100.0, 50.0), 1.0, None, 10.0)
    assert x == pytest.approx(10.0)
    assert y == pytest.approx(5.0)


def test_project_differing_k_aligns_partner_shafts():
    """Two floors of different k map a stacked shaft to the SAME building XY."""
    # Floor A: nav==mask (k=1), stair canvas (100,100).
    a = project_to_building_frame((100.0, 100.0), 1.0, None, 10.0)
    # Floor B: nav 2× mask (k=2), stair canvas (200,200) → same mask px (100,100).
    b = project_to_building_frame((200.0, 200.0), 2.0, None, 10.0)
    assert a == pytest.approx(b)
    assert a == pytest.approx((10.0, 10.0))


def test_project_similarity_applied_matches_manual():
    """scale+rotation+translation match a hand computation."""
    transform = {"scale": 2.0, "rotation_rad": math.pi / 2, "tx": 10.0, "ty": 5.0}
    x, y = project_to_building_frame((50.0, 30.0), 1.0, transform, 1.0)
    # c≈0, s=2 → x_ref = -2*30 + 10 = -50; y_ref = 2*50 + 5 = 105.
    assert x == pytest.approx(-50.0, abs=1e-6)
    assert y == pytest.approx(105.0, abs=1e-6)


def test_project_invalid_k_raises():
    with pytest.raises(ValueError):
        project_to_building_frame((1.0, 1.0), 0.0, None, 10.0)


# match_cross_floor_transitions


def test_match_adjacent_stairs_within_tolerance_links():
    nodes = [
        _tn(10, 1, "room_s1", "staircase", 0.0, 0.0),
        _tn(20, 2, "room_s2", "staircase", 0.5, 0.0),
    ]
    links, unmatched = match_cross_floor_transitions(nodes, 1.5)
    assert len(links) == 1
    assert links[0].lower_floor_id == 10 and links[0].upper_floor_id == 20
    assert links[0].type == "staircase" and links[0].source == "auto"
    assert unmatched == []


def test_match_far_shafts_no_link():
    nodes = [
        _tn(10, 1, "room_s1", "staircase", 0.0, 0.0),
        _tn(20, 2, "room_s2", "staircase", 5.0, 0.0),
    ]
    links, unmatched = match_cross_floor_transitions(nodes, 1.5)
    assert links == []
    assert len(unmatched) == 2


def test_match_two_close_shafts_mutual_nearest_only():
    """Two shafts 1 m apart link within themselves, never cross (mutual-nearest)."""
    nodes = [
        _tn(10, 1, "room_a1", "staircase", 0.0, 0.0),
        _tn(20, 2, "room_a2", "staircase", 0.0, 0.0),
        _tn(10, 1, "room_b1", "staircase", 1.0, 0.0),
        _tn(20, 2, "room_b2", "staircase", 1.0, 0.0),
    ]
    links, _ = match_cross_floor_transitions(nodes, 1.5)
    assert len(links) == 2
    pairs = {(lk.lower_node, lk.upper_node) for lk in links}
    assert pairs == {("room_a1", "room_a2"), ("room_b1", "room_b2")}


def test_match_stair_no_up_blocks_edge():
    nodes = [
        _tn(10, 1, "room_s1", "staircase", 0.0, 0.0, connects_up=False),
        _tn(20, 2, "room_s2", "staircase", 0.0, 0.0),
    ]
    links, unmatched = match_cross_floor_transitions(nodes, 1.5)
    assert links == []
    assert len(unmatched) == 2


def test_match_stair_no_down_blocks_edge():
    nodes = [
        _tn(10, 1, "room_s1", "staircase", 0.0, 0.0),
        _tn(20, 2, "room_s2", "staircase", 0.0, 0.0, connects_down=False),
    ]
    links, _ = match_cross_floor_transitions(nodes, 1.5)
    assert links == []


def test_match_legacy_no_gate_fields_links():
    """Default gates (no fields set) → the stair links normally."""
    nodes = [
        _tn(10, 1, "room_s1", "staircase", 0.0, 0.0),
        _tn(20, 2, "room_s2", "staircase", 0.0, 0.0),
    ]
    links, _ = match_cross_floor_transitions(nodes, 1.5)
    assert len(links) == 1


def test_match_elevator_excluded_floor_skips():
    """An elevator excluding floor 5 links 4↔6 directly; floor 5 is unmatched."""
    rng = {"floor_from": 4, "floor_to": 6, "floors_excluded": [5]}
    nodes = [
        _tn(40, 4, "room_e4", "elevator", 0.0, 0.0, **rng),
        _tn(50, 5, "room_e5", "elevator", 0.0, 0.0, **rng),
        _tn(60, 6, "room_e6", "elevator", 0.0, 0.0, **rng),
    ]
    links, unmatched = match_cross_floor_transitions(nodes, 1.5)
    assert len(links) == 1
    assert links[0].lower_floor_id == 40 and links[0].upper_floor_id == 60
    assert [u.node for u in unmatched] == ["room_e5"]


def test_match_different_types_never_link():
    nodes = [
        _tn(10, 1, "room_s1", "staircase", 0.0, 0.0),
        _tn(20, 2, "room_e1", "elevator", 0.0, 0.0),
    ]
    links, unmatched = match_cross_floor_transitions(nodes, 1.5)
    assert links == []
    assert len(unmatched) == 2


# merge_floor_graphs_by_id


def test_merge_weights_in_meters():
    g = nx.Graph()
    g.add_node("room_a", type="room", pos=(10.0, 10.0))
    g.add_node("room_b", type="room", pos=(110.0, 10.0))
    g.add_edge("room_a", "room_b", weight=100.0, type="corridor_edge")
    merged = merge_floor_graphs_by_id(
        [_entry(10, 1, g, scale_factor=0.02)], [], TRANSITION_COST_M, 10.0
    )
    assert merged["10:room_a"]["10:room_b"]["weight"] == pytest.approx(2.0)


def test_merge_adds_transition_edge_cost():
    g1 = nx.Graph()
    g1.add_node("room_s1", type="room", room_type="staircase", pos=(100.0, 20.0))
    g2 = nx.Graph()
    g2.add_node("room_s2", type="room", room_type="staircase", pos=(100.0, 20.0))
    link = TransitionLink(10, "room_s1", 20, "room_s2", "staircase", "auto", 0.0)
    merged = merge_floor_graphs_by_id(
        [_entry(10, 1, g1), _entry(20, 2, g2, elevation=3.0)],
        [link], TRANSITION_COST_M, 10.0,
    )
    edge = merged["10:room_s1"]["20:room_s2"]
    assert edge["type"] == "floor_transition"
    assert edge["weight"] == pytest.approx(TRANSITION_COST_M)


def test_merge_applies_overrides():
    """merge wires exactly the final link set — present link → edge; [] → none."""
    g1 = nx.Graph()
    g1.add_node("room_s1", type="room", room_type="staircase", pos=(100.0, 20.0))
    g2 = nx.Graph()
    g2.add_node("room_s2", type="room", room_type="staircase", pos=(100.0, 20.0))
    entries = [_entry(10, 1, g1), _entry(20, 2, g2, elevation=3.0)]
    link = TransitionLink(10, "room_s1", 20, "room_s2", "staircase", "forced", 0.0)

    with_link = merge_floor_graphs_by_id(entries, [link], TRANSITION_COST_M, 10.0)
    assert with_link.has_edge("10:room_s1", "20:room_s2")

    without = merge_floor_graphs_by_id(entries, [], TRANSITION_COST_M, 10.0)
    assert not without.has_edge("10:room_s1", "20:room_s2")


# find_multifloor_route_by_id


def _two_floor_merged(link=True):
    """Floor 10 (A→s1) + floor 20 (s2→m→B, plus a longer s2→B). Stair links s1↔s2."""
    g1 = nx.Graph()
    g1.add_node("room_A", type="room", pos=(20.0, 20.0))
    g1.add_node("room_s1", type="room", room_type="staircase", pos=(100.0, 20.0))
    g1.add_edge("room_A", "room_s1", weight=80.0, type="corridor_edge",
                pts=[(20.0, 20.0), (100.0, 20.0)])

    g2 = nx.Graph()
    g2.add_node("room_s2", type="room", room_type="staircase", pos=(100.0, 20.0))
    g2.add_node("c_m", type="corridor_node", pos=(130.0, 20.0))
    g2.add_node("room_B", type="room", pos=(200.0, 20.0))
    g2.add_edge("room_s2", "c_m", weight=30.0, type="corridor_edge",
                pts=[(100.0, 20.0), (130.0, 20.0)])
    g2.add_edge("c_m", "room_B", weight=30.0, type="corridor_edge",
                pts=[(130.0, 20.0), (200.0, 20.0)])
    g2.add_edge("room_s2", "room_B", weight=100.0, type="corridor_edge",
                pts=[(100.0, 20.0), (200.0, 20.0)])

    links = (
        [TransitionLink(10, "room_s1", 20, "room_s2", "staircase", "auto", 0.0)]
        if link
        else []
    )
    return merge_floor_graphs_by_id(
        [_entry(10, 1, g1), _entry(20, 2, g2, elevation=3.0)],
        links, TRANSITION_COST_M, 10.0,
    )


def test_route_two_floors_via_stair_two_segments():
    merged = _two_floor_merged()
    result = find_multifloor_route_by_id(merged, 10, "A", 20, "B")
    assert result["status"] == "success"
    assert len(result["path_segments"]) == 2
    assert result["path_segments"][0]["floor_id"] == 10
    assert result["path_segments"][1]["floor_id"] == 20
    assert len(result["transitions_used"]) == 1
    assert result["transitions_used"][0]["type"] == "staircase"
    # A→s1 (8m) + transition (3m) + s2→m→B (6m) = 17m.
    assert result["total_distance_m"] == pytest.approx(17.0)


def test_route_astar_equals_dijkstra_cost():
    """Admissible heuristic → A* total == Dijkstra shortest-path length."""
    merged = _two_floor_merged()
    result = find_multifloor_route_by_id(merged, 10, "A", 20, "B")
    dijkstra = nx.dijkstra_path_length(merged, "10:room_A", "20:room_B", weight="weight")
    assert result["total_distance_m"] == pytest.approx(dijkstra)


def test_route_no_link_returns_no_path():
    merged = _two_floor_merged(link=False)
    result = find_multifloor_route_by_id(merged, 10, "A", 20, "B")
    assert result["status"] == "no_path"
    assert result["path_segments"] == []


def test_route_unknown_room_raises():
    merged = _two_floor_merged()
    with pytest.raises(ValueError):
        find_multifloor_route_by_id(merged, 10, "does-not-exist", 20, "B")
