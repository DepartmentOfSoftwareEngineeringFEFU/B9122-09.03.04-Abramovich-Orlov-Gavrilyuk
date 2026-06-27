"""Service tests for BuildingAssemblyService (subfeature A).


BuildingAssemblyService". Style mirrors ``test_floor_assembly_service.py``:
repositories + storage are mocked (``AsyncMock``); ORM rows are plain
``SimpleNamespace`` value objects so ``x.attr is None`` behaves like a real
column (a ``MagicMock`` attribute is a truthy mock, never ``None``).

The single IO seam (``_floor_mask_dims`` — the only method that touches OpenCV /
disk) is monkeypatched so the tests exercise the ORCHESTRATION (id matching,
de-normalisation by each floor's OWN dims, chain compose, atomic persist, status
derivation) without any real image round-trip (Cyrillic-tmp caveat, ../04 Notes).
"""

import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from app.core.exceptions import (
    BuildingNotFoundError,
    FloorAssemblyConflictError,
    FloorNotFoundError,
)
from app.core.floor_stitching_constants import FLOOR_HEIGHT
from app.models.building_assembly import ControlPoint
from app.processing.floor_stack import SimilarityT
from app.services.building_assembly_service import BuildingAssemblyService


# Builders


def _make_service() -> BuildingAssemblyService:
    """BuildingAssemblyService wired with all-mock collaborators."""
    return BuildingAssemblyService(
        building_repo=AsyncMock(),
        floor_repo=AsyncMock(),
        storage=AsyncMock(),
    )


def _floor(
    fid: int,
    number: int,
    *,
    building_id: int = 1,
    stitch_points=None,
    stitch_ref_points=None,
    building_transform=None,
    pixels_per_meter: float | None = 50.0,
    mask_file_id: str | None = "mask-1",
):
    """A Floor ORM stand-in (only the columns the service reads)."""
    return SimpleNamespace(
        id=fid,
        number=number,
        building_id=building_id,
        stitch_points=stitch_points,
        stitch_ref_points=stitch_ref_points,
        building_transform=building_transform,
        pixels_per_meter=pixels_per_meter,
        mask_file_id=mask_file_id,
        mask_file=SimpleNamespace(url=f"/api/v1/uploads/masks/{mask_file_id}.png"),
    )


def _cp_list(points: list[tuple[str, float, float]]) -> list[dict]:
    """``[(id, x, y), ...]`` -> stored ``[{id,x,y}]`` dicts."""
    return [{"id": pid, "x": x, "y": y} for pid, x, y in points]


def _ref_to_floor(t: SimilarityT, pts: np.ndarray) -> np.ndarray:
    """Inverse-map reference-frame points onto a floor's own pixel grid.

    ``p_ref = s R p_floor + (tx,ty)``  =>  ``p_floor = (1/s) R^-1 (p_ref - t)``.
    Mirrors the helper in ``test_floor_stack`` so the service tests can build
    self-consistent per-floor point sets from a known ground-truth transform.
    """
    cos_t = math.cos(t.rotation_rad)
    sin_t = math.sin(t.rotation_rad)
    rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]], dtype=np.float64)
    shifted = pts - np.array([t.tx, t.ty])
    return (shifted @ rot) / t.scale  # rot.T == inverse rotation


# Shared reference-frame anchor points used by the solve tests.
_REF_PTS = np.array(
    [[100.0, 120.0], [400.0, 150.0], [250.0, 500.0], [120.0, 460.0]],
    dtype=np.float64,
)


def _normalized_points(
    floor_to_ref: SimilarityT, dims: tuple[int, int]
) -> list[dict]:
    """Project the shared anchors onto this floor and normalise to [0,1].

    Returns the stored ``[{id,x,y}]`` list (ids ``cp-1..cp-N``) for a floor with
    the given ground-truth ``floor_to_ref`` transform and ``(W, H)`` mask dims.
    """
    w, h = dims
    floor_px = _ref_to_floor(floor_to_ref, _REF_PTS)
    return [
        {"id": f"cp-{i + 1}", "x": float(floor_px[i][0] / w), "y": float(floor_px[i][1] / h)}
        for i in range(len(_REF_PTS))
    ]


#save_stitch_points


