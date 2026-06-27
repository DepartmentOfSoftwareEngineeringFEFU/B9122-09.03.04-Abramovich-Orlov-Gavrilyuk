"""Service tests for FloorAssemblyService (-).

Style mirrors the existing service tests (``test_floor_service.py``): repositories
and storage are mocked (``AsyncMock``); ORM rows are plain ``SimpleNamespace``
value objects so ``x.attr is None`` checks behave like real columns (a ``MagicMock``
attribute is a truthy mock, never ``None``).

The IO seams of the service (``_master_pixel_dims``, ``_load_section_mask_for_build``,
``_storage_load_mask_sync_guard``) and the pure ``processing`` callables
(``assemble_floor_mask``, ``build_mesh_from_mask``) are patched so the tests
exercise the *orchestration* logic — id matching, atomicity, the memory-guard
``k`` threading and the warning rules — without touching OpenCV/trimesh or disk.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from pydantic import ValidationError

import app.services.floor_assembly_service as fas
from app.core.exceptions import (
    FileStorageError,
    FloorAssemblyConflictError,
    FloorNotFoundError,
    PreviewNotFoundError,
    SectionNotBoundError,
    SectionNotFoundError,
    SectionValidationError,
)
from app.core.floor_stitching_constants import (
    DEFAULT_CONNECTOR_THICKNESS_M,
    MAX_FLOOR_CANVAS_PX,
)
from app.models.floor_assembly import (
    ConnectorInput,
    CutoutInput,
    MasterControlPoint,
)
from app.processing.registration import SimilarityResult
from app.services.floor_assembly_service import (
    FloorAssemblyService,
    _OkSolve,
    _derive_ppm_floor,
)


# Builders


def _make_service() -> FloorAssemblyService:
    """FloorAssemblyService wired with all-mock collaborators."""
    return FloorAssemblyService(
        floor_repo=AsyncMock(),
        section_repo=AsyncMock(),
        reconstruction_repo=AsyncMock(),
        connector_repo=AsyncMock(),
        storage=AsyncMock(),
    )


def _recon(
    rid: int = 1,
    *,
    control_points=None,
    mask_file_id: str | None = "mask-1",
    ppm: float | None = 50.0,
):
    """Section-local control points live on the bound reconstruction."""
    vectorization_data = (
        json.dumps({"estimated_pixels_per_meter": ppm}) if ppm is not None else None
    )
    return SimpleNamespace(
        id=rid,
        control_points=control_points if control_points is not None else [],
        mask_file_id=mask_file_id,
        vectorization_data=vectorization_data,
    )


def _section(
    sid: int = 10,
    number: int = 1,
    *,
    transform=None,
    master_points=None,
    reconstruction="__bound__",
):
    recon = _recon() if reconstruction == "__bound__" else reconstruction
    return SimpleNamespace(
        id=sid,
        number=number,
        transform=transform,
        control_points=master_points if master_points is not None else [],
        reconstruction=recon,
    )


def _floor(
    fid: int = 1,
    *,
    pixels_per_meter: float | None = 50.0,
    mesh_file_glb: str | None = None,
    schema_image_id: str | None = "schema-1",
    schema_crop_bbox=None,
    nav_cutouts=None,
):
    return SimpleNamespace(
        id=fid,
        pixels_per_meter=pixels_per_meter,
        mesh_file_glb=mesh_file_glb,
        schema_image_id=schema_image_id,
        schema_crop_bbox=schema_crop_bbox,
        schema_image=SimpleNamespace(url="/api/v1/uploads/plans/schema-1.png"),
        nav_cutouts=nav_cutouts,
    )


def _local(cp_id: str, x: float, y: float) -> dict:
    return {"id": cp_id, "x": x, "y": y}


def _master(point_id: str, x: float, y: float) -> dict:
    return {"point_id": point_id, "x": x, "y": y}


class _Capture:
    """Callable double that records the last call's args and returns ``ret``."""

    def __init__(self, ret):
        self.ret = ret
        self.args: tuple = ()
        self.kwargs: dict = {}
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.calls += 1
        return self.ret


def _mask(h: int = 100, w: int = 100) -> np.ndarray:
    return np.full((h, w), 255, np.uint8)


#save master control points


@pytest.mark.asyncio
async def test_save_master_points_rejects_unknown_point_id():
    """A master point_id absent from the section's local ids → SectionValidationError."""
    svc = _make_service()
    section = _section(
        sid=10,
        reconstruction=_recon(control_points=[_local("cp-1", 0.2, 0.2)]),
    )
    svc._section_repo.get_by_id.return_value = section

    with pytest.raises(SectionValidationError):
        await svc.save_section_control_points(
            floor_id=1,
            section_id=10,
            points=[MasterControlPoint(point_id="cp-9", x=0.5, y=0.5)],
        )
    # Orphan rejected BEFORE any persist.
    svc._section_repo.update_master_control_points.assert_not_called()


