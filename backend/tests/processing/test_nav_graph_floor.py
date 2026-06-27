"""Pure unit tests for ``processing.nav_graph_floor``.

No DB, no storage, no mocks — only numpy + the pure functions under test. Covers
``transform_rooms_to_floor_canvas`` (polygon→bbox + rotation, the "no shifts"
maths), ``transform_doors_to_floor_canvas`` and ``build_floor_graph_from_mask``
(delegation to the nav_graph pipeline).
"""

import math

import networkx as nx
import numpy as np
import pytest

from app.core.exceptions import ImageProcessingError
from app.processing.nav_graph_floor import (
    MAX_BRIDGE_PX,
    SectionDoorInput,
    SectionRoomInput,
    build_floor_graph_from_mask,
    transform_doors_to_floor_canvas,
    transform_rooms_to_floor_canvas,
)


def make_room(
    x: float = 0.1,
    y: float = 0.1,
    w: float = 0.2,
    h: float = 0.2,
    scale_k: float = 1.0,
    tx: float = 0.0,
    ty: float = 0.0,
    mask_w: int = 100,
    mask_h: int = 100,
    rotation_rad: float = 0.0,
    room_id: str = "r1",
) -> SectionRoomInput:
    """Build a SectionRoomInput whose polygon is the rectangle ``(x, y, w, h)``.

    The rectangular polygon makes the no-rotation floor bbox identical to the old
    x/y/width/height inputs, so the scale+shift maths tests stay assertable.
    """
    return SectionRoomInput(
        room_id=room_id,
        name="Test",
        room_type="room",
        polygon=[(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
        mask_w=mask_w,
        mask_h=mask_h,
        scale_k=scale_k,
        rotation_rad=rotation_rad,
        tx_k=tx,
        ty_k=ty,
    )


def make_l_mask(w: int = 200, h: int = 200) -> np.ndarray:
    """A bordered canvas with an inner wall stub — guarantees corridor space."""
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[0:5, :] = 255
    mask[-5:, :] = 255
    mask[:, 0:5] = 255
    mask[:, -5:] = 255
    mask[80:85, 50:] = 255
    return mask


# transform_rooms_to_floor_canvas (scale + shift, no rotation)


def test_transform_rooms_single_room_correct_floor_px():
    """room (0.1,0.1,0.2,0.2), mask 100×100, scale_k=2, tx=10, ty=20, canvas 300.

    floor px x = 0.1*100*2 + 10 = 30 → norm 30/300 = 0.1.
    """
    room = make_room(scale_k=2.0, tx=10.0, ty=20.0, mask_w=100, mask_h=100)
    out = transform_rooms_to_floor_canvas([room], 300, 300)
    assert len(out) == 1
    assert out[0]["x"] == pytest.approx(0.1, abs=1e-9)
    # y px = 0.1*100*2 + 20 = 40 → 40/300
    assert out[0]["y"] == pytest.approx(40.0 / 300.0, abs=1e-9)


def test_transform_rooms_k_one_is_identity_scale():
    """scale_k=1, tx=ty=0, mask==canvas → norm coords preserved."""
    room = make_room(x=0.3, y=0.4, w=0.2, h=0.1, scale_k=1.0, mask_w=200, mask_h=200)
    out = transform_rooms_to_floor_canvas([room], 200, 200)
    assert out[0]["x"] == pytest.approx(0.3, abs=1e-9)
    assert out[0]["y"] == pytest.approx(0.4, abs=1e-9)
    assert out[0]["width"] == pytest.approx(0.2, abs=1e-9)
    assert out[0]["height"] == pytest.approx(0.1, abs=1e-9)


def test_transform_rooms_k_two_doubles_coords():
    """scale_k=2 doubles room px width/height (norm over the same canvas)."""
    room = make_room(x=0.1, y=0.1, w=0.2, h=0.2, scale_k=2.0, mask_w=100, mask_h=100)
    out = transform_rooms_to_floor_canvas([room], 400, 400)
    # px w = 0.2*100*2 = 40 → 40/400 = 0.1 ; vs scale_k=1 would give 0.05
    assert out[0]["width"] == pytest.approx(40.0 / 400.0, abs=1e-9)
    assert out[0]["height"] == pytest.approx(40.0 / 400.0, abs=1e-9)


def test_transform_rooms_clips_to_canvas():
    """A room extending past the canvas is clipped so x + width <= 1.0."""
    room = make_room(x=0.9, y=0.9, w=0.5, h=0.5, scale_k=1.0, mask_w=100, mask_h=100)
    out = transform_rooms_to_floor_canvas([room], 100, 100)
    assert len(out) == 1
    assert out[0]["x"] + out[0]["width"] <= 1.0 + 1e-9
    assert out[0]["y"] + out[0]["height"] <= 1.0 + 1e-9


def test_transform_rooms_empty_input_returns_empty():
    """Empty room list → empty output."""
    assert transform_rooms_to_floor_canvas([], 100, 100) == []


def test_transform_rooms_no_rotation_applied():
    """room at (0,0) maps to (tx_k/W, ty_k/H) exactly — pure scale+shift."""
    room = make_room(x=0.0, y=0.0, w=0.1, h=0.1, scale_k=3.0, tx=15.0, ty=25.0,
                     mask_w=100, mask_h=100)
    out = transform_rooms_to_floor_canvas([room], 200, 200)
    assert out[0]["x"] == pytest.approx(15.0 / 200.0, abs=1e-9)
    assert out[0]["y"] == pytest.approx(25.0 / 200.0, abs=1e-9)


# transform_rooms: polygon → bbox + rotation (this feature)


def test_transform_rooms_polygon_to_bbox():
    """An explicit polygon → its floor-canvas AABB (rotation_rad=0)."""
    room = SectionRoomInput(
        room_id="r1", name="Test", room_type="room",
        polygon=[(0.2, 0.2), (0.4, 0.2), (0.4, 0.5), (0.2, 0.5)],
        mask_w=100, mask_h=100,
        scale_k=1.0, rotation_rad=0.0, tx_k=0.0, ty_k=0.0,
    )
    out = transform_rooms_to_floor_canvas([room], 100, 100)
    assert out[0]["x"] == pytest.approx(0.2, abs=1e-9)
    assert out[0]["y"] == pytest.approx(0.2, abs=1e-9)
    assert out[0]["width"] == pytest.approx(0.2, abs=1e-9)   # 0.4 - 0.2
    assert out[0]["height"] == pytest.approx(0.3, abs=1e-9)  # 0.5 - 0.2


def test_transform_rooms_applies_rotation():
    """A 90° rotation swaps a wide room's bbox into a tall one."""
    room = SectionRoomInput(
        room_id="r1", name="Test", room_type="room",
        # wide rectangle: 40px wide × 10px tall in section space.
        polygon=[(0.1, 0.1), (0.5, 0.1), (0.5, 0.2), (0.1, 0.2)],
        mask_w=100, mask_h=100,
        scale_k=1.0, rotation_rad=np.pi / 2, tx_k=30.0, ty_k=10.0,
    )
    out = transform_rooms_to_floor_canvas([room], 200, 200)
    # After R(90°): bbox width 10px, height 40px (wide → tall).
    assert out[0]["width"] == pytest.approx(10.0 / 200.0, abs=1e-9)
    assert out[0]["height"] == pytest.approx(40.0 / 200.0, abs=1e-9)
    assert out[0]["height"] > out[0]["width"], "90° rotation makes the wide room tall"


def test_transform_rooms_drops_zero_area():
    """A degenerate (zero-width) room is dropped, not emitted."""
    room = SectionRoomInput(
        room_id="r1", name="Test", room_type="room",
        polygon=[(0.5, 0.1), (0.5, 0.1), (0.5, 0.5), (0.5, 0.5)],  # zero width
        mask_w=100, mask_h=100,
        scale_k=1.0, rotation_rad=0.0, tx_k=0.0, ty_k=0.0,
    )
    assert transform_rooms_to_floor_canvas([room], 100, 100) == []


def test_transform_rooms_output_shape():
    """Output keys: AABB + oriented box + transition metadata pass-through (D)."""
    out = transform_rooms_to_floor_canvas([make_room()], 100, 100)
    assert set(out[0].keys()) == {
        "id", "name", "room_type", "x", "y", "width", "height",
        "obb_cx", "obb_cy", "obb_w", "obb_h", "rotation_rad",
        "floor_from", "floor_to", "floors_excluded",
        "connects_up", "connects_down",
    }


# transform_doors_to_floor_canvas


def test_transform_doors_to_floor_canvas_point():
    """A door position → a floor-canvas point: x1==x2, y1==y2, room_id echoed."""
    door = SectionDoorInput(
        door_id="d1", position=(0.5, 0.25), room_id="r1",
        mask_w=100, mask_h=100,
        scale_k=2.0, rotation_rad=0.0, tx_k=10.0, ty_k=20.0,
    )
    out = transform_doors_to_floor_canvas([door], 200, 200)
    assert len(out) == 1
    # px = 0.5*100*2 + 10 = 110 → 0.55 ; py = 0.25*100*2 + 20 = 70 → 0.35
    assert out[0]["x1"] == pytest.approx(110.0 / 200.0, abs=1e-9)
    assert out[0]["y1"] == pytest.approx(70.0 / 200.0, abs=1e-9)
    assert out[0]["x1"] == out[0]["x2"]
    assert out[0]["y1"] == out[0]["y2"]
    assert out[0]["room_id"] == "r1"


def test_transform_doors_applies_rotation():
    """A 90° rotation rotates the door point about the section origin."""
    door = SectionDoorInput(
        door_id="d1", position=(0.5, 0.0), room_id=None,
        mask_w=100, mask_h=100,
        scale_k=1.0, rotation_rad=np.pi / 2, tx_k=80.0, ty_k=10.0,
    )
    out = transform_doors_to_floor_canvas([door], 200, 200)
    # sx=50, sy=0 ; cos=0, sin=1 → fx = -0 + 80 = 80 ; fy = 50 + 10 = 60
    assert out[0]["x1"] == pytest.approx(80.0 / 200.0, abs=1e-9)
    assert out[0]["y1"] == pytest.approx(60.0 / 200.0, abs=1e-9)
    assert out[0]["room_id"] is None


# build_floor_graph_from_mask


def test_floor_graph_l_mask_has_corridor_nodes():
    """A bordered mask yields at least one corridor_node."""
    graph = build_floor_graph_from_mask(make_l_mask(), [], [], 200, 200)
    corridor_nodes = [
        n for n, d in graph.nodes(data=True) if d.get("type") == "corridor_node"
    ]
    assert len(corridor_nodes) >= 1, "expected at least one corridor node"


def test_floor_graph_rooms_appear_as_room_nodes():
    """One room dict → at least one node with type 'room'."""
    room = {
        "id": "abc",
        "name": "Room A",
        "room_type": "room",
        "x": 0.3,
        "y": 0.3,
        "width": 0.1,
        "height": 0.1,
    }
    graph = build_floor_graph_from_mask(make_l_mask(), [room], [], 200, 200)
    room_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "room"]
    assert len(room_nodes) >= 1, "expected the room to appear as a room node"


def test_build_floor_graph_includes_doors():
    """A floor door dict produces a node with type 'door' in the graph."""
    room = {
        "id": "r1", "name": "R", "room_type": "room",
        "x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1,
    }
    door = {
        "id": "d1", "x1": 0.35, "y1": 0.35, "x2": 0.35, "y2": 0.35,
        "room_id": "r1",
    }
    graph = build_floor_graph_from_mask(make_l_mask(), [room], [door], 200, 200)
    door_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "door"]
    assert len(door_nodes) >= 1, "expected the door to appear as a door node"