@pytest.mark.asyncio
async def test_save_stitch_points_persists():
    """Save persists the upper points + ref points on the UPPER floor's row."""
    svc = _make_service()
    upper = _floor(11, number=2)
    lower = _floor(10, number=1)
    svc._floor_repo.get_by_id = AsyncMock(return_value=upper)
    svc._floor_repo.list_by_building = AsyncMock(return_value=[lower, upper])
    svc._floor_repo.update_stitch_points = AsyncMock(return_value=upper)

    points = [ControlPoint(id="cp-1", x=0.31, y=0.42), ControlPoint(id="cp-2", x=0.77, y=0.55)]
    ref_points = [ControlPoint(id="cp-1", x=0.29, y=0.40), ControlPoint(id="cp-2", x=0.74, y=0.52)]

    resp = await svc.save_stitch_points(11, points, ref_points)

    assert resp.floor_id == 11
    assert resp.points_count == 2
    assert resp.ref_points_count == 2
    svc._floor_repo.update_stitch_points.assert_awaited_once()
    args = svc._floor_repo.update_stitch_points.await_args.args
    assert args[0] == 11
    assert args[1] == [{"id": "cp-1", "x": 0.31, "y": 0.42}, {"id": "cp-2", "x": 0.77, "y": 0.55}]
    assert args[2] == [{"id": "cp-1", "x": 0.29, "y": 0.40}, {"id": "cp-2", "x": 0.74, "y": 0.52}]


@pytest.mark.asyncio
async def test_save_stitch_points_unpaired_ids_raises():
    """Saving on the LOWEST floor (no floor below) is a 409 conflict.

    (The id-pairing rule itself is enforced upstream by the Pydantic request
    model — covered in ``test_building_assembly_api``; the service guards the
    floor-level precondition.)
    """
    svc = _make_service()
    lowest = _floor(10, number=1)
    svc._floor_repo.get_by_id = AsyncMock(return_value=lowest)
    svc._floor_repo.list_by_building = AsyncMock(return_value=[lowest, _floor(11, number=2)])
    svc._floor_repo.update_stitch_points = AsyncMock()

    points = [ControlPoint(id="cp-1", x=0.1, y=0.1)]
    with pytest.raises(FloorAssemblyConflictError):
        await svc.save_stitch_points(10, points, points)
    svc._floor_repo.update_stitch_points.assert_not_called()


@pytest.mark.asyncio
async def test_save_stitch_points_floor_not_found_raises():
    """A missing upper floor is a 404 (FloorNotFoundError)."""
    svc = _make_service()
    svc._floor_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(FloorNotFoundError):
        await svc.save_stitch_points(999, [], [])


#solve_stitch


def _three_solvable_floors() -> list[SimpleNamespace]:
    """Three floors with self-consistent paired points + a known ground truth.

    Floor 0 (id 10) = reference. Each upper floor stores its OWN points (upper-
    normalised) AND the matching ref points (lower-normalised) — exactly the data
    ``_solve_pair`` de-normalises by each floor's OWN dims.
    """
    f0 = SimilarityT(scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0)
    f1 = SimilarityT(scale=1.2, rotation_rad=math.radians(8.0), tx=40.0, ty=-25.0)
    f2 = SimilarityT(scale=0.85, rotation_rad=math.radians(-12.0), tx=-18.0, ty=33.0)
    # Per-floor own mask dims (deliberately DIFFERENT —).
    dims = {10: (600, 700), 11: (520, 705), 12: (640, 680)}

    floor0 = _floor(10, number=1, pixels_per_meter=37.5)
    floor1 = _floor(
        11,
        number=2,
        pixels_per_meter=36.9,
        stitch_points=_normalized_points(f1, dims[11]),
        stitch_ref_points=_normalized_points(f0, dims[10]),
    )
    floor2 = _floor(
        12,
        number=3,
        pixels_per_meter=40.0,
        stitch_points=_normalized_points(f2, dims[12]),
        stitch_ref_points=_normalized_points(f1, dims[11]),
    )
    floor0._dims = dims[10]  # type: ignore[attr-defined]
    floor1._dims = dims[11]  # type: ignore[attr-defined]
    floor2._dims = dims[12]  # type: ignore[attr-defined]
    return [floor0, floor1, floor2]


def _patch_mask_dims(svc: BuildingAssemblyService, monkeypatch) -> None:
    """Stub the single IO seam: return each floor's ``._dims`` (no disk/cv2)."""
    monkeypatch.setattr(
        svc, "_floor_mask_dims", lambda floor: getattr(floor, "_dims", None)
    )


