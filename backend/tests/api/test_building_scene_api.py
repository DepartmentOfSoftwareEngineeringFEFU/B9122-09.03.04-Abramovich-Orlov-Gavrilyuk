"""API tests for the building-scene router (subfeature B).

 API section. Style mirrors
``test_building_assembly_api.py``: the service is fully mocked and injected via
``app.dependency_overrides[get_building_scene_service]``; the tests assert the thin
router's contract -- status codes + the JSON shape from../.

Note: this read endpoint is public (optional bearer) so the end-user 3D-routes
screen can load the scene anonymously — a missing token still returns 200.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.deps import get_building_scene_service
from app.core.exceptions import BuildingNotFoundError
from app.models.building_scene import (
    BuildingScene3DResponse,
    ScenePlacement,
    SceneFloor,
)
from main import app


def _mock_svc() -> MagicMock:
    svc = MagicMock()
    svc.get_scene_3d = AsyncMock()
    return svc


def _use(svc: MagicMock) -> None:
    app.dependency_overrides[get_building_scene_service] = lambda: svc


def _clear() -> None:
    app.dependency_overrides.pop(get_building_scene_service, None)


@pytest.mark.asyncio
async def test_get_scene_200_shape(client, auth_headers):
    """Happy read -- the per-floor mesh_url + placement shape round-trips."""
    svc = _mock_svc()
    svc.get_scene_3d.return_value = BuildingScene3DResponse(
        building_id=3,
        reference_floor_id=10,
        floor_height_m=3.0,
        floors=[
            SceneFloor(
                floor_id=10,
                number=1,
                elevation_m=0.0,
                has_mesh=True,
                mesh_url="/api/v1/uploads/models/floor_10.glb",
                placement=ScenePlacement(
                    scale=1.0, rotation_y_rad=0.0, tx=0.0, ty=0.0, tz=0.0
                ),
            ),
            SceneFloor(
                floor_id=11,
                number=2,
                elevation_m=3.0,
                has_mesh=True,
                mesh_url="/api/v1/uploads/models/floor_11.glb",
                placement=ScenePlacement(
                    scale=1.01, rotation_y_rad=0.0349, tx=-0.84, ty=3.0, tz=1.27
                ),
            ),
            SceneFloor(
                floor_id=12,
                number=3,
                elevation_m=6.0,
                has_mesh=False,
                mesh_url=None,
                placement=None,
            ),
        ],
    )
    _use(svc)
    try:
        resp = await client.get("/api/v1/buildings/3/scene-3d", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["building_id"] == 3
        assert data["reference_floor_id"] == 10
        assert data["floor_height_m"] == 3.0
        by_floor = {f["floor_id"]: f for f in data["floors"]}
        # reference floor: identity placement at origin.
        ref = by_floor[10]
        assert ref["has_mesh"] is True
        assert ref["mesh_url"] == "/api/v1/uploads/models/floor_10.glb"
        assert ref["placement"]["scale"] == 1.0
        assert ref["placement"]["ty"] == 0.0
        # solved upper floor: placement carries elevation in ty.
        upper = by_floor[11]
        assert upper["placement"]["ty"] == 3.0
        assert upper["elevation_m"] == 3.0
        # meshless floor: listed, no url, no placement (not an error).
        none_floor = by_floor[12]
        assert none_floor["has_mesh"] is False
        assert none_floor["mesh_url"] is None
        assert none_floor["placement"] is None
    finally:
        _clear()


@pytest.mark.asyncio
async def test_get_scene_missing_building_404(client, auth_headers):
    svc = _mock_svc()
    svc.get_scene_3d.side_effect = BuildingNotFoundError(999)
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/buildings/999/scene-3d", headers=auth_headers
        )
        assert resp.status_code == 404
    finally:
        _clear()


@pytest.mark.asyncio
async def test_get_scene_public_no_auth_200(client):
    """Public read: no bearer token still returns 200 (end-user 3D-routes screen)."""
    svc = _mock_svc()
    svc.get_scene_3d.return_value = BuildingScene3DResponse(
        building_id=3,
        reference_floor_id=10,
        floor_height_m=3.0,
        floors=[
            SceneFloor(
                floor_id=10,
                number=1,
                elevation_m=0.0,
                has_mesh=False,
                mesh_url=None,
                placement=None,
            ),
        ],
    )
    _use(svc)
    try:
        resp = await client.get("/api/v1/buildings/3/scene-3d")
        assert resp.status_code == 200
        svc.get_scene_3d.assert_called_once()
    finally:
        _clear()
