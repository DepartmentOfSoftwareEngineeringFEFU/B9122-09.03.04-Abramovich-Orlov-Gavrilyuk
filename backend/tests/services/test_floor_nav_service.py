"""Service tests for ``FloorNavService``.

The repos are AsyncMocks; ``cv2.imread`` is monkeypatched to return a small
in-memory mask (so both the schema-dims read and the section-mask load resolve
without touching disk). Tests respect the REAL data model: ``Section`` has NO
``mask`` and NO ``image_size_cropped`` attribute; rooms come from
``reconstruction.vectorization_data`` (a JSON string).
"""

import json
import logging

import networkx as nx
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.exceptions import (
    FloorAssemblyConflictError,
    FloorNavGraphNotFoundError,
    FloorNotFoundError,
    FloorSchemaError,
)
from app.processing.nav_graph import serialize_nav_graph
from app.services.floor_nav_service import FloorNavService


def make_floor(ppm: float = 50.0) -> MagicMock:
    f = MagicMock()
    f.id = 1
    f.pixels_per_meter = ppm
    f.schema_image_id = "schema-1"
    f.schema_crop_bbox = None  # no crop → full (decoded) dims
    f.nav_cutouts = None  # no cutouts by default
    return f


def make_section(
    scale: float = 1.0, tx: float = 0.0, ty: float = 0.0, rooms=None
) -> MagicMock:
    s = MagicMock()
    s.id = 10
    s.transform = {"scale": scale, "tx": tx, "ty": ty}
    recon = MagicMock()
    recon.id = 100
    recon.mask_file_id = "mask-100"
    recon.vectorization_data = json.dumps(
        {
            "image_size_cropped": [200, 150],
            "rooms": rooms if rooms is not None else [],
        }
    )
    s.reconstruction = recon
    return s


# VectorRoom shape: polygon as a list of {x, y} dicts (NO x/y/width/height).
# The rectangle (0.3,0.3)-(0.45,0.45) gives a 0.15×0.15 floor bbox at k=1.
_ROOM = {
    "id": "abc",
    "name": "Аудитория 301",
    "room_type": "room",
    "polygon": [
        {"x": 0.3, "y": 0.3},
        {"x": 0.45, "y": 0.3},
        {"x": 0.45, "y": 0.45},
        {"x": 0.3, "y": 0.45},
    ],
}


@pytest.fixture
def small_mask() -> np.ndarray:
    m = np.zeros((150, 200), dtype=np.uint8)
    m[0:4, :] = 255
    m[-4:, :] = 255
    m[:, 0:4] = 255
    m[:, -4:] = 255
    return m


def _make_svc(tmp_path, monkeypatch, small_mask, floor=None, sections=None):
    """Wire a FloorNavService with AsyncMock repos + patched cv2.imread."""
    floor_repo = AsyncMock()
    floor_repo.get_by_id.return_value = floor if floor is not None else make_floor()
    section_repo = AsyncMock()
    section_repo.list_by_floor.return_value = (
        sections if sections is not None else [make_section()]
    )
    connector_repo = AsyncMock()
    connector_repo.list_by_floor.return_value = []
    storage = MagicMock()
    storage.find_file.return_value = "/fake/path.png"
    service = FloorNavService(
        floor_repo=floor_repo,
        section_repo=section_repo,
        connector_repo=connector_repo,
        storage=storage,
        upload_dir=str(tmp_path),
    )
    # All cv2.imread calls (schema dims + section mask) return the small mask.
    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imread", lambda *a, **k: small_mask
    )
    return service


@pytest.fixture
def svc(tmp_path, monkeypatch, small_mask) -> FloorNavService:
    return _make_svc(tmp_path, monkeypatch, small_mask)


# build_floor_nav_graph


@pytest.mark.asyncio
async def test_build_floor_nav_graph_saves_json(svc, tmp_path):
    result = await svc.build_floor_nav_graph(1)
    nav_file = tmp_path / "nav" / "floor_1_nav.json"
    assert nav_file.exists(), "nav JSON should be written"
    assert "nodes_count" in result
    assert result["floor_id"] == 1
    assert result["canvas_size_px"] == [200, 150]