@pytest.mark.asyncio
async def test_solve_three_floors_sets_transforms(monkeypatch):
    """Happy 3-floor solve sets a building_transform on every floor (atomic)."""
    svc = _make_service()
    floors = _three_solvable_floors()
    svc._building_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=1))
    svc._floor_repo.list_by_building = AsyncMock(return_value=floors)
    svc._floor_repo.update_building_transform = AsyncMock()
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.solve_stitch(1)

    assert resp.building_id == 1
    assert resp.reference_floor_id == 10
    by_floor = {s.floor_id: s for s in resp.floors}
    assert by_floor[10].status == "reference"
    assert by_floor[11].status == "ok"
    assert by_floor[12].status == "ok"
    # elevation derived from number (lowest = 0).
    assert by_floor[10].elevation_m == 0.0
    assert by_floor[11].elevation_m == FLOOR_HEIGHT
    assert by_floor[12].elevation_m == 2 * FLOOR_HEIGHT

    # Reference floor's building transform is identity.
    ref_t = by_floor[10].building_transform
    assert ref_t is not None
    assert math.isclose(ref_t.scale, 1.0, abs_tol=1e-9)
    assert math.isclose(ref_t.tx, 0.0, abs_tol=1e-9)

    # Floor 2's COMPOSED transform maps its own pixels onto the reference px:
    # ground truth f2 = scale 0.85, rotation -12deg, translation (-18, 33).
    t2 = by_floor[12].building_transform
    assert t2 is not None
    assert math.isclose(t2.scale, 0.85, abs_tol=1e-3)
    assert math.isclose(t2.rotation_rad, math.radians(-12.0), abs_tol=1e-3)
    assert math.isclose(t2.tx, -18.0, abs_tol=1e-2)
    assert math.isclose(t2.ty, 33.0, abs_tol=1e-2)

    # Persisted exactly once per floor.
    assert svc._floor_repo.update_building_transform.await_count == 3


@pytest.mark.asyncio
async def test_solve_pair_few_points_needs_points(monkeypatch):
    """A pair with < 3 matched points reports ``needs_points`` (no transform)."""
    svc = _make_service()
    floor0 = _floor(10, number=1)
    floor0._dims = (600, 700)  # type: ignore[attr-defined]
    # Upper floor with only TWO paired points (< MIN_CONTROL_POINTS = 3).
    floor1 = _floor(
        11,
        number=2,
        stitch_points=_cp_list([("cp-1", 0.2, 0.2), ("cp-2", 0.8, 0.3)]),
        stitch_ref_points=_cp_list([("cp-1", 0.21, 0.19), ("cp-2", 0.79, 0.31)]),
    )
    floor1._dims = (520, 705)  # type: ignore[attr-defined]
    svc._building_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=1))
    svc._floor_repo.list_by_building = AsyncMock(return_value=[floor0, floor1])
    svc._floor_repo.update_building_transform = AsyncMock()
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.solve_stitch(1)

    by_floor = {s.floor_id: s for s in resp.floors}
    assert by_floor[11].status == "needs_points"
    assert by_floor[11].building_transform is None
    # Persisted None for the unlinked floor (clears any stale transform).
    svc._floor_repo.update_building_transform.assert_any_await(11, None)


@pytest.mark.asyncio
async def test_solve_degenerate_pair_status(monkeypatch):
    """Collinear / coincident points yield a ``degenerate`` pair status."""
    svc = _make_service()
    floor0 = _floor(10, number=1)
    floor0._dims = (600, 700)  # type: ignore[attr-defined]
    # 3 paired points but COINCIDENT (zero baseline) → DegenerateControlPointsError.
    same = _cp_list([("cp-1", 0.5, 0.5), ("cp-2", 0.5, 0.5), ("cp-3", 0.5, 0.5)])
    floor1 = _floor(11, number=2, stitch_points=same, stitch_ref_points=same)
    floor1._dims = (520, 705)  # type: ignore[attr-defined]
    svc._building_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=1))
    svc._floor_repo.list_by_building = AsyncMock(return_value=[floor0, floor1])
    svc._floor_repo.update_building_transform = AsyncMock()
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.solve_stitch(1)

    by_floor = {s.floor_id: s for s in resp.floors}
    assert by_floor[11].status == "degenerate"
    assert by_floor[11].building_transform is None


@pytest.mark.asyncio
async def test_solve_single_floor_raises_conflict():
    """A building with < 2 floors cannot be stitched (409)."""
    svc = _make_service()
    svc._building_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=1))
    svc._floor_repo.list_by_building = AsyncMock(return_value=[_floor(10, number=1)])

    with pytest.raises(FloorAssemblyConflictError):
        await svc.solve_stitch(1)