def test_floor_graph_empty_mask_raises_error():
    """An empty array raises ImageProcessingError."""
    with pytest.raises(ImageProcessingError):
        build_floor_graph_from_mask(np.zeros((0, 0), dtype=np.uint8), [], [], 0, 0)


def make_two_section_mask(w: int = 400, h: int = 200) -> np.ndarray:
    """A bordered canvas split by a vertical divider → two enclosed sections."""
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[:5, :] = 255
    mask[-5:, :] = 255
    mask[:, :5] = 255
    mask[:, -5:] = 255
    mask[:, 195:205] = 255
    return mask


def test_floor_graph_two_sections_each_have_skeleton():
    """R1: BOTH sections get a corridor skeleton (was: only the biggest)."""
    graph = build_floor_graph_from_mask(make_two_section_mask(), [], [], 400, 200)
    corridor_pos = [
        d["pos"] for _, d in graph.nodes(data=True)
        if d.get("type") == "corridor_node"
    ]
    assert any(pos[0] < 195 for pos in corridor_pos), "left section skeleton"
    assert any(pos[0] > 205 for pos in corridor_pos), "right section skeleton"


def test_floor_graph_threads_wall_mask_and_max_snap(monkeypatch):
    """build_floor_graph_from_mask passes wall_mask + bounds to integrate_semantics."""
    import app.processing.nav_graph as ng

    captured: dict = {}

    def spy(G, rooms, doors, w, h, wall_mask=None,
            max_snap_dist_px=float("inf"), skip_px=0.0):
        captured["wall_mask"] = wall_mask
        captured["max_snap_dist_px"] = max_snap_dist_px
        captured["skip_px"] = skip_px
        return G

    monkeypatch.setattr(ng, "integrate_semantics", spy)

    mask = make_l_mask()
    build_floor_graph_from_mask(mask, [], [], 200, 200)

    assert captured["wall_mask"] is not None
    assert captured["wall_mask"].shape == mask.shape
    assert captured["max_snap_dist_px"] != float("inf")
    assert captured["skip_px"] > 0.0