@pytest.mark.asyncio
async def test_build_nav_passes_cutouts_to_assemble(tmp_path, monkeypatch, small_mask):
    """floors.nav_cutouts → CutoutRaster list handed to assemble_floor_mask."""
    import app.services.floor_nav_service as fns

    floor = make_floor()
    floor.nav_cutouts = [
        {"points": [[0.3, 0.3], [0.6, 0.3], [0.6, 0.6], [0.3, 0.6]]}
    ]
    svc = _make_svc(tmp_path, monkeypatch, small_mask, floor=floor)

    captured: dict = {}
    orig = fns.assemble_floor_mask

    def spy(*args, **kwargs):
        captured["cutouts"] = kwargs.get("cutouts")
        return orig(*args, **kwargs)

    monkeypatch.setattr(fns, "assemble_floor_mask", spy)
    await svc.build_floor_nav_graph(1)

    assert captured["cutouts"] is not None
    assert len(captured["cutouts"]) == 1


@pytest.mark.asyncio
async def test_build_floor_nav_graph_no_transforms_raises_conflict(
    tmp_path, monkeypatch, small_mask
):
    section = make_section()
    section.transform = None
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    with pytest.raises(FloorAssemblyConflictError):
        await svc.build_floor_nav_graph(1)


@pytest.mark.asyncio
async def test_build_floor_nav_graph_no_ppm_raises_schema_error(
    tmp_path, monkeypatch, small_mask
):
    floor = make_floor(ppm=None)
    svc = _make_svc(tmp_path, monkeypatch, small_mask, floor=floor)
    with pytest.raises(FloorSchemaError):
        await svc.build_floor_nav_graph(1)


@pytest.mark.asyncio
async def test_build_floor_nav_graph_null_vdata_skips_rooms(
    tmp_path, monkeypatch, small_mask
):
    section = make_section()
    section.reconstruction.vectorization_data = None
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    result = await svc.build_floor_nav_graph(1)
    assert result["rooms_count"] == 0


@pytest.mark.asyncio
async def test_build_floor_nav_graph_floor_missing_raises_404(
    tmp_path, monkeypatch, small_mask
):
    floor_repo = AsyncMock()
    floor_repo.get_by_id.return_value = None
    svc = FloorNavService(
        floor_repo=floor_repo,
        section_repo=AsyncMock(),
        connector_repo=AsyncMock(),
        storage=MagicMock(),
        upload_dir=str(tmp_path),
    )
    with pytest.raises(FloorNotFoundError):
        await svc.build_floor_nav_graph(1)


@pytest.mark.asyncio
async def test_build_nav_graph_rooms_count_positive(
    tmp_path, monkeypatch, small_mask
):
    """A section whose vectorization_data has a polygon room → rooms_count > 0."""
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    result = await svc.build_floor_nav_graph(1)
    assert result["rooms_count"] > 0


@pytest.mark.asyncio
async def test_build_nav_graph_includes_doors(tmp_path, monkeypatch, small_mask):
    """A section with a VectorDoor → a door node in the assembled nav graph."""
    section = make_section(rooms=[_ROOM])
    vdata = json.loads(section.reconstruction.vectorization_data)
    vdata["doors"] = [
        {
            "id": "d1",
            "position": {"x": 0.35, "y": 0.35},
            "width": 0.9,
            "connects": ["abc"],
        }
    ]
    section.reconstruction.vectorization_data = json.dumps(vdata)
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])

    await svc.build_floor_nav_graph(1)
    data = await svc.get_floor_nav_graph_2d(1)

    assert len(data["metadata"]["door_nodes"]) >= 1, "door node must be present"


def test_read_rooms_returns_polygon():
    """_read_rooms echoes the raw VectorRoom polygon."""
    recon = MagicMock()
    recon.vectorization_data = json.dumps({"rooms": [_ROOM]})
    rooms = FloorNavService._read_rooms(recon)
    assert rooms[0]["polygon"] == _ROOM["polygon"]


