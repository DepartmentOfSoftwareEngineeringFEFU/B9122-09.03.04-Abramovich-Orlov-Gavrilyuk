"""Service tests for ``BuildingNavService`` (D).

 (Service section):
cross-floor route stacked by elevation, same-floor delegate, not_aligned,
missing-graph 404, link listing with overrides, and force-override validation.

Repos are AsyncMocks; nav graphs are REAL JSON files written under ``tmp_path/nav``
(the service reads them off disk); ``_floor_mask_dims`` is patched per instance to
return fixed dims (cv2 imread fails on the Cyrillic tmp home — see floor_nav tests).
The persisted floor-mask PNG is absent, so ``los_prune`` is simply skipped.
"""

import json

import networkx as nx
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.exceptions import (
    BuildingNotFoundError,
    FloorNavGraphNotFoundError,
)
from app.models.building_nav import TransitionOverride
from app.processing.nav_graph import serialize_nav_graph
from app.services.building_nav_service import BuildingNavService

MASK = 200


def _floor(fid, number, *, ppm=10.0, transform=None, mask_id="m"):
    f = MagicMock()
    f.id = fid
    f.number = number
    f.pixels_per_meter = ppm
    f.building_transform = transform
    f.mask_file_id = mask_id
    return f


def _building(overrides=None):
    b = MagicMock()
    b.id = 3
    b.transition_overrides = overrides
    return b


_IDENTITY = {"scale": 1.0, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0}


def _write_floor(nav_dir, floor_id, rooms, edges):
    """Serialise a small floor graph to ``floor_{id}_nav.json`` under nav_dir."""
    g = nx.Graph()
    for r in rooms:
        attrs = {k: v for k, v in r.items() if k != "id"}
        g.add_node(r["id"], **attrs)
    for u, v, data in edges:
        g.add_edge(u, v, **data)
    nav_dir.mkdir(exist_ok=True)
    (nav_dir / f"floor_{floor_id}_nav.json").write_text(
        json.dumps(serialize_nav_graph(g, MASK, MASK, 0.1))
    )


def _stair(node_id, x, y):
    return {
        "id": node_id, "type": "room", "room_type": "staircase",
        "pos": (x, y), "connects_up": True, "connects_down": True,
    }


def _room(node_id, x, y):
    return {"id": node_id, "type": "room", "room_type": "room", "pos": (x, y)}


def _corridor(u, v, weight, pts):
    return (u, v, {"weight": weight, "type": "corridor_edge", "pts": pts})


def _make_svc(tmp_path, floors, building):
    floor_repo = AsyncMock()
    floor_repo.list_by_building.return_value = floors
    building_repo = AsyncMock()
    building_repo.get_by_id.return_value = building
    svc = BuildingNavService(
        building_repo=building_repo,
        floor_repo=floor_repo,
        storage=MagicMock(),
        upload_dir=str(tmp_path),
    )
    # Patch the single IO seam → fixed dims (k = nav/floor = 200/200 = 1).
    svc._floor_mask_dims = lambda floor: (MASK, MASK)  # type: ignore[assignment]
    return svc, building_repo


def _two_stair_floors(tmp_path):
    """Floor 10 (room_A → stair s1) + floor 20 (stair s2 → room_B), s1/s2 stacked."""
    nav = tmp_path / "nav"
    _write_floor(
        nav, 10,
        [_room("room_A", 20.0, 20.0), _stair("room_s1", 100.0, 20.0)],
        [_corridor("room_A", "room_s1", 80.0, [(20.0, 20.0), (100.0, 20.0)])],
    )
    _write_floor(
        nav, 20,
        [_stair("room_s2", 100.0, 20.0), _room("room_B", 180.0, 20.0)],
        [_corridor("room_s2", "room_B", 80.0, [(100.0, 20.0), (180.0, 20.0)])],
    )