@pytest.mark.asyncio
async def test_save_master_points_section_not_found_raises_404_type():
    svc = _make_service()
    svc._section_repo.get_by_id.return_value = None
    with pytest.raises(SectionNotFoundError):
        await svc.save_section_control_points(1, 999, points=[])


@pytest.mark.asyncio
async def test_save_master_points_unbound_section_raises_conflict():
    svc = _make_service()
    svc._section_repo.get_by_id.return_value = _section(sid=10, reconstruction=None)
    with pytest.raises(SectionNotBoundError):
        await svc.save_section_control_points(1, 10, points=[])


@pytest.mark.asyncio
async def test_save_master_points_reports_matched_and_unmatched():
    """matched = section ids placed on the master; unmatched = the rest."""
    svc = _make_service()
    section = _section(
        sid=10,
        reconstruction=_recon(
            control_points=[
                _local("cp-1", 0.1, 0.1),
                _local("cp-2", 0.2, 0.2),
                _local("cp-3", 0.3, 0.3),
            ]
        ),
    )
    svc._section_repo.get_by_id.return_value = section

    resp = await svc.save_section_control_points(
        floor_id=1,
        section_id=10,
        points=[
            MasterControlPoint(point_id="cp-1", x=0.5, y=0.5),
            MasterControlPoint(point_id="cp-2", x=0.6, y=0.6),
        ],
    )

    assert set(resp.section_point_ids) == {"cp-1", "cp-2", "cp-3"}
    assert set(resp.matched_ids) == {"cp-1", "cp-2"}
    assert resp.unmatched_ids == ["cp-3"]
    svc._section_repo.update_master_control_points.assert_awaited_once()


#solve transforms


@pytest.mark.asyncio
async def test_solve_no_bound_sections_raises_conflict():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    svc._section_repo.list_by_floor.return_value = [
        _section(sid=10, reconstruction=None)
    ]
    with pytest.raises(FloorAssemblyConflictError):
        await svc.solve_transforms(1)


@pytest.mark.asyncio
async def test_solve_floor_not_found_raises():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = None
    with pytest.raises(FloorNotFoundError):
        await svc.solve_transforms(999)


@pytest.mark.asyncio
async def test_solve_skips_section_with_fewer_than_three_matched_points():
    """< 3 matched ids → status needs_points, no transform; stale transform cleared."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    section = _section(
        sid=10,
        master_points=[_master("cp-1", 0.1, 0.1), _master("cp-2", 0.9, 0.1)],
        reconstruction=_recon(
            control_points=[_local("cp-1", 0.1, 0.1), _local("cp-2", 0.9, 0.1)]
        ),
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))

    resp = await svc.solve_transforms(1)

    assert resp.sections[0].status == "needs_points"
    assert resp.sections[0].transform is None
    assert resp.pixels_per_meter is None
    svc._section_repo.update_transform.assert_awaited_once_with(10, None)
    svc._floor_repo.update_pixels_per_meter.assert_not_called()


@pytest.mark.asyncio
async def test_solve_marks_degenerate_section():
    """3 matched but clustered points (baseline < threshold) → degenerate."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    # Section-local points within ~1.4px on a 100x100 mask → baseline too short.
    section = _section(
        sid=10,
        master_points=[
            _master("cp-1", 0.10, 0.10),
            _master("cp-2", 0.90, 0.10),
            _master("cp-3", 0.50, 0.90),
        ],
        reconstruction=_recon(
            control_points=[
                _local("cp-1", 0.100, 0.100),
                _local("cp-2", 0.105, 0.105),
                _local("cp-3", 0.110, 0.110),
            ]
        ),
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))
    svc._storage_load_mask_sync_guard = MagicMock(return_value=_mask(100, 100))

    resp = await svc.solve_transforms(1)

    assert resp.sections[0].status == "degenerate"
    assert resp.sections[0].transform is None
    svc._section_repo.update_transform.assert_awaited_once_with(10, None)


