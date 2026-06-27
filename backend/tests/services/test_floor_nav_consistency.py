"""Consistency cross-check — the "no shifts" / drift guard.

``FloorNavService`` recomputes ``k`` / canvas / effective-ppm INDEPENDENTLY of
``FloorAssemblyService.build_floor_mesh`` (no shared method). This test pins the
nav service's geometry to the SAME deterministic formula both code paths use, so
any future drift in either path (e.g. a changed ``k`` clamp) fails here.

Driving ``build_floor_mesh`` end-to-end is heavyweight (trimesh GLB export + file
IO), so — as the plan permits — this asserts the nav service reproduces the
documented ``k`` / canvas arithmetic exactly, for a known ``master_w/h`` +
``min_scale``. The formula under test is identical to
``floor_assembly_service.py`` (``k = min(max(1, 1/min_scale),
MAX_FLOOR_CANVAS_PX/long_side)`` ; ``canvas = round(master * k)`` ; effective ppm
= ``ppm * k``).
"""

import json

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.floor_stitching_constants import (
    CANVAS_TRUST_RESIDUAL_M,
    MAX_FLOOR_CANVAS_PX,
)
from app.processing.floor_assembly import compute_canvas_factor
from app.services.floor_nav_service import FloorNavService


def _expected_k(master_w: int, master_h: int, min_scale: float) -> float:
    long_side = max(master_w, master_h)
    return min(max(1.0, 1.0 / min_scale), MAX_FLOOR_CANVAS_PX / long_side)


@pytest.mark.asyncio
async def test_nav_canvas_and_ppm_match_floor_assembly_build(tmp_path, monkeypatch):
    """nav canvas_size_px + effective ppm == the documented k/canvas formula."""
    master_w, master_h = 200, 150
    ppm = 50.0
    # A small section scale (< 1) forces k = 1/min_scale (the upscale branch) — the
    # exact behaviour build_floor_mesh uses for low-res master schemas.
    min_scale = 0.5

    mask = np.zeros((master_h, master_w), dtype=np.uint8)
    mask[0:4, :] = 255
    mask[-4:, :] = 255
    mask[:, 0:4] = 255
    mask[:, -4:] = 255

    floor = MagicMock()
    floor.id = 1
    floor.pixels_per_meter = ppm
    floor.schema_image_id = "schema-1"
    floor.schema_crop_bbox = None

    section = MagicMock()
    section.id = 10
    section.transform = {"scale": min_scale, "tx": 0.0, "ty": 0.0}
    recon = MagicMock()
    recon.id = 100
    recon.mask_file_id = "mask-100"
    recon.vectorization_data = json.dumps({"rooms": []})
    section.reconstruction = recon

    floor_repo = AsyncMock()
    floor_repo.get_by_id.return_value = floor
    section_repo = AsyncMock()
    section_repo.list_by_floor.return_value = [section]
    connector_repo = AsyncMock()
    connector_repo.list_by_floor.return_value = []
    storage = MagicMock()
    storage.find_file.return_value = "/fake/path.png"

    svc = FloorNavService(
        floor_repo=floor_repo,
        section_repo=section_repo,
        connector_repo=connector_repo,
        storage=storage,
        upload_dir=str(tmp_path),
    )
    # The schema-dims read AND the section-mask load both decode to ``mask`` — so
    # the master canvas is (master_w, master_h) and min_scale comes from transform.
    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imread", lambda *a, **k: mask
    )

    result = await svc.build_floor_nav_graph(1)

    k = _expected_k(master_w, master_h, min_scale)
    expected_canvas = [round(master_w * k), round(master_h * k)]
    expected_eff_ppm = ppm * k
    expected_scale_factor = round(1.0 / expected_eff_ppm, 6)

    assert result["canvas_size_px"] == expected_canvas, (
        "nav canvas must equal round(master * k) — drift vs build_floor_mesh"
    )
    # scale_factor = 1 / (ppm * k) — same effective ppm as the GLB build.
    assert result["scale_factor"] == pytest.approx(expected_scale_factor, abs=1e-6)
    # Recover effective ppm from the reported scale_factor and confirm it matches.
    recovered_eff_ppm = 1.0 / result["scale_factor"]
    assert recovered_eff_ppm == pytest.approx(expected_eff_ppm, rel=1e-4)