def test_read_doors_returns_position_connects():
    """_read_doors echoes the raw VectorDoor position + connects."""
    recon = MagicMock()
    recon.vectorization_data = json.dumps(
        {
            "doors": [
                {"id": "d1", "position": {"x": 0.5, "y": 0.5}, "connects": ["abc"]}
            ]
        }
    )
    doors = FloorNavService._read_doors(recon)
    assert doors[0]["position"] == {"x": 0.5, "y": 0.5}
    assert doors[0]["connects"] == ["abc"]


_STAIR = {
    "id": "s1",
    "name": "Лестница",
    "room_type": "staircase",
    "polygon": [
        {"x": 0.3, "y": 0.3},
        {"x": 0.45, "y": 0.3},
        {"x": 0.45, "y": 0.45},
        {"x": 0.3, "y": 0.45},
    ],
    "connects_up": False,
    "connects_down": True,
}

_ELEVATOR = {
    "id": "e1",
    "name": "Лифт",
    "room_type": "elevator",
    "polygon": [
        {"x": 0.6, "y": 0.6},
        {"x": 0.75, "y": 0.6},
        {"x": 0.75, "y": 0.75},
        {"x": 0.6, "y": 0.75},
    ],
    "floor_from": 1,
    "floor_to": 5,
    "floors_excluded": [3],
}


@pytest.mark.asyncio
async def test_build_graph_threads_transition_metadata_onto_nodes(
    tmp_path, monkeypatch, small_mask
):
    """Stair gates + elevator range ride onto the persisted nav room nodes (D)."""
    from app.processing.nav_graph import deserialize_nav_graph

    section = make_section(rooms=[_STAIR, _ELEVATOR])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    await svc.build_floor_nav_graph(1)

    with open(svc._nav_path(1)) as f:
        graph, _ = deserialize_nav_graph(json.load(f))

    stair = graph.nodes["room_s1"]
    assert stair["connects_up"] is False
    assert stair["connects_down"] is True
    elevator = graph.nodes["room_e1"]
    assert elevator["floor_from"] == 1
    assert elevator["floor_to"] == 5
    assert elevator["floors_excluded"] == [3]


@pytest.mark.asyncio
async def test_build_graph_legacy_rooms_default_gates(
    tmp_path, monkeypatch, small_mask
):
    """A room with no gate keys still builds; the node defaults to True/True."""
    from app.processing.nav_graph import deserialize_nav_graph

    section = make_section(rooms=[_ROOM])  # _ROOM carries no transition keys
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    await svc.build_floor_nav_graph(1)

    with open(svc._nav_path(1)) as f:
        graph, _ = deserialize_nav_graph(json.load(f))

    node = graph.nodes["room_abc"]
    assert node["connects_up"] is True
    assert node["connects_down"] is True


@pytest.mark.asyncio
async def test_build_nav_graph_threads_rotation(tmp_path, monkeypatch, small_mask):
    """The section's rotation_rad reaches the SectionRoomInput fed to the transform."""
    import app.services.floor_nav_service as fns

    section = make_section(rooms=[_ROOM])
    section.transform = {"scale": 1.0, "rotation_rad": 0.6, "tx": 0.0, "ty": 0.0}
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])

    captured: dict = {}
    real = fns.transform_rooms_to_floor_canvas

    def spy(room_inputs, canvas_w, canvas_h):
        captured["rooms"] = room_inputs
        return real(room_inputs, canvas_w, canvas_h)

    monkeypatch.setattr(fns, "transform_rooms_to_floor_canvas", spy)
    await svc.build_floor_nav_graph(1)

    assert captured["rooms"], "a room input should have been built"
    assert captured["rooms"][0].rotation_rad == pytest.approx(0.6)


# rooms_on_corridor build metric (AC-6)


@pytest.mark.asyncio
async def test_build_floor_nav_graph_returns_rooms_on_corridor(
    tmp_path, monkeypatch, small_mask
):
    """The build dict carries an additive int rooms_on_corridor in [0, rooms_count]."""
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    result = await svc.build_floor_nav_graph(1)
    assert "rooms_on_corridor" in result
    assert isinstance(result["rooms_on_corridor"], int)
    assert 0 <= result["rooms_on_corridor"] <= result["rooms_count"]