@pytest.mark.asyncio
async def test_solve_persists_transform_for_valid_section():
    """Well-spread points → status ok, transform + floor ppm persisted (s≈2, ppm≈100)."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    # master = 2 x section (200px master, 100px section) → exact scale 2.0, residual 0.
    section = _section(
        sid=10,
        number=1,
        master_points=[
            _master("cp-1", 0.10, 0.10),
            _master("cp-2", 0.90, 0.10),
            _master("cp-3", 0.50, 0.90),
        ],
        reconstruction=_recon(
            control_points=[
                _local("cp-1", 0.10, 0.10),
                _local("cp-2", 0.90, 0.10),
                _local("cp-3", 0.50, 0.90),
            ],
            ppm=50.0,
        ),
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))
    svc._storage_load_mask_sync_guard = MagicMock(return_value=_mask(100, 100))

    resp = await svc.solve_transforms(1)

    assert resp.sections[0].status == "ok"
    assert resp.anchor_section_id == 10
    assert resp.pixels_per_meter == pytest.approx(100.0, rel=1e-3)
    # update_transform got a real dict (not None) with the fitted scale.
    args = svc._section_repo.update_transform.await_args
    assert args.args[0] == 10
    persisted = args.args[1]
    assert persisted["scale"] == pytest.approx(2.0, rel=1e-3)
    assert persisted["n_points"] == 3
    svc._floor_repo.update_pixels_per_meter.assert_awaited_once()


@pytest.mark.asyncio
async def test_solve_transforms_persists_rotation(monkeypatch):
    """The solved rotation_rad is written into the persisted transform dict."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    section = _section(
        sid=10,
        number=1,
        master_points=[_master(f"cp-{i}", 0.1 * i, 0.1) for i in range(1, 4)],
        reconstruction=_recon(
            control_points=[_local(f"cp-{i}", 0.1 * i, 0.1) for i in range(1, 4)],
            ppm=50.0,
        ),
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))
    svc._storage_load_mask_sync_guard = MagicMock(return_value=_mask(100, 100))
    monkeypatch.setattr(
        fas,
        "solve_similarity",
        MagicMock(
            return_value=SimilarityResult(
                scale=1.0, rotation_rad=0.5, tx=0.0, ty=0.0,
                residual_rms=0.0, n_points=3,
            )
        ),
    )

    resp = await svc.solve_transforms(1)

    # Persisted dict AND the response model both carry the solved rotation.
    persisted = svc._section_repo.update_transform.await_args.args[1]
    assert persisted["rotation_rad"] == pytest.approx(0.5)
    assert resp.sections[0].transform.rotation_rad == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_solve_response_carries_ppm_spread_warning_on_ok_section(monkeypatch):
    """Non-anchor section whose implied ppm differs > PPM_WARN_RATIO → ok + warning."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    sec_a = _section(  # anchor: 4 matched points
        sid=10,
        number=1,
        master_points=[_master(f"cp-{i}", 0.1 * i, 0.1) for i in range(1, 5)],
        reconstruction=_recon(
            control_points=[_local(f"cp-{i}", 0.1 * i, 0.1) for i in range(1, 5)],
            ppm=50.0,
        ),
    )
    sec_b = _section(  # 3 matched points, ppm spread via scale 1.3
        sid=20,
        number=2,
        master_points=[_master(f"cp-{i}", 0.1 * i, 0.2) for i in range(1, 4)],
        reconstruction=_recon(
            control_points=[_local(f"cp-{i}", 0.1 * i, 0.2) for i in range(1, 4)],
            ppm=50.0,
        ),
    )
    svc._section_repo.list_by_floor.return_value = [sec_a, sec_b]
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))
    svc._storage_load_mask_sync_guard = MagicMock(return_value=_mask(100, 100))
    # Deterministic solver: anchor s=1.0 (n=4); other s=1.3 (n=3) → implied ppm 65 vs 50.
    monkeypatch.setattr(
        fas,
        "solve_similarity",
        MagicMock(
            side_effect=[
                SimilarityResult(
                    scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0,
                    residual_rms=0.0, n_points=4,
                ),
                SimilarityResult(
                    scale=1.3, rotation_rad=0.0, tx=0.0, ty=0.0,
                    residual_rms=0.0, n_points=3,
                ),
            ]
        ),
    )

    resp = await svc.solve_transforms(1)

    by_id = {s.section_id: s for s in resp.sections}
    assert resp.anchor_section_id == 10
    assert by_id[20].status == "ok"
    assert by_id[20].warning is not None and "масштаб" in by_id[20].warning.lower()
    assert by_id[10].warning is None  # anchor matches itself exactly


@pytest.mark.asyncio
async def test_solve_high_residual_section_is_ok_with_warning(monkeypatch):
    """Large residual (m) but solvable → status ok + a non-fatal residual warning."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    section = _section(
        sid=10,
        number=1,
        master_points=[_master(f"cp-{i}", 0.1 * i, 0.1) for i in range(1, 4)],
        reconstruction=_recon(
            control_points=[_local(f"cp-{i}", 0.1 * i, 0.1) for i in range(1, 4)],
            ppm=50.0,
        ),
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))
    svc._storage_load_mask_sync_guard = MagicMock(return_value=_mask(100, 100))
    # residual 100px / ppm 50 = 2.0 m >> RESIDUAL_WARN_M (0.5).
    monkeypatch.setattr(
        fas,
        "solve_similarity",
        MagicMock(
            return_value=SimilarityResult(
                scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0, residual_rms=100.0,
                n_points=3,
            )
        ),
    )

    resp = await svc.solve_transforms(1)

    assert resp.sections[0].status == "ok"
    assert resp.sections[0].warning is not None
    assert "неточно" in resp.sections[0].warning.lower()