@pytest.mark.asyncio
async def test_nav_canvas_excludes_misregistered_section(tmp_path, monkeypatch):
    """A mis-registered section (high residual) does NOT bloat the nav canvas:
    build_floor_nav_graph derives k from the SAME robust helper as
    build_floor_mesh, excluding the bad section from the min-scale."""
    master_w, master_h = 200, 150
    ppm = 12.0

    mask = np.zeros((master_h, master_w), dtype=np.uint8)
    mask[0:4, :] = 255
    mask[-4:, :] = 255
    mask[:, 0:4] = 255
    mask[:, -4:] = 255

    floor = MagicMock()
    floor.id = 1
    floor.pixels_per_meter = ppm
    floor.schema_image_id = "schema-1"
    floor.schema_crop_bbox = None

    def _sec(sid: int, scale: float, residual: float) -> MagicMock:
        s = MagicMock()
        s.id = sid
        s.transform = {
            "scale": scale, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0,
            "residual_rms_px": residual,
        }
        recon = MagicMock()
        recon.id = sid * 10
        recon.mask_file_id = f"mask-{sid}"
        recon.vectorization_data = json.dumps({"rooms": []})
        s.reconstruction = recon
        return s

    good = _sec(10, 0.8, 6.0)    # 0.5 m → trusted
    bad = _sec(20, 0.1, 480.0)   # 40 m → mis-registered, excluded from k

    floor_repo = AsyncMock()
    floor_repo.get_by_id.return_value = floor
    section_repo = AsyncMock()
    section_repo.list_by_floor.return_value = [good, bad]
    connector_repo = AsyncMock()
    connector_repo.list_by_floor.return_value = []
    storage = MagicMock()
    storage.find_file.return_value = "/fake/path.png"

    svc = FloorNavService(
        floor_repo=floor_repo,
        section_repo=section_repo,
        connector_repo=connector_repo,
        storage=storage,
        upload_dir=str(tmp_path),
    )
    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imread", lambda *a, **k: mask
    )

    result = await svc.build_floor_nav_graph(1)

    # Robust k excludes the bad section: k = 1/0.8 = 1.25 (NOT 1/0.1 = 10).
    expected_k = compute_canvas_factor(
        [(0.8, 6.0), (0.1, 480.0)],
        max(master_w, master_h),
        ppm,
        MAX_FLOOR_CANVAS_PX,
        CANVAS_TRUST_RESIDUAL_M,
    )
    assert expected_k == pytest.approx(1.25)
    assert result["canvas_size_px"] == [
        round(master_w * expected_k),
        round(master_h * expected_k),
    ]


@pytest.mark.asyncio
async def test_mesh_and_nav_apply_same_cutouts(tmp_path, monkeypatch):
    """A cutout de-normalises to BYTE-IDENTICAL pixels in both builds.

    Both services compute the same k / canvas (pinned above) and use the same
    ``round(px*canvas_w), round(py*canvas_h)`` de-norm, so a saved cutout reaches
    3D and nav identically — the "one edit, both outputs" guarantee.
    """
    import app.services.floor_assembly_service as fas
    import app.services.floor_nav_service as fns
    from app.services.floor_assembly_service import FloorAssemblyService

    master_w, master_h = 200, 150
    ppm, min_scale = 50.0, 0.5
    cutout_json = [{"points": [[0.4, 0.5], [0.6, 0.5], [0.6, 0.7], [0.4, 0.7]]}]

    mask = np.zeros((master_h, master_w), dtype=np.uint8)
    mask[0:4, :] = 255
    mask[-4:, :] = 255
    mask[:, 0:4] = 255
    mask[:, -4:] = 255

    def _floor() -> MagicMock:
        f = MagicMock()
        f.id = 1
        f.pixels_per_meter = ppm
        f.schema_image_id = "schema-1"
        f.schema_crop_bbox = None
        f.nav_cutouts = cutout_json
        return f

    def _section() -> MagicMock:
        s = MagicMock()
        s.id = 10
        s.transform = {
            "scale": min_scale, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0,
        }
        recon = MagicMock()
        recon.id = 100
        recon.mask_file_id = "mask-100"
        recon.vectorization_data = json.dumps({"rooms": []})
        s.reconstruction = recon
        return s

    captured: dict = {}

    # nav path
    nav_floor_repo = AsyncMock()
    nav_floor_repo.get_by_id.return_value = _floor()
    nav_section_repo = AsyncMock()
    nav_section_repo.list_by_floor.return_value = [_section()]
    nav_connector_repo = AsyncMock()
    nav_connector_repo.list_by_floor.return_value = []
    nav_storage = MagicMock()
    nav_storage.find_file.return_value = "/fake/path.png"
    nav = FloorNavService(
        floor_repo=nav_floor_repo, section_repo=nav_section_repo,
        connector_repo=nav_connector_repo, storage=nav_storage,
        upload_dir=str(tmp_path),
    )
    monkeypatch.setattr(
        "app.services.floor_nav_service.cv2.imread", lambda *a, **k: mask
    )
    nav_orig = fns.assemble_floor_mask

    def nav_spy(*args, **kwargs):
        captured["nav"] = kwargs.get("cutouts")
        return nav_orig(*args, **kwargs)

    monkeypatch.setattr(fns, "assemble_floor_mask", nav_spy)
    await nav.build_floor_nav_graph(1)

    # mesh path (build + storage seams patched — no trimesh / IO)
    mesh = FloorAssemblyService(
        floor_repo=AsyncMock(), section_repo=AsyncMock(),
        reconstruction_repo=AsyncMock(), connector_repo=AsyncMock(),
        storage=AsyncMock(),
    )
    mesh._floor_repo.get_by_id.return_value = _floor()
    mesh._section_repo.list_by_floor.return_value = [_section()]
    mesh._connector_repo.list_by_floor.return_value = []
    mesh._master_pixel_dims = AsyncMock(return_value=(master_w, master_h))
    mesh._load_section_mask_for_build = MagicMock(return_value=mask)
    mesh._storage.save_floor_preview_mesh.return_value = ("id", "/url.glb")
    monkeypatch.setattr(fas, "build_mesh_from_mask", lambda *a, **k: object())
    mesh_orig = fas.assemble_floor_mask

    def mesh_spy(*args, **kwargs):
        captured["mesh"] = kwargs.get("cutouts")
        return mesh_orig(*args, **kwargs)

    monkeypatch.setattr(fas, "assemble_floor_mask", mesh_spy)
    await mesh.build_floor_mesh(1)

    # both rasterise the cutout to the SAME master pixels
    assert captured["nav"] is not None and captured["mesh"] is not None
    assert len(captured["nav"]) == 1 and len(captured["mesh"]) == 1
    np.testing.assert_array_equal(
        captured["nav"][0].points_px, captured["mesh"][0].points_px
    )