def test_floor_graph_calls_bridge_with_mask_and_threshold(monkeypatch):
    """build_floor_graph_from_mask calls bridge_graph_components with the wall mask
    and a bounded threshold in [MIN_BRIDGE_PX, MAX_BRIDGE_PX]."""
    import app.processing.nav_graph as ng
    from app.processing.nav_graph_floor import MAX_BRIDGE_PX, MIN_BRIDGE_PX

    captured: dict = {}
    real_bridge = ng.bridge_graph_components

    def spy(G, wall_mask, max_bridge_dist_px):
        captured["wall_mask"] = wall_mask
        captured["max_bridge_dist_px"] = max_bridge_dist_px
        return real_bridge(G, wall_mask, max_bridge_dist_px)

    monkeypatch.setattr(ng, "bridge_graph_components", spy)

    mask = make_l_mask()
    build_floor_graph_from_mask(mask, [], [], 200, 200)

    assert captured["wall_mask"] is not None
    assert captured["wall_mask"].shape == mask.shape
    assert MIN_BRIDGE_PX <= captured["max_bridge_dist_px"] <= MAX_BRIDGE_PX


def test_floor_graph_walled_sections_stay_separate():
    """Two sections split by a solid full-height divider are NOT bridged.

    ⚠ Coarse sanity: the sections are also >MAX_BRIDGE_PX apart, so this could
    pass on distance alone. The strict LOS refusal (close nodes + wall between)
    is rigorously covered by the unit test
    ``TestBridgeGraphComponents.test_bridge_wall_between_keeps_two_components``.
    Here the full-height divider guarantees any left↔right line crosses a wall.
    """
    graph = build_floor_graph_from_mask(make_two_section_mask(), [], [], 400, 200)
    left = [n for n, d in graph.nodes(data=True)
            if d.get("type") == "corridor_node" and d["pos"][0] < 195]
    right = [n for n, d in graph.nodes(data=True)
             if d.get("type") == "corridor_node" and d["pos"][0] > 205]
    assert left and right, "both sections should have corridor nodes"
    left_comp = nx.node_connected_component(graph, left[0])
    assert not any(r in left_comp for r in right), \
        "walled sections must not be bridged together"


