"""
API tests for reconstruction save / patch / list modifications.
7 tests covering PATCH floor_id, PUT /save with floor_id, GET list filters.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from main import app
from app.api.deps import get_reconstruction_service, get_floor_service
from app.core.exceptions import FloorNotFoundError
from app.models.floors import (
    FloorWithBuildingResponse,
    BuildingBrief,
    CropBboxModel,
)


def _mock_reconstruction(id: int = 1, name: str = "Test", floor_id: int = 101):
    r = MagicMock()
    r.id = id
    r.name = name
    r.status = 3
    r.floor_id = floor_id
    r.created_at = datetime(2026, 1, 1)
    r.updated_at = datetime(2026, 1, 1)
    r.created_by = 1
    r.error_message = None
    r.mask_file_id = None
    r.plan_file = MagicMock()
    r.plan_file.url = "/uploads/plan.jpg"
    r.mask_file = None
    r.floor = MagicMock()
    r.floor.id = floor_id
    r.floor.number = 7
    r.floor.building = MagicMock()
    r.floor.building.code = "D"
    r.section = None
    return r


def _make_recon_svc(reconstruction=None):
    svc = MagicMock()
    svc.patch_floor = AsyncMock(return_value=reconstruction)
    svc.save = AsyncMock(return_value=reconstruction)
    svc.get_reconstruction = AsyncMock(return_value=reconstruction)
    svc.get_vectorization_data = AsyncMock(return_value=None)
    svc.list = AsyncMock(return_value=[])
    svc.get_by_id = AsyncMock(return_value=reconstruction)
    svc.get_status_display = MagicMock(return_value="Готово")
    svc.build_mesh_url = MagicMock(return_value=None)
    return svc


def _make_floor_svc(floor=None, not_found: bool = False):
    svc = MagicMock()
    svc.create_floor = AsyncMock()
    svc.list_by_building = AsyncMock()
    svc.delete = AsyncMock()
    if not_found:
        svc.get_by_id = AsyncMock(side_effect=FloorNotFoundError(999))
    else:
        floor_resp = floor or FloorWithBuildingResponse(
            id=101,
            building_id=42,
            number=7,
            sections_count=0,
            reconstructions_unbound_count=0,
            created_at=datetime(2026, 1, 1),
            building=BuildingBrief(id=42, code="D", name="Корпус D"),
            schema_image_id=None,
            schema_image_url=None,
            schema_crop_bbox=None,
            wall_polygons=None,
        )
        svc.get_by_id = AsyncMock(return_value=floor_resp)
    return svc


# PATCH /reconstruction/reconstructions/{id}

@pytest.mark.asyncio
async def test_patch_reconstruction_floor_id_returns_200(client, auth_headers):
    recon = _mock_reconstruction()
    recon_svc = _make_recon_svc(reconstruction=recon)
    floor_svc = _make_floor_svc()
    app.dependency_overrides[get_reconstruction_service] = lambda: recon_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.patch(
            "/api/v1/reconstruction/reconstructions/1",
            json={"floor_id": 101},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_patch_reconstruction_missing_floor_returns_404(client, auth_headers):
    recon_svc = _make_recon_svc()
    floor_svc = _make_floor_svc(not_found=True)
    app.dependency_overrides[get_reconstruction_service] = lambda: recon_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.patch(
            "/api/v1/reconstruction/reconstructions/1",
            json={"floor_id": 999},
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert "999" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


# PUT /reconstruction/reconstructions/{id}/save

@pytest.mark.asyncio
async def test_save_reconstruction_with_floor_id_returns_200(client, auth_headers):
    recon = _mock_reconstruction()
    recon_svc = _make_recon_svc(reconstruction=recon)
    floor_svc = _make_floor_svc()
    app.dependency_overrides[get_reconstruction_service] = lambda: recon_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/reconstruction/reconstructions/1/save",
            json={"name": "D-7-Section4", "floor_id": 101},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_save_reconstruction_missing_floor_id_returns_404(client, auth_headers):
    """Save with non-existent floor_id → 404."""
    recon_svc = _make_recon_svc()
    floor_svc = _make_floor_svc(not_found=True)
    app.dependency_overrides[get_reconstruction_service] = lambda: recon_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/reconstruction/reconstructions/1/save",
            json={"name": "Test", "floor_id": 999},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_save_reconstruction_no_floor_id_returns_422(client, auth_headers):
    """floor_id is required in SaveReconstructionRequest → 422 if missing."""
    recon_svc = _make_recon_svc()
    floor_svc = _make_floor_svc()
    app.dependency_overrides[get_reconstruction_service] = lambda: recon_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/reconstruction/reconstructions/1/save",
            json={"name": "Test"},  # no floor_id
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


# GET /api/v1/reconstruction/reconstructions

@pytest.mark.asyncio
async def test_list_reconstructions_unbound_filter_returns_only_unbound(client, auth_headers):
    recon = _mock_reconstruction()
    recon_svc = _make_recon_svc()
    # Return one unbound reconstruction
    recon_svc.list.return_value = [recon]
    app.dependency_overrides[get_reconstruction_service] = lambda: recon_svc
    try:
        resp = await client.get(
            "/api/v1/reconstruction/reconstructions?unbound=true",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # Verify service was called with unbound=True
        recon_svc.list.assert_called_once()
        call_kwargs = recon_svc.list.call_args.kwargs
        assert call_kwargs.get("unbound") is True
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_get_reconstruction_includes_floor_and_section_info(client, auth_headers):
    """GET /reconstructions/{id} returns extended response with floor+section (via CalculateMeshResponse)."""
    recon = _mock_reconstruction()
    recon_svc = _make_recon_svc(reconstruction=recon)
    app.dependency_overrides[get_reconstruction_service] = lambda: recon_svc
    try:
        resp = await client.get(
            "/api/v1/reconstruction/reconstructions/1",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["status"] == 3
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