def _disconnected_wings_with_bridge(tmp_path):
    """Floor 10: two wings (room_A↔s1) and (room_B↔s2) NOT connected to each
    other. Floor 20: a corridor s1u↔s2u bridging the two stacked stair shafts,
    so the only A→B route is up-and-over via floor 20."""
    nav = tmp_path / "nav"
    _write_floor(
        nav, 10,
        [
            _room("room_A", 20.0, 20.0), _stair("room_s1", 100.0, 20.0),
            _room("room_B", 20.0, 180.0), _stair("room_s2", 100.0, 180.0),
        ],
        [
            _corridor("room_A", "room_s1", 80.0, [(20.0, 20.0), (100.0, 20.0)]),
            _corridor("room_B", "room_s2", 80.0, [(20.0, 180.0), (100.0, 180.0)]),
        ],
    )
    _write_floor(
        nav, 20,
        [_stair("room_s1u", 100.0, 20.0), _stair("room_s2u", 100.0, 180.0)],
        [_corridor("room_s1u", "room_s2u", 160.0, [(100.0, 20.0), (100.0, 180.0)])],
    )


@pytest.mark.asyncio
async def test_find_route_stacks_segments_by_elevation(tmp_path):
    _two_stair_floors(tmp_path)
    floors = [
        _floor(10, 1, transform=None),          # reference → aligned by identity
        _floor(20, 2, transform=_IDENTITY),     # aligned
    ]
    svc, _ = _make_svc(tmp_path, floors, _building())

    resp = await svc.find_multifloor_route(3, 10, "A", 20, "B")

    assert resp.status == "success"
    assert len(resp.path_segments) == 2
    by_floor = {s.floor_id: s for s in resp.path_segments}
    # Floor 10 (number 1) sits at elevation 0 → y ≈ 0.1; floor 20 one pitch up
    # (FLOOR_HEIGHT + INTER_FLOOR_GAP_M = 3.2) → y ≈ 3.3, matching the GLB stack.
    assert all(pt[1] == pytest.approx(0.1) for pt in by_floor[10].coordinates_3d)
    assert all(pt[1] == pytest.approx(3.3) for pt in by_floor[20].coordinates_3d)
    assert len(resp.transitions_used) == 1
    assert resp.transitions_used[0].type == "staircase"
    assert resp.total_distance_meters == pytest.approx(19.0)


@pytest.mark.asyncio
async def test_find_route_same_floor_delegates(tmp_path):
    _two_stair_floors(tmp_path)
    floors = [_floor(10, 1, transform=None), _floor(20, 2, transform=_IDENTITY)]
    svc, _ = _make_svc(tmp_path, floors, _building())

    resp = await svc.find_multifloor_route(3, 10, "A", 10, "s1")

    assert resp.status == "success"
    assert len(resp.path_segments) == 1
    assert resp.path_segments[0].floor_id == 10
    assert resp.transitions_used == []


@pytest.mark.asyncio
async def test_find_route_same_floor_routes_up_and_over_when_disconnected(tmp_path):
    """A10_3→A10_2 bug: same-floor endpoints in disconnected wings must route up
    the stairs, across the upper floor, and back down — not fall back to no_path."""
    _disconnected_wings_with_bridge(tmp_path)
    floors = [_floor(10, 1, transform=None), _floor(20, 2, transform=_IDENTITY)]
    svc, _ = _make_svc(tmp_path, floors, _building())

    resp = await svc.find_multifloor_route(3, 10, "A", 10, "B")

    assert resp.status == "success"
    # Up-and-over: floor 10 → floor 20 → floor 10 = 3 segments, 2 stair hops.
    assert [s.floor_id for s in resp.path_segments] == [10, 20, 10]
    assert len(resp.transitions_used) == 2
    assert all(t.type == "staircase" for t in resp.transitions_used)


@pytest.mark.asyncio
async def test_find_route_unaligned_returns_not_aligned(tmp_path):
    _two_stair_floors(tmp_path)
    # Floor 20 has a graph but NO building_transform and is not the reference.
    floors = [_floor(10, 1, transform=None), _floor(20, 2, transform=None)]
    svc, _ = _make_svc(tmp_path, floors, _building())

    resp = await svc.find_multifloor_route(3, 10, "A", 20, "B")

    assert resp.status == "not_aligned"
    assert resp.path_segments == []
    assert resp.message


