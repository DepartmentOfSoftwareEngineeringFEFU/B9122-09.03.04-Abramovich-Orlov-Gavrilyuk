"""API tests for the building-assembly router (subfeature A).


building_assembly". Style mirrors ``test_floor_assembly_api.py``: the service is
fully mocked and injected via ``app.dependency_overrides[get_building_assembly_service]``;
the tests assert the thin router's contract — status codes (the exception→HTTP
table) and the JSON shapes from../.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from main import app
from app.api.deps import get_building_assembly_service
from app.core.exceptions import BuildingNotFoundError, FloorAssemblyConflictError
from app.models.building_assembly import (
    AssemblyFloor,
    BuildingAssemblyResponse,
    FloorStitchStatus,
    SaveStitchPointsResponse,
    SolveStitchResponse,
    StitchTransform,
)


def _mock_svc() -> MagicMock:
    svc = MagicMock()
    svc.save_stitch_points = AsyncMock()
    svc.solve_stitch = AsyncMock()
    svc.get_assembly = AsyncMock()
    return svc


def _use(svc: MagicMock) -> None:
    app.dependency_overrides[get_building_assembly_service] = lambda: svc


def _clear() -> None:
    app.dependency_overrides.pop(get_building_assembly_service, None)


# PUT /floors/{id}/stitch-points


@pytest.mark.asyncio
async def test_put_stitch_points_200(client, auth_headers):
    svc = _mock_svc()
    svc.save_stitch_points.return_value = SaveStitchPointsResponse(
        floor_id=11, points_count=2, ref_points_count=2
    )
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/11/stitch-points",
            json={
                "points": [
                    {"id": "cp-1", "x": 0.31, "y": 0.42},
                    {"id": "cp-2", "x": 0.77, "y": 0.55},
                ],
                "ref_points": [
                    {"id": "cp-1", "x": 0.29, "y": 0.40},
                    {"id": "cp-2", "x": 0.74, "y": 0.52},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["floor_id"] == 11
        assert data["points_count"] == 2
        assert data["ref_points_count"] == 2
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_stitch_points_unpaired_422(client, auth_headers):
    """Unpaired ids are rejected by the request model (422) — service not called."""
    svc = _mock_svc()
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/11/stitch-points",
            json={
                "points": [{"id": "cp-1", "x": 0.3, "y": 0.4}],
                "ref_points": [{"id": "cp-2", "x": 0.3, "y": 0.4}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        svc.save_stitch_points.assert_not_called()
    finally:
        _clear()


# POST /buildings/{id}/solve-stitch


@pytest.mark.asyncio
async def test_solve_stitch_200(client, auth_headers):
    """Happy solve — the reference/ok/needs_points status strings round-trip."""
    svc = _mock_svc()
    svc.solve_stitch.return_value = SolveStitchResponse(
        building_id=3,
        reference_floor_id=10,
        floors=[
            FloorStitchStatus(
                floor_id=10,
                number=1,
                status="reference",
                building_transform=StitchTransform(
                    scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0,
                    residual_rms_px=0.0, n_points=0,
                ),
                residual_rms_m=0.0,
                elevation_m=0.0,
            ),
            FloorStitchStatus(
                floor_id=11,
                number=2,
                status="ok",
                building_transform=StitchTransform(
                    scale=0.98, rotation_rad=0.0123, tx=14.2, ty=-7.5,
                    residual_rms_px=3.1, n_points=4,
                ),
                residual_rms_m=0.06,
                elevation_m=3.0,
            ),
            FloorStitchStatus(
                floor_id=12,
                number=3,
                status="needs_points",
                building_transform=None,
                residual_rms_m=None,
                elevation_m=6.0,
            ),
        ],
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/buildings/3/solve-stitch", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["building_id"] == 3
        assert data["reference_floor_id"] == 10
        statuses = {f["floor_id"]: f["status"] for f in data["floors"]}
        assert statuses == {10: "reference", 11: "ok", 12: "needs_points"}
        # The B/D shared transform shape round-trips intact.
        upper = next(f for f in data["floors"] if f["floor_id"] == 11)
        assert upper["building_transform"]["scale"] == 0.98
        assert upper["building_transform"]["n_points"] == 4
        assert upper["elevation_m"] == 3.0
        broken = next(f for f in data["floors"] if f["floor_id"] == 12)
        assert broken["building_transform"] is None
    finally:
        _clear()


@pytest.mark.asyncio
async def test_solve_stitch_too_few_floors_409(client, auth_headers):
    svc = _mock_svc()
    svc.solve_stitch.side_effect = FloorAssemblyConflictError(
        "Building needs >= 2 floors to stitch"
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/buildings/3/solve-stitch", headers=auth_headers
        )
        assert resp.status_code == 409
    finally:
        _clear()


# GET /buildings/{id}/assembly


@pytest.mark.asyncio
async def test_get_assembly_200(client, auth_headers):
    """Assembly read echoes mask dims (D's k) + transform + pair_status."""
    svc = _mock_svc()
    svc.get_assembly.return_value = BuildingAssemblyResponse(
        building_id=3,
        reference_floor_id=10,
        floors=[
            AssemblyFloor(
                id=10,
                number=1,
                mask_url="/api/v1/uploads/masks/floor-10-mask.png",
                mask_width=1240,
                mask_height=720,
                pixels_per_meter=37.5,
                elevation_m=0.0,
                points_count=0,
                ref_points_count=0,
                building_transform=None,
                pair_status="reference",
            ),
            AssemblyFloor(
                id=11,
                number=2,
                mask_url="/api/v1/uploads/masks/floor-11-mask.png",
                mask_width=1200,
                mask_height=705,
                pixels_per_meter=36.9,
                elevation_m=3.0,
                points_count=4,
                ref_points_count=4,
                building_transform=StitchTransform(
                    scale=0.98, rotation_rad=0.0123, tx=14.2, ty=-7.5,
                    residual_rms_px=3.1, n_points=4,
                ),
                pair_status="ok",
            ),
        ],
    )
    _use(svc)
    try:
        resp = await client.get("/api/v1/buildings/3/assembly", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["building_id"] == 3
        assert data["reference_floor_id"] == 10
        ref = next(f for f in data["floors"] if f["id"] == 10)
        assert ref["mask_width"] == 1240
        assert ref["mask_height"] == 720
        assert ref["pair_status"] == "reference"
        assert ref["building_transform"] is None
        upper = next(f for f in data["floors"] if f["id"] == 11)
        # mask_width/height are REQUIRED for subfeature D's canvas factor k.
        assert upper["mask_width"] == 1200
        assert upper["mask_height"] == 705
        assert upper["building_transform"]["scale"] == 0.98
        assert upper["pair_status"] == "ok"
    finally:
        _clear()


@pytest.mark.asyncio
async def test_get_assembly_missing_building_404(client, auth_headers):
    svc = _mock_svc()
    svc.get_assembly.side_effect = BuildingNotFoundError(999)
    _use(svc)
    try:
        resp = await client.get("/api/v1/buildings/999/assembly", headers=auth_headers)
        assert resp.status_code == 404
    finally:
        _clear()