@pytest.mark.asyncio
async def test_build_floor_nav_graph_all_attached_no_warning(
    tmp_path, monkeypatch, small_mask, caplog
):
    """All rooms reach the corridor → rooms_on_corridor == rooms_count, no warning."""
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    with caplog.at_level(logging.WARNING, logger="app.services.floor_nav_service"):
        result = await svc.build_floor_nav_graph(1)
    assert result["rooms_count"] >= 1
    assert result["rooms_on_corridor"] == result["rooms_count"]
    assert "reach a corridor" not in caplog.text


@pytest.mark.asyncio
async def test_build_floor_nav_graph_unlinked_room_warns(tmp_path, monkeypatch, caplog):
    """A room with no reachable corridor → rooms_on_corridor < rooms_count + warning."""
    walled = np.full((150, 200), 255, dtype=np.uint8)  # all-wall mask → no corridor
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, walled, sections=[section])
    with caplog.at_level(logging.WARNING, logger="app.services.floor_nav_service"):
        result = await svc.build_floor_nav_graph(1)
    assert result["rooms_on_corridor"] < result["rooms_count"]
    assert "reach a corridor" in caplog.text


# find_floor_route


@pytest.mark.asyncio
async def test_find_floor_route_returns_3d_path(tmp_path, monkeypatch, small_mask):
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    await svc.build_floor_nav_graph(1)
    # Route from the room to itself — exercises the found/no_path branch.
    result = await svc.find_floor_route(1, "abc", "abc")
    assert result["status"] in {"found", "no_path"}
    assert isinstance(result["path_3d"], list)
    assert result["from_room_id"] == "abc"


@pytest.mark.asyncio
async def test_find_floor_route_graph_not_built_raises_not_found(svc):
    with pytest.raises(FloorNavGraphNotFoundError):
        await svc.find_floor_route(1, "abc", "def")


@pytest.mark.asyncio
async def test_find_floor_route_unknown_room_raises_value_error(
    tmp_path, monkeypatch, small_mask
):
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    await svc.build_floor_nav_graph(1)
    with pytest.raises(ValueError):
        await svc.find_floor_route(1, "does-not-exist", "abc")


# get_floor_rooms_3d


@pytest.mark.asyncio
async def test_get_floor_rooms_3d_no_graph_returns_empty(svc):
    assert await svc.get_floor_rooms_3d(1) == []