# attach_unlinked_rooms wiring (cross-floor fragmentation fix)


def make_two_band_mask(band: int = 18, gap: int = 6, w: int = 160) -> np.ndarray:
    """Two horizontal free corridor bands split by a thin full-width wall.

    The two band skeletons sit ~24 px apart (< ``MAX_BRIDGE_PX`` = 60), so the
    RAISED bridge ceiling would reach across them by distance — only the LOS gate
    refuses, because a solid wall lies between (AC-4).
    """
    h = 12 + band + gap + band + 12
    m = np.zeros((h, w), dtype=np.uint8)
    m[0:6, :] = 255
    m[-6:, :] = 255
    m[:, 0:6] = 255
    m[:, -6:] = 255
    y1b = 6 + band            # bottom of band 1
    ywb = y1b + gap           # bottom of the divider wall
    y2b = ywb + band          # bottom of band 2
    m[y1b:ywb, 6:w - 6] = 255       # solid full-width divider between the bands
    m[y2b:h - 6, 6:w - 6] = 255     # wall below band 2 → exactly two free bands
    return m


def test_build_floor_graph_attaches_doorless_stair_to_corridor():
    """AC-2: a door-less staircase lands on the corridor via a room_to_corridor edge."""
    stair = {
        "id": "s1", "name": "Лестница", "room_type": "staircase",
        "x": 0.05, "y": 0.2, "width": 0.1, "height": 0.1,
    }
    graph = build_floor_graph_from_mask(make_l_mask(), [stair], [], 200, 200)
    assert "room_s1" in graph
    comp = nx.node_connected_component(graph, "room_s1")
    assert any(graph.nodes[n].get("type") == "corridor_node" for n in comp), \
        "the door-less stair must share a component with a corridor node"
    assert any(
        d.get("type") == "room_to_corridor"
        for _, _, d in graph.edges("room_s1", data=True)
    ), "the linking edge must be a room_to_corridor attach edge"