# ppm derivation helper (pure)


def test_derive_ppm_floor_empty_returns_none():
    assert _derive_ppm_floor([]) == (None, None)


def test_derive_ppm_floor_uses_section_with_most_points():
    results = [
        _OkSolve(section_id=10, section_number=1, n_matched=3, scale=1.0, ppm_section=60.0),
        _OkSolve(section_id=20, section_number=2, n_matched=5, scale=2.0, ppm_section=50.0),
    ]
    anchor_id, ppm = _derive_ppm_floor(results)
    assert anchor_id == 20  # most matched points wins
    assert ppm == pytest.approx(100.0)  # 50 * 2.0


def test_derive_ppm_floor_tie_breaks_on_smaller_section_number():
    results = [
        _OkSolve(section_id=10, section_number=2, n_matched=4, scale=1.0, ppm_section=50.0),
        _OkSolve(section_id=20, section_number=1, n_matched=4, scale=1.0, ppm_section=70.0),
    ]
    anchor_id, _ = _derive_ppm_floor(results)
    assert anchor_id == 20  # same n_matched, smaller number


def test_derive_ppm_floor_skips_sections_without_metric_scale():
    results = [
        _OkSolve(section_id=10, section_number=1, n_matched=4, scale=1.0, ppm_section=None),
    ]
    assert _derive_ppm_floor(results) == (None, None)


#connectors


@pytest.mark.asyncio
async def test_get_connectors_floor_not_found_raises():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = None
    with pytest.raises(FloorNotFoundError):
        await svc.get_connectors(999)


@pytest.mark.asyncio
async def test_replace_connectors_is_atomic():
    """The service delegates to a SINGLE atomic replace_all_for_floor call."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    svc._connector_repo.replace_all_for_floor.return_value = [
        SimpleNamespace(
            id=1, points=[[0.1, 0.1], [0.2, 0.2]], height_m=None,
            thickness_m=None, connects=None,
        )
    ]
    items = [
        ConnectorInput(points=[(0.1, 0.1), (0.2, 0.2)]),
        ConnectorInput(points=[(0.3, 0.3), (0.4, 0.4)]),
    ]

    resp = await svc.replace_connectors(1, items)

    svc._connector_repo.replace_all_for_floor.assert_awaited_once()
    floor_arg, items_arg = svc._connector_repo.replace_all_for_floor.await_args.args
    assert floor_arg == 1
    assert len(items_arg) == 2
    assert resp.floor_id == 1


@pytest.mark.asyncio
async def test_replace_connectors_empty_clears_all():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    svc._connector_repo.replace_all_for_floor.return_value = []

    resp = await svc.replace_connectors(1, [])

    floor_arg, items_arg = svc._connector_repo.replace_all_for_floor.await_args.args
    assert items_arg == []
    assert resp.connectors == []


def test_replace_connectors_line_one_point_returns_422():
    """A 1-vertex connector is rejected at the contract boundary (>= 2 points)."""
    with pytest.raises(ValidationError):
        ConnectorInput(points=[(0.1, 0.1)])


#cutouts (floors.nav_cutouts JSON column)


@pytest.mark.asyncio
async def test_get_cutouts_returns_saved():
    """The JSON column is mapped to indexed Cutout models."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor(
        nav_cutouts=[
            {"points": [[0.4, 0.5], [0.55, 0.5], [0.55, 0.62], [0.4, 0.62]]},
            {"points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]},
        ]
    )

    resp = await svc.get_cutouts(1)

    assert resp.floor_id == 1
    assert [c.id for c in resp.cutouts] == [0, 1]
    assert resp.cutouts[0].points[0] == (0.4, 0.5)


@pytest.mark.asyncio
async def test_cutouts_missing_floor_raises():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = None
    with pytest.raises(FloorNotFoundError):
        await svc.get_cutouts(999)