@pytest.mark.asyncio
async def test_get_floor_rooms_3d_positions_use_scale_factor(
    tmp_path, monkeypatch, small_mask
):
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    build = await svc.build_floor_nav_graph(1)
    scale_factor = build["scale_factor"]
    rooms = await svc.get_floor_rooms_3d(1)
    assert len(rooms) >= 1
    room = rooms[0]
    # All 3 position/size components are finite numbers.
    assert all(isinstance(v, (int, float)) for v in room["position"])
    assert all(isinstance(v, (int, float)) for v in room["size"])
    # size_x ≈ room_px_w * scale_factor. room px width = 0.15 * 200 (mask_w) on a
    # k=1 canvas (master 200x150, no upscale needed) → 30 px.
    expected_w = 0.15 * 200 * scale_factor
    assert room["size"][0] == pytest.approx(expected_w, rel=0.1)
    # No rotation on this section → box rotation is 0.
    assert room["rotation"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.asyncio
async def test_get_floor_rooms_3d_uses_oriented_box_rotation(svc):
    """A room node with an oriented box → rooms-3d returns rotation = -angle and
    the oriented (true) dims rather than the inflated AABB."""
    G = nx.Graph()
    G.add_node(
        "room_abc", type="room", room_id="abc", room_name="A",
        room_type="room", pos=(100.0, 75.0),
        bbox=(70.0, 60.0, 60.0, 30.0),         # inflated AABB
        obox=(100.0, 75.0, 40.0, 20.0, 0.5),   # cx, cy, w, h, angle(rad)
    )
    with open(svc._nav_path(1), "w") as f:
        json.dump(serialize_nav_graph(G, 200, 150, 0.02), f)

    rooms = await svc.get_floor_rooms_3d(1)
    assert len(rooms) == 1
    assert rooms[0]["rotation"] == pytest.approx(-0.5, abs=1e-6)
    # size uses the oriented (true) dims, not the inflated AABB.
    assert rooms[0]["size"][0] == pytest.approx(40.0 * 0.02, abs=1e-6)
    assert rooms[0]["size"][2] == pytest.approx(20.0 * 0.02, abs=1e-6)


@pytest.mark.asyncio
async def test_get_floor_rooms_3d_bbox_only_falls_back_no_rotation(svc):
    """A legacy room node with only an AABB bbox → rotation 0, no crash."""
    G = nx.Graph()
    G.add_node(
        "room_x", type="room", room_id="x", room_name="X",
        room_type="room", pos=(50.0, 50.0), bbox=(40.0, 40.0, 20.0, 20.0),
    )
    with open(svc._nav_path(1), "w") as f:
        json.dump(serialize_nav_graph(G, 200, 150, 0.02), f)

    rooms = await svc.get_floor_rooms_3d(1)
    assert len(rooms) == 1
    assert rooms[0]["rotation"] == 0.0
    assert rooms[0]["size"][0] == pytest.approx(20.0 * 0.02, abs=1e-6)


# get_floor_nav_graph_2d


@pytest.mark.asyncio
async def test_get_floor_nav_graph_2d_returns_shape(
    tmp_path, monkeypatch, small_mask
):
    section = make_section(rooms=[_ROOM])
    svc = _make_svc(tmp_path, monkeypatch, small_mask, sections=[section])
    build = await svc.build_floor_nav_graph(1)

    data = await svc.get_floor_nav_graph_2d(1)

    # Top-level shape mirrors the reconstruction nav-graph endpoint.
    assert set(data.keys()) == {"metadata", "graph"}
    meta = data["metadata"]
    assert meta["nodes_count"] == build["nodes_count"]
    assert meta["edges_count"] == build["edges_count"]
    assert isinstance(meta["room_nodes"], list)
    assert isinstance(meta["door_nodes"], list)
    assert meta["mask_width"] == 200
    assert meta["mask_height"] == 150

    # Graph carries node-link data under the ``edges`` key (NOT ``links``).
    assert "nodes" in data["graph"] and "edges" in data["graph"]
    assert "links" not in data["graph"]
    assert len(data["graph"]["nodes"]) == build["nodes_count"]

    # The room node keeps id / type / pos[x, y] / room_name for the renderer.
    room_node = next(
        n for n in data["graph"]["nodes"] if n.get("type") == "room"
    )
    assert "id" in room_node
    assert room_node["room_name"] == "Аудитория 301"
    assert len(room_node["pos"]) == 2
    assert all(isinstance(c, (int, float)) for c in room_node["pos"])


@pytest.mark.asyncio
async def test_get_floor_nav_graph_2d_no_graph_raises_not_found(svc):
    with pytest.raises(FloorNavGraphNotFoundError):
        await svc.get_floor_nav_graph_2d(1)


# persist assembled mask (build)


@pytest.mark.asyncio
async def test_build_persists_floor_mask_png(svc, monkeypatch):
    """build_floor_nav_graph persists the assembled mask via imwrite to the
    floor_{id}_mask.png path.

    Spy on imwrite rather than asserting a real file: cv2.imwrite returns False
    on non-ASCII paths (pytest tmp_path lives under a Cyrillic home), which is a
    Windows test-isolation quirk only — production upload_dir is ASCII. This
    mirrors how the suite already stubs cv2.imread to avoid real cv2 disk IO.
    """
    captured: dict = {}

    def spy_imwrite(path, img):
        captured["path"] = path
        captured["img"] = img
        return True

    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imwrite", spy_imwrite
    )
    await svc.build_floor_nav_graph(1)
    assert captured.get("path", "").endswith("floor_1_mask.png")
    assert captured["img"] is not None