def test_build_floor_graph_linked_room_single_link():
    """A door-linked room reaches the corridor via its door; the attach pass skips
    it — no duplicate room_to_corridor edge is added."""
    room = {
        "id": "r1", "name": "R", "room_type": "room",
        "x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1,
    }
    door = {
        "id": "d1", "x1": 0.35, "y1": 0.29, "x2": 0.35, "y2": 0.29, "room_id": "r1",
    }
    graph = build_floor_graph_from_mask(make_l_mask(), [room], [door], 200, 200)
    comp = nx.node_connected_component(graph, "room_r1")
    assert any(graph.nodes[n].get("type") == "corridor_node" for n in comp), \
        "the door-linked room must be on the corridor"
    room_edge_types = {
        d.get("type") for _, _, d in graph.edges("room_r1", data=True)
    }
    assert "room_to_corridor" not in room_edge_types, \
        "an already-linked room must not get an extra attach edge"
    assert room_edge_types == {"room_to_door"}, "room's only link is the door path"
    assert any(
        d.get("type") == "door_to_corridor" for _, _, d in graph.edges(data=True)
    ), "the door must have snapped to the corridor"


def test_build_floor_graph_walled_strips_not_bridged():
    """AC-4: two corridor bands within the raised bridge cap by distance but split
    by a solid wall stay in separate components (the LOS gate refuses to bridge)."""
    graph = build_floor_graph_from_mask(make_two_band_mask(), [], [], 160, 66)
    corridor = [
        (n, d["pos"]) for n, d in graph.nodes(data=True)
        if d.get("type") == "corridor_node"
    ]
    top = [n for n, pos in corridor if pos[1] < 24]
    bottom = [n for n, pos in corridor if pos[1] > 30]
    assert top and bottom, "both bands must produce corridor nodes"
    # The nearest cross-wall pair is within the raised bridge ceiling by distance,
    # so only the LOS gate (not the cap) can keep the bands apart.
    nearest = min(
        math.hypot(tp[0] - bp[0], tp[1] - bp[1])
        for _, tp in corridor if tp[1] < 24
        for _, bp in corridor if bp[1] > 30
    )
    assert nearest < MAX_BRIDGE_PX, "test setup: bands must be within the bridge cap"
    top_comp = nx.node_connected_component(graph, top[0])
    assert not any(b in top_comp for b in bottom), \
        "a solid wall between the bands must block bridging (LOS gate)"


# oriented room box (rotation fix)


def test_transform_rooms_emits_oriented_box_with_rotation():
    """A rotated room carries TRUE (un-inflated) dims + rotation_rad; the
    axis-aligned width/height are inflated by the rotation."""
    room = make_room(
        x=0.3, y=0.3, w=0.2, h=0.1, scale_k=1.0, tx=0.0, ty=0.0,
        mask_w=100, mask_h=100, rotation_rad=math.radians(30), room_id="r1",
    )
    out = transform_rooms_to_floor_canvas([room], 200, 200)
    assert len(out) == 1
    r = out[0]
    assert r["rotation_rad"] == pytest.approx(math.radians(30))
    # True dims normalised: w = 0.2*100/200 = 0.1 ; h = 0.1*100/200 = 0.05.
    assert r["obb_w"] == pytest.approx(0.1, abs=1e-6)
    assert r["obb_h"] == pytest.approx(0.05, abs=1e-6)
    # The AABB of the rotated rectangle is strictly larger than the true dims.
    assert r["width"] > r["obb_w"]
    assert r["height"] > r["obb_h"]


def test_transform_rooms_no_rotation_obb_matches_aabb():
    """With rotation 0 the oriented box equals the axis-aligned bbox (no spin)."""
    room = make_room(
        x=0.3, y=0.3, w=0.2, h=0.1, scale_k=1.0, tx=0.0, ty=0.0,
        mask_w=100, mask_h=100, rotation_rad=0.0, room_id="r1",
    )
    out = transform_rooms_to_floor_canvas([room], 200, 200)
    r = out[0]
    assert r["rotation_rad"] == 0.0
    assert r["obb_w"] == pytest.approx(r["width"], abs=1e-6)
    assert r["obb_h"] == pytest.approx(r["height"], abs=1e-6)