@pytest.mark.asyncio
async def test_replace_cutouts_valid_persists():
    """replace_cutouts writes the whole list to the nav_cutouts column once."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    saved = [{"points": [[0.4, 0.5], [0.55, 0.5], [0.55, 0.62], [0.4, 0.62]]}]
    svc._floor_repo.update_nav_cutouts.return_value = _floor(nav_cutouts=saved)

    items = [
        CutoutInput(points=[(0.4, 0.5), (0.55, 0.5), (0.55, 0.62), (0.4, 0.62)])
    ]
    resp = await svc.replace_cutouts(1, items)

    svc._floor_repo.update_nav_cutouts.assert_awaited_once()
    floor_arg, payload_arg = svc._floor_repo.update_nav_cutouts.await_args.args
    assert floor_arg == 1
    assert payload_arg == [
        {"points": [[0.4, 0.5], [0.55, 0.5], [0.55, 0.62], [0.4, 0.62]]}
    ]
    assert resp.cutouts[0].id == 0


@pytest.mark.asyncio
async def test_replace_cutouts_empty_clears():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    svc._floor_repo.update_nav_cutouts.return_value = _floor(nav_cutouts=[])

    resp = await svc.replace_cutouts(1, [])

    floor_arg, payload_arg = svc._floor_repo.update_nav_cutouts.await_args.args
    assert payload_arg == []
    assert resp.cutouts == []


@pytest.mark.asyncio
async def test_replace_cutouts_missing_floor_raises():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = None
    with pytest.raises(FloorNotFoundError):
        await svc.replace_cutouts(
            999, [CutoutInput(points=[(0.1, 0.1), (0.2, 0.1), (0.2, 0.2)])]
        )
    svc._floor_repo.update_nav_cutouts.assert_not_called()


#build (preview)


def _patch_build_seams(svc, monkeypatch, *, master_dims=(800, 600)):
    """Patch the build IO/processing seams; return (cap_assemble, cap_build)."""
    svc._master_pixel_dims = AsyncMock(return_value=master_dims)
    cap_assemble = _Capture(np.zeros((master_dims[1], master_dims[0]), np.uint8))
    cap_build = _Capture(object())  # sentinel mesh
    monkeypatch.setattr(fas, "assemble_floor_mask", cap_assemble)
    monkeypatch.setattr(fas, "build_mesh_from_mask", cap_build)
    svc._storage.save_floor_preview_mesh.return_value = (
        "floor-1-preview-abcd1234",
        "/api/v1/uploads/models/floor-1-preview-abcd1234.glb",
    )
    return cap_assemble, cap_build


@pytest.mark.asyncio
async def test_build_no_transformed_sections_raises_conflict():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    svc._section_repo.list_by_floor.return_value = [_section(sid=10, transform=None)]
    with pytest.raises(FloorAssemblyConflictError):
        await svc.build_floor_mesh(1)


@pytest.mark.asyncio
async def test_build_includes_only_ok_sections(monkeypatch):
    """Only sections carrying a transform are built; transform-less ones are ignored."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    ok = _section(sid=10, transform={"scale": 1.0, "tx": 0.0, "ty": 0.0})
    pending = _section(sid=20, transform=None)
    svc._section_repo.list_by_floor.return_value = [ok, pending]
    svc._connector_repo.list_by_floor.return_value = []
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    _patch_build_seams(svc, monkeypatch)

    resp = await svc.build_floor_mesh(1)

    assert resp.included_sections == [10]
    assert 20 not in resp.included_sections


@pytest.mark.asyncio
async def test_build_mesh_passes_cutouts_to_assemble(monkeypatch):
    """floors.nav_cutouts → CutoutRaster list handed to assemble_floor_mask."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor(
        nav_cutouts=[{"points": [[0.4, 0.5], [0.6, 0.5], [0.6, 0.7], [0.4, 0.7]]}]
    )
    section = _section(sid=10, transform={"scale": 1.0, "tx": 0.0, "ty": 0.0})
    svc._section_repo.list_by_floor.return_value = [section]
    svc._connector_repo.list_by_floor.return_value = []
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    cap_assemble, _ = _patch_build_seams(svc, monkeypatch)

    resp = await svc.build_floor_mesh(1)

    assert "cutouts" in cap_assemble.kwargs
    assert len(cap_assemble.kwargs["cutouts"]) == 1
    assert resp.cutout_count == 1


@pytest.mark.asyncio
async def test_build_skips_missing_mask_file_continues(monkeypatch):
    """A section with a transform but no mask file → excluded reason 'mask_missing'."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    a = _section(sid=10, transform={"scale": 1.0, "tx": 0.0, "ty": 0.0})
    b = _section(sid=20, transform={"scale": 1.0, "tx": 0.0, "ty": 0.0})
    svc._section_repo.list_by_floor.return_value = [a, b]
    svc._connector_repo.list_by_floor.return_value = []
    # First section has a mask, second is missing.
    svc._load_section_mask_for_build = MagicMock(side_effect=[_mask(50, 50), None])
    _patch_build_seams(svc, monkeypatch)

    resp = await svc.build_floor_mesh(1)

    assert resp.included_sections == [10]
    assert [e.section_id for e in resp.excluded_sections] == [20]
    assert resp.excluded_sections[0].reason == "mask_missing"