@pytest.mark.asyncio
async def test_build_mask_dims_match_graph(svc, monkeypatch):
    """Persisted mask shape == (canvas_h, canvas_w) of the graph metadata.

    canvas_size_px = [canvas_w, canvas_h]; numpy shape = (rows, cols) =
    (canvas_h, canvas_w) → assert shape == (size[1], size[0]).
    """
    captured: dict = {}

    def spy_imwrite(path, img):
        captured["path"] = path
        captured["img"] = img
        return True

    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imwrite", spy_imwrite
    )
    result = await svc.build_floor_nav_graph(1)
    assert captured["path"].endswith("floor_1_mask.png")
    canvas_w, canvas_h = result["canvas_size_px"]
    assert captured["img"].shape == (canvas_h, canvas_w)


@pytest.mark.asyncio
async def test_build_mask_write_failure_does_not_break_build(svc, monkeypatch):
    """A mask imwrite failure is swallowed — the build still returns its meta."""
    def boom(*a, **k):
        raise IOError("disk full")

    monkeypatch.setattr("app.services.floor_nav_service.cv2.imwrite", boom)
    result = await svc.build_floor_nav_graph(1)
    assert result["floor_id"] == 1
    assert "nodes_count" in result


# los_prune at route time


def _routable_graph_json() -> dict:
    """A 2-room graph with one corridor edge → find_route returns a path."""
    G = nx.Graph()
    G.add_node("room_A", type="room", pos=(20.0, 20.0))
    G.add_node("room_B", type="room", pos=(120.0, 20.0))
    G.add_edge(
        "room_A", "room_B", weight=100.0, type="corridor_edge",
        pts=[(20.0, 20.0), (70.0, 20.0), (120.0, 20.0)],
    )
    # mask_w=200, mask_h=150 → matches the small_mask fixture (150, 200).
    return serialize_nav_graph(G, 200, 150, 0.02)


@pytest.mark.asyncio
async def test_route_applies_los_prune_when_mask_present(svc, monkeypatch):
    """Mask present + dims match → los_prune is invoked with (coords, wall_mask)."""
    with open(svc._nav_path(1), "w") as f:
        json.dump(_routable_graph_json(), f)

    captured: dict = {}

    def spy_los(coords, wall_mask):
        captured["coords"] = coords
        captured["wall_mask"] = wall_mask
        return [(20.0, 20.0), (120.0, 20.0)]

    # cv2.imread is patched by the svc fixture → small_mask (150, 200) == dims.
    monkeypatch.setattr("app.services.floor_nav_service.los_prune", spy_los)

    result = await svc.find_floor_route(1, "A", "B")
    assert result["status"] == "found"
    assert captured["coords"] is not None
    assert captured["wall_mask"] is not None
    assert captured["wall_mask"].shape == (150, 200)


@pytest.mark.asyncio
async def test_route_missing_mask_falls_back_unpruned(svc, monkeypatch):
    """No persisted mask (imread → None) → los_prune skipped, route still found."""
    with open(svc._nav_path(1), "w") as f:
        json.dump(_routable_graph_json(), f)

    called = {"los": False}

    def spy_los(coords, wall_mask):
        called["los"] = True
        return coords

    monkeypatch.setattr("app.services.floor_nav_service.los_prune", spy_los)
    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imread", lambda *a, **k: None
    )

    result = await svc.find_floor_route(1, "A", "B")
    assert result["status"] == "found"
    assert called["los"] is False


@pytest.mark.asyncio
async def test_route_mask_dim_mismatch_skips_los(svc, monkeypatch):
    """Mask of a different shape → guard skips los_prune (wall-safety), no crash."""
    with open(svc._nav_path(1), "w") as f:
        json.dump(_routable_graph_json(), f)

    called = {"los": False}

    def spy_los(coords, wall_mask):
        called["los"] = True
        return coords

    monkeypatch.setattr("app.services.floor_nav_service.los_prune", spy_los)
    wrong = np.zeros((155, 200), dtype=np.uint8)  # (mask_h + 5, mask_w)
    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imread", lambda *a, **k: wrong
    )

    result = await svc.find_floor_route(1, "A", "B")
    assert result["status"] == "found"
    assert called["los"] is False