@pytest.mark.asyncio
async def test_find_route_missing_graph_raises(tmp_path):
    # Only floor 10's graph is written → floor 20 endpoint has no graph.
    nav = tmp_path / "nav"
    _write_floor(
        nav, 10,
        [_room("room_A", 20.0, 20.0), _stair("room_s1", 100.0, 20.0)],
        [_corridor("room_A", "room_s1", 80.0, [(20.0, 20.0), (100.0, 20.0)])],
    )
    floors = [_floor(10, 1, transform=None), _floor(20, 2, transform=_IDENTITY)]
    svc, _ = _make_svc(tmp_path, floors, _building())

    with pytest.raises(FloorNavGraphNotFoundError):
        await svc.find_multifloor_route(3, 10, "A", 20, "B")


@pytest.mark.asyncio
async def test_find_route_missing_building_raises(tmp_path):
    floor_repo = AsyncMock()
    building_repo = AsyncMock()
    building_repo.get_by_id.return_value = None
    svc = BuildingNavService(building_repo, floor_repo, MagicMock(), str(tmp_path))
    with pytest.raises(BuildingNotFoundError):
        await svc.find_multifloor_route(999, 1, "A", 2, "B")


@pytest.mark.asyncio
async def test_list_links_auto_plus_overrides(tmp_path):
    """Auto link s1↔s2 shown disabled by an override; the lone elevator is unmatched."""
    nav = tmp_path / "nav"
    _write_floor(
        nav, 10,
        [
            _room("room_A", 20.0, 20.0),
            _stair("room_s1", 100.0, 20.0),
            {"id": "room_e1", "type": "room", "room_type": "elevator",
             "pos": (300.0, 20.0)},  # no partner → unmatched
        ],
        [_corridor("room_A", "room_s1", 80.0, [(20.0, 20.0), (100.0, 20.0)])],
    )
    _write_floor(
        nav, 20,
        [_stair("room_s2", 100.0, 20.0), _room("room_B", 180.0, 20.0)],
        [_corridor("room_s2", "room_B", 80.0, [(100.0, 20.0), (180.0, 20.0)])],
    )
    overrides = [
        {"lower_floor_id": 10, "lower_node": "room_s1",
         "upper_floor_id": 20, "upper_node": "room_s2", "action": "disable"},
    ]
    floors = [_floor(10, 1, transform=None), _floor(20, 2, transform=_IDENTITY)]
    svc, _ = _make_svc(tmp_path, floors, _building(overrides=overrides))

    resp = await svc.list_links(3)

    assert len(resp.links) == 1
    link = resp.links[0]
    assert link.source == "auto"
    assert link.enabled is False  # the override disabled it
    assert link.type == "staircase"
    assert any(u.node == "room_e1" for u in resp.unmatched)


@pytest.mark.asyncio
async def test_save_overrides_force_invalid_node_raises(tmp_path):
    _two_stair_floors(tmp_path)
    floors = [_floor(10, 1, transform=None), _floor(20, 2, transform=_IDENTITY)]
    svc, building_repo = _make_svc(tmp_path, floors, _building())

    bad = [
        TransitionOverride(
            lower_floor_id=10, lower_node="room_nope",
            upper_floor_id=20, upper_node="room_s2", action="force",
        )
    ]
    with pytest.raises(ValueError):
        await svc.save_overrides(3, bad)
    building_repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_save_overrides_valid_persists(tmp_path):
    _two_stair_floors(tmp_path)
    floors = [_floor(10, 1, transform=None), _floor(20, 2, transform=_IDENTITY)]
    svc, building_repo = _make_svc(tmp_path, floors, _building())

    overrides = [
        TransitionOverride(
            lower_floor_id=10, lower_node="room_s1",
            upper_floor_id=20, upper_node="room_s2", action="disable",
        )
    ]
    resp = await svc.save_overrides(3, overrides)
    assert resp.overrides_count == 1
    building_repo.update.assert_called_once()