@pytest.mark.asyncio
async def test_build_emits_low_detail_warning_when_cap_clamps_scale(monkeypatch):
    """Section still downsampled below DETAIL_WARN_SCALE after the canvas cap binds
    → a non-fatal low_detail warning. The compared value is the EFFECTIVE scale
    (base_scale * k), so the upscale must be unable to lift it to native."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    section = _section(sid=10, transform={"scale": 0.1, "tx": 0.0, "ty": 0.0})
    svc._section_repo.list_by_floor.return_value = [section]
    svc._connector_repo.list_by_floor.return_value = []
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    # Master long side 4000 = MAX_FLOOR_CANVAS_PX → the cap clamps k to 1.0, so the
    # upscale cannot lift the 0.1× section to native: effective 0.1 < 0.5.
    _patch_build_seams(svc, monkeypatch, master_dims=(4000, 3000))

    resp = await svc.build_floor_mesh(1)

    assert resp.included_sections == [10]
    codes = [(w.section_id, w.code) for w in resp.warnings]
    assert (10, "low_detail") in codes


@pytest.mark.asyncio
async def test_build_upscales_low_res_master_to_render_sections_native(monkeypatch):
    """Round-2 fix: a low-res "карта отсеков" (tiny section scales) is UPSCALED so
    sections rasterise at ~native resolution — otherwise walls collapse to
    sub-pixel and the floor extrudes as blank scraps. k = 1/min(scale) threads into
    canvas, transform and builder ppm; a lifted section gets no low_detail warning."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor(pixels_per_meter=10.0)
    section = _section(sid=10, transform={"scale": 0.2, "tx": 4.0, "ty": 6.0})
    svc._section_repo.list_by_floor.return_value = [section]
    svc._connector_repo.list_by_floor.return_value = []
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    # Master 400x300, scale 0.2 → k = 1/0.2 = 5 (well under the 4000 cap).
    cap_assemble, cap_build = _patch_build_seams(
        svc, monkeypatch, master_dims=(400, 300)
    )

    resp = await svc.build_floor_mesh(1)

    k = 5.0
    # Section lifted to ~native (0.2 * 5 = 1.0×) → NO low_detail warning.
    assert resp.warnings == []
    # (a) canvas dims upscaled by k.
    assert resp.canvas_size_px == (2000, 1500)
    assert cap_assemble.args[1] == (2000, 1500)
    # (b) transform pre-multiplied by k → native-scale warp.
    warp_inputs = cap_assemble.args[0]
    assert warp_inputs[0].scale == pytest.approx(0.2 * k)  # == 1.0
    assert warp_inputs[0].tx == pytest.approx(4.0 * k)
    assert warp_inputs[0].ty == pytest.approx(6.0 * k)
    # (e) builder ppm x k so metres stay correct on the upscaled canvas.
    assert cap_build.kwargs["pixels_per_meter"] == pytest.approx(10.0 * k)
    # Response echoes the UN-scaled metric ppm.
    assert resp.pixels_per_meter == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_canvas_capped_at_max_px_scales_transforms_by_k(monkeypatch):
    """one k threads identically into canvas, transform, connector px+thickness, ppm."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor(pixels_per_meter=50.0)
    section = _section(sid=10, transform={"scale": 2.0, "tx": 10.0, "ty": 20.0})
    svc._section_repo.list_by_floor.return_value = [section]
    svc._connector_repo.list_by_floor.return_value = [
        SimpleNamespace(id=1, points=[[0.5, 0.5], [0.6, 0.6]], thickness_m=None)
    ]
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    # Master long side 5000 > 4000 → k = 4000/5000 = 0.8.
    cap_assemble, cap_build = _patch_build_seams(svc, monkeypatch, master_dims=(5000, 4000))

    resp = await svc.build_floor_mesh(1)

    k = MAX_FLOOR_CANVAS_PX / 5000  # 0.8
    # (a) canvas dims x k, long side capped at 4000.
    assert resp.canvas_size_px == (4000, 3200)
    assert max(resp.canvas_size_px) <= MAX_FLOOR_CANVAS_PX
    # (b) section transform pre-multiplied by k.
    warp_inputs = cap_assemble.args[0]
    assert warp_inputs[0].scale == pytest.approx(2.0 * k)
    assert warp_inputs[0].tx == pytest.approx(10.0 * k)
    assert warp_inputs[0].ty == pytest.approx(20.0 * k)
    # canvas passed to assemble is the k-scaled size.
    assert cap_assemble.args[1] == (4000, 3200)
    # (c) connector points de-normalised against the k-scaled canvas.
    connectors_raster = cap_assemble.args[2]
    assert connectors_raster[0].points_px[0].tolist() == [round(0.5 * 4000), round(0.5 * 3200)]
    # (d) connector thickness (default) k-scaled, floored to >= 1.
    expected_thick = max(1, round(DEFAULT_CONNECTOR_THICKNESS_M * 50.0 * k))
    assert connectors_raster[0].thickness_px == expected_thick
    assert cap_assemble.kwargs["default_wall_thickness_px"] == expected_thick
    # (e) builder ppm x k so metres stay correct on the shrunk canvas.
    assert cap_build.kwargs["pixels_per_meter"] == pytest.approx(50.0 * k)
    # Response echoes the UN-scaled metric ppm (the model's real scale).
    assert resp.pixels_per_meter == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_build_mesh_threads_rotation_into_warp(monkeypatch):
    """rotation_rad from the transform reaches SectionWarpInput, NOT k-scaled."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor(pixels_per_meter=10.0)
    section = _section(
        sid=10,
        transform={"scale": 0.2, "rotation_rad": 0.7, "tx": 4.0, "ty": 6.0},
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._connector_repo.list_by_floor.return_value = []
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    # Master 400x300, scale 0.2 → k = 1 / 0.2 = 5.
    cap_assemble, _ = _patch_build_seams(svc, monkeypatch, master_dims=(400, 300))

    await svc.build_floor_mesh(1)

    warp_inputs = cap_assemble.args[0]
    # scale/tx/ty are pre-multiplied by k; rotation_rad is k-invariant.
    assert warp_inputs[0].scale == pytest.approx(0.2 * 5.0)
    assert warp_inputs[0].rotation_rad == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_build_mesh_legacy_transform_defaults_rotation_zero(monkeypatch):
    """A legacy transform (no rotation_rad key) → warp input rotation_rad == 0.0."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    # Legacy dict: no "rotation_rad" key (solved before rotation existed).
    section = _section(sid=10, transform={"scale": 1.0, "tx": 0.0, "ty": 0.0})
    svc._section_repo.list_by_floor.return_value = [section]
    svc._connector_repo.list_by_floor.return_value = []
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    cap_assemble, _ = _patch_build_seams(svc, monkeypatch)

    await svc.build_floor_mesh(1)

    warp_inputs = cap_assemble.args[0]
    assert warp_inputs[0].rotation_rad == 0.0


@pytest.mark.asyncio
async def test_build_mesh_excludes_misregistered_section_from_k(monkeypatch):
    """A mis-registered section (high residual) must NOT bloat k / the canvas."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor(pixels_per_meter=12.0)
    good = _section(
        sid=10,
        transform={
            "scale": 0.8, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0,
            "residual_rms_px": 6.0,  # 0.5 m at ppm 12 → trusted
        },
    )
    bad = _section(
        sid=20,
        transform={
            "scale": 0.18, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0,
            "residual_rms_px": 437.0,  # 36 m → mis-registered, excluded from k
        },
    )
    svc._section_repo.list_by_floor.return_value = [good, bad]
    svc._connector_repo.list_by_floor.return_value = []
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    # Master 400x300 → un-guarded k would be 1/0.18 ≈ 5.6 (canvas ~2224px); the
    # robust k excludes the bad section → k = 1/0.8 = 1.25.
    cap_assemble, _ = _patch_build_seams(svc, monkeypatch, master_dims=(400, 300))

    resp = await svc.build_floor_mesh(1)

    assert resp.canvas_size_px == (500, 375)  # round(400*1.25), round(300*1.25)
    warp = {w.section_id: w for w in cap_assemble.args[0]}
    assert warp[10].scale == pytest.approx(0.8 * 1.25)  # good section at native


@pytest.mark.asyncio
async def test_build_mesh_returns_preview_without_persisting(monkeypatch):
    """Build writes a preview handle and does NOT touch floors.mesh_file_glb."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    section = _section(sid=10, transform={"scale": 1.0, "tx": 0.0, "ty": 0.0})
    svc._section_repo.list_by_floor.return_value = [section]
    connectors = [
        SimpleNamespace(id=1, points=[[0.2, 0.2], [0.6, 0.2]], thickness_m=None),
        SimpleNamespace(id=2, points=[[0.3, 0.3], [0.7, 0.3]], thickness_m=None),
    ]
    svc._connector_repo.list_by_floor.return_value = connectors
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    _patch_build_seams(svc, monkeypatch)  # master 800x600 → k = 1

    resp = await svc.build_floor_mesh(1)

    assert resp.persisted is False
    assert resp.glb_file_id == "floor-1-preview-abcd1234"
    assert resp.canvas_size_px == (800, 600)  # master dims, k = 1
    assert resp.connector_count == 2
    # Preview must NOT persist the floor model.
    svc._floor_repo.update_mesh_glb.assert_not_called()


#confirm


@pytest.mark.asyncio
async def test_confirm_mesh_promotes_preview_to_floor():
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    svc._storage.promote_floor_preview.return_value = (
        "models/floor-1.glb",
        "/api/v1/uploads/models/floor-1.glb",
    )

    resp = await svc.confirm_floor_mesh(1, "floor-1-preview-abcd1234")

    assert resp.persisted is True
    assert resp.mesh_file_glb == "models/floor-1.glb"
    svc._floor_repo.update_mesh_glb.assert_awaited_once_with(1, "models/floor-1.glb")


@pytest.mark.asyncio
async def test_confirm_mesh_unknown_glb_id_raises_422():
    """A missing/invalid preview handle surfaces as PreviewNotFoundError (→ 422)."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    svc._storage.promote_floor_preview.side_effect = FileStorageError(
        "floor-1-preview-deadbeef", "models/floor-1-preview-deadbeef.glb"
    )

    with pytest.raises(PreviewNotFoundError):
        await svc.confirm_floor_mesh(1, "floor-1-preview-deadbeef")
    svc._floor_repo.update_mesh_glb.assert_not_called()