@pytest.mark.asyncio
async def test_solve_building_not_found_raises():
    """A missing building is a 404 (BuildingNotFoundError)."""
    svc = _make_service()
    svc._building_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(BuildingNotFoundError):
        await svc.solve_stitch(999)


@pytest.mark.asyncio
async def test_solve_persist_is_atomic(monkeypatch):
    """No floor is persisted until the WHOLE pass (load+solve+compose) succeeds.

    The compose step is made to blow up; the test asserts ``update_building_transform``
    was never awaited — proving computation completes before ANY write.
    """
    svc = _make_service()
    floors = _three_solvable_floors()
    svc._building_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=1))
    svc._floor_repo.list_by_building = AsyncMock(return_value=floors)
    svc._floor_repo.update_building_transform = AsyncMock()
    _patch_mask_dims(svc, monkeypatch)

    # Force the compose (last pure step before persistence) to fail.
    def _boom(*_args, **_kwargs):
        raise RuntimeError("compose blew up")

    monkeypatch.setattr(
        "app.services.building_assembly_service.compose_chain_transforms", _boom
    )

    with pytest.raises(RuntimeError):
        await svc.solve_stitch(1)
    svc._floor_repo.update_building_transform.assert_not_called()


#get_assembly


@pytest.mark.asyncio
async def test_get_assembly_returns_transforms_and_elevation(monkeypatch):
    """Assembly read returns per-floor mask dims, elevation, transform, status."""
    svc = _make_service()
    transform = {
        "scale": 0.98,
        "rotation_rad": 0.0123,
        "tx": 14.2,
        "ty": -7.5,
        "residual_rms_px": 3.1,
        "n_points": 4,
    }
    floor0 = _floor(10, number=1, pixels_per_meter=37.5)
    floor0._dims = (1240, 720)  # type: ignore[attr-defined]
    floor1 = _floor(
        11,
        number=2,
        pixels_per_meter=36.9,
        stitch_points=_cp_list(
            [("cp-1", 0.1, 0.1), ("cp-2", 0.2, 0.2), ("cp-3", 0.3, 0.3), ("cp-4", 0.4, 0.4)]
        ),
        stitch_ref_points=_cp_list(
            [("cp-1", 0.1, 0.1), ("cp-2", 0.2, 0.2), ("cp-3", 0.3, 0.3), ("cp-4", 0.4, 0.4)]
        ),
        building_transform=transform,
    )
    floor1._dims = (1200, 705)  # type: ignore[attr-defined]

    svc._building_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=3))
    svc._floor_repo.list_by_building = AsyncMock(return_value=[floor0, floor1])
    # get_by_id (re-fetch for eager mask_file) returns the same rows by id.
    by_id = {10: floor0, 11: floor1}
    svc._floor_repo.get_by_id = AsyncMock(side_effect=lambda fid: by_id[fid])
    _patch_mask_dims(svc, monkeypatch)

    resp = await svc.get_assembly(3)

    assert resp.building_id == 3
    assert resp.reference_floor_id == 10
    by_floor = {f.id: f for f in resp.floors}

    ref = by_floor[10]
    assert ref.mask_width == 1240
    assert ref.mask_height == 720
    assert ref.elevation_m == 0.0
    assert ref.pair_status == "reference"
    assert ref.building_transform is None

    upper = by_floor[11]
    assert upper.mask_width == 1200
    assert upper.mask_height == 705
    assert upper.elevation_m == FLOOR_HEIGHT
    assert upper.points_count == 4
    assert upper.ref_points_count == 4
    assert upper.pair_status == "ok"
    assert upper.building_transform is not None
    assert math.isclose(upper.building_transform.scale, 0.98, abs_tol=1e-9)
    assert upper.building_transform.n_points == 4
    assert upper.mask_url == "/api/v1/uploads/masks/mask-1.png"
    # Saved anchor coords are returned so the editor redraws them on reload.
    assert len(upper.points) == 4
    assert upper.points[0].id == "cp-1"
    assert len(upper.ref_points) == 4
    assert ref.points == []
    assert ref.ref_points == []


@pytest.mark.asyncio
async def test_get_assembly_missing_building_raises():
    """A missing building is a 404 (BuildingNotFoundError)."""
    svc = _make_service()
    svc._building_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(BuildingNotFoundError):
        await svc.get_assembly(999)
