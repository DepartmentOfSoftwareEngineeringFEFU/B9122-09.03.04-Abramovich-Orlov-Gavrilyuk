"""Service tests for BuildingSceneService (subfeature B).

 Style mirrors
``test_building_assembly_service.py``: repositories are ``AsyncMock``; ORM rows are plain
``SimpleNamespace`` value objects (so ``x.attr is None`` behaves like a real column); the
single IO seam ``_floor_mask_dims`` (the only method touching OpenCV/disk) is monkeypatched
to return each floor's ``._dims`` — no real image round-trip (Cyrillic-tmp caveat).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import BuildingNotFoundError
from app.core.floor_stitching_constants import FLOOR_HEIGHT, INTER_FLOOR_GAP_M
from app.services.building_scene_service import BuildingSceneService

_IDENTITY = {"scale": 1.0, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0}


# Builders


def _make_service() -> BuildingSceneService:
    """BuildingSceneService with mock collaborators; ``uploads_url`` is a sync stub."""
    svc = BuildingSceneService(
        building_repo=AsyncMock(),
        floor_repo=AsyncMock(),
        storage=Mock(),
    )
    svc._storage.uploads_url_versioned = Mock(
        side_effect=lambda rel: f"/api/v1/uploads/{rel}"
    )
    return svc


def _floor(
    fid: int,
    number: int,
    *,
    pixels_per_meter: float | None = 10.0,
    mesh_file_glb: str | None = None,
    building_transform: dict | None = None,
    mask_file_id: str | None = "mask-1",
    dims: tuple[int, int] | None = (100, 200),
):
    """A Floor ORM stand-in (only the columns BuildingSceneService reads)."""
    return SimpleNamespace(
        id=fid,
        number=number,
        pixels_per_meter=pixels_per_meter,
        mesh_file_glb=mesh_file_glb,
        building_transform=building_transform,
        mask_file_id=mask_file_id,
        _dims=dims,
    )


def _patch_mask_dims(svc: BuildingSceneService, monkeypatch) -> None:
    """Stub the single IO seam: return each floor's ``._dims`` (no disk/cv2)."""
    monkeypatch.setattr(
        svc, "_floor_mask_dims", lambda floor: getattr(floor, "_dims", None)
    )


def _building(bid: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=bid)


# Tests


async def test_get_scene_missing_building_raises():
    """A missing building is a 404 (BuildingNotFoundError); floors never queried."""
    svc = _make_service()
    svc._building_repo.get_by_id = AsyncMock(return_value=None)
    svc._floor_repo.list_by_building = AsyncMock()

    with pytest.raises(BuildingNotFoundError):
        await svc.get_scene_3d(999)
    svc._floor_repo.list_by_building.assert_not_called()


async def test_get_scene_solved_floor_has_url_and_placement(monkeypatch):
    """A solved upper floor with a mesh gets a mesh_url AND a placement."""
    svc = _make_service()
    ref = _floor(10, number=1)
    upper = _floor(
        11,
        number=2,
        mesh_file_glb="models/floor_11.glb",
        building_transform=_IDENTITY,
    )
    svc._building_repo.get_by_id = AsyncMock(return_value=_building())
    svc._floor_repo.list_by_building = AsyncMock(return_value=[ref, upper])
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.get_scene_3d(1)

    by_floor = {f.floor_id: f for f in resp.floors}
    assert by_floor[11].has_mesh is True
    assert by_floor[11].mesh_url == "/api/v1/uploads/models/floor_11.glb"
    assert by_floor[11].placement is not None
    # equal ppm + equal dims + identity transform → identity horizontal, Y=elevation.
    # Stacking pitch is FLOOR_HEIGHT + INTER_FLOOR_GAP_M so slabs don't intersect.
    assert by_floor[11].placement.scale == pytest.approx(1.0)
    assert by_floor[11].placement.tx == pytest.approx(0.0)
    assert by_floor[11].placement.tz == pytest.approx(0.0)
    assert by_floor[11].placement.ty == pytest.approx(FLOOR_HEIGHT + INTER_FLOOR_GAP_M)


async def test_get_scene_floor_without_mesh_listed_no_url(monkeypatch):
    """A floor with no GLB is still listed, with has_mesh False and mesh_url None."""
    svc = _make_service()
    ref = _floor(10, number=1)
    upper = _floor(11, number=2, mesh_file_glb=None, building_transform=_IDENTITY)
    svc._building_repo.get_by_id = AsyncMock(return_value=_building())
    svc._floor_repo.list_by_building = AsyncMock(return_value=[ref, upper])
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.get_scene_3d(1)

    assert len(resp.floors) == 2
    by_floor = {f.floor_id: f for f in resp.floors}
    assert by_floor[11].has_mesh is False
    assert by_floor[11].mesh_url is None


async def test_get_scene_unsolved_floor_placement_none(monkeypatch):
    """A non-reference floor with no building_transform has placement None."""
    svc = _make_service()
    ref = _floor(10, number=1)
    upper = _floor(
        11, number=2, mesh_file_glb="models/floor_11.glb", building_transform=None
    )
    svc._building_repo.get_by_id = AsyncMock(return_value=_building())
    svc._floor_repo.list_by_building = AsyncMock(return_value=[ref, upper])
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.get_scene_3d(1)

    by_floor = {f.floor_id: f for f in resp.floors}
    assert by_floor[11].has_mesh is True
    assert by_floor[11].placement is None


async def test_get_scene_reference_identity(monkeypatch):
    """The reference (lowest) floor is placed at identity even if unsolved."""
    svc = _make_service()
    ref = _floor(10, number=1, building_transform=None)  # not yet solved
    svc._building_repo.get_by_id = AsyncMock(return_value=_building())
    svc._floor_repo.list_by_building = AsyncMock(return_value=[ref])
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.get_scene_3d(1)

    assert resp.reference_floor_id == 10
    p = resp.floors[0].placement
    assert p is not None
    assert p.scale == pytest.approx(1.0)
    assert p.rotation_y_rad == pytest.approx(0.0)
    assert p.tx == pytest.approx(0.0)
    assert p.ty == pytest.approx(0.0)
    assert p.tz == pytest.approx(0.0)
    assert resp.floors[0].elevation_m == pytest.approx(0.0)


async def test_get_scene_no_floors_empty():
    """A building with no floors returns an empty (non-error) scene."""
    svc = _make_service()
    svc._building_repo.get_by_id = AsyncMock(return_value=_building())
    svc._floor_repo.list_by_building = AsyncMock(return_value=[])

    resp = await svc.get_scene_3d(1)

    assert resp.floors == []
    assert resp.reference_floor_id is None
    assert resp.floor_height_m == pytest.approx(FLOOR_HEIGHT)


async def test_get_scene_mesh_url_from_storage_helper(monkeypatch):
    """mesh_url is produced by FileStorage.uploads_url(rel_path)."""
    svc = _make_service()
    ref = _floor(10, number=1, mesh_file_glb="models/floor_10.glb")
    svc._building_repo.get_by_id = AsyncMock(return_value=_building())
    svc._floor_repo.list_by_building = AsyncMock(return_value=[ref])
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.get_scene_3d(1)

    svc._storage.uploads_url_versioned.assert_any_call("models/floor_10.glb")
    assert resp.floors[0].mesh_url == "/api/v1/uploads/models/floor_10.glb"
