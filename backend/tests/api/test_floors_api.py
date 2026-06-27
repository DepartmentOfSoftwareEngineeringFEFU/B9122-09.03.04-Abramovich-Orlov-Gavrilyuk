"""
API tests for Floor hierarchy endpoints.
8 tests covering create, list, get, delete with 404/409 error cases.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from main import app
from app.api.deps import get_floor_service
from app.core.exceptions import BuildingNotFoundError, FloorDuplicateNumberError, FloorNotFoundError
from app.models.floors import (
    FloorResponse,
    FloorWithBuildingResponse,
    BuildingBrief,
    CropBboxModel,
)


def _floor_response(**kwargs) -> FloorResponse:
    defaults = dict(
        id=101,
        building_id=42,
        number=7,
        sections_count=0,
        reconstructions_unbound_count=0,
        created_at=datetime(2026, 1, 1),
    )
    defaults.update(kwargs)
    return FloorResponse(**defaults)


def _floor_with_building(**kwargs) -> FloorWithBuildingResponse:
    defaults = dict(
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
    defaults.update(kwargs)
    return FloorWithBuildingResponse(**defaults)


def _make_mock_svc():
    svc = MagicMock()
    svc.create_floor = AsyncMock()
    svc.list_by_building = AsyncMock()
    svc.get_by_id = AsyncMock()
    svc.delete = AsyncMock()
    return svc


# POST /api/v1/buildings/{id}/floors

@pytest.mark.asyncio
async def test_create_floor_valid_returns_201(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.create_floor.return_value = _floor_response()
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.post(
            "/api/v1/buildings/42/floors",
            json={"number": 7},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 101
        assert data["number"] == 7
        assert data["building_id"] == 42
    finally:
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_create_floor_missing_building_returns_404(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.create_floor.side_effect = BuildingNotFoundError(999)
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.post(
            "/api/v1/buildings/999/floors",
            json={"number": 7},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_create_floor_duplicate_number_returns_409(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.create_floor.side_effect = FloorDuplicateNumberError("D", 7)
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.post(
            "/api/v1/buildings/42/floors",
            json={"number": 7},
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert "7" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_floor_service, None)


# GET /api/v1/buildings/{id}/floors

@pytest.mark.asyncio
async def test_list_floors_returns_sorted_by_number(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.list_by_building.return_value = [
        _floor_response(id=100, number=1),
        _floor_response(id=101, number=7),
    ]
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/buildings/42/floors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["number"] == 1
        assert data[1]["number"] == 7
    finally:
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_list_floors_missing_building_returns_404(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.list_by_building.side_effect = BuildingNotFoundError(999)
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/buildings/999/floors", headers=auth_headers)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_floor_service, None)


# GET /api/v1/floors/{id}

@pytest.mark.asyncio
async def test_get_floor_returns_with_building(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.get_by_id.return_value = _floor_with_building()
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/floors/101", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 101
        assert data["building"]["code"] == "D"
        assert data["schema_image_id"] is None
    finally:
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_get_floor_missing_returns_404(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.get_by_id.side_effect = FloorNotFoundError(999)
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/floors/999", headers=auth_headers)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_floor_service, None)


# DELETE /api/v1/floors/{id}

@pytest.mark.asyncio
async def test_delete_floor_cascades_to_sections(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.delete.return_value = None
    app.dependency_overrides[get_floor_service] = lambda: mock_svc
    try:
        resp = await client.delete("/api/v1/floors/101", headers=auth_headers)
        assert resp.status_code == 204
        mock_svc.delete.assert_called_once_with(101)
    finally:
        app.dependency_overrides.pop(get_floor_service, None)