# Non-displacement: vectorization_data is read-only


@pytest.mark.asyncio
async def test_vectorization_data_never_written_during_assembly(monkeypatch):
    """HARD CONSTRAINT: solve + build + confirm never write vectorization_data.

    The reconstruction repository is the ONLY component that could persist it; the
    assembly flow must never call it at all, and the in-memory string is unchanged.
    """
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    original_vd = json.dumps({"estimated_pixels_per_meter": 50.0})
    recon = _recon(
        control_points=[
            _local("cp-1", 0.10, 0.10),
            _local("cp-2", 0.90, 0.10),
            _local("cp-3", 0.50, 0.90),
        ],
        ppm=50.0,
    )
    recon.vectorization_data = original_vd
    section = _section(
        sid=10,
        transform=None,
        master_points=[
            _master("cp-1", 0.10, 0.10),
            _master("cp-2", 0.90, 0.10),
            _master("cp-3", 0.50, 0.90),
        ],
        reconstruction=recon,
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._connector_repo.list_by_floor.return_value = []
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))
    svc._storage_load_mask_sync_guard = MagicMock(return_value=_mask(100, 100))

    # solve — writes section.transform via the repo; the solved transform makes the
    # section build-eligible below.
    await svc.solve_transforms(1)
    section.transform = svc._section_repo.update_transform.await_args.args[1]

    # build
    svc._load_section_mask_for_build = MagicMock(return_value=_mask(50, 50))
    _patch_build_seams(svc, monkeypatch, master_dims=(200, 200))
    await svc.build_floor_mesh(1)

    # confirm
    svc._storage.promote_floor_preview.return_value = ("models/floor-1.glb", "/u")
    await svc.confirm_floor_mesh(1, "floor-1-preview-abcd1234")

    # The reconstruction repo was never touched → vectorization_data never written.
    assert svc._reconstruction_repo.method_calls == []
    assert recon.vectorization_data == original_vd


@pytest.mark.asyncio
async def test_reconstruction_control_points_roundtrip_unchanged():
    """Solving reads control points; it must not mutate the stored lists."""
    svc = _make_service()
    svc._floor_repo.get_by_id.return_value = _floor()
    local_pts = [
        _local("cp-1", 0.10, 0.10),
        _local("cp-2", 0.90, 0.10),
        _local("cp-3", 0.50, 0.90),
    ]
    master_pts = [
        _master("cp-1", 0.10, 0.10),
        _master("cp-2", 0.90, 0.10),
        _master("cp-3", 0.50, 0.90),
    ]
    section = _section(
        sid=10,
        master_points=master_pts,
        reconstruction=_recon(control_points=local_pts, ppm=50.0),
    )
    svc._section_repo.list_by_floor.return_value = [section]
    svc._master_pixel_dims = AsyncMock(return_value=(200, 200))
    svc._storage_load_mask_sync_guard = MagicMock(return_value=_mask(100, 100))

    await svc.solve_transforms(1)

    assert section.reconstruction.control_points == local_pts
    assert section.control_points == master_pts
