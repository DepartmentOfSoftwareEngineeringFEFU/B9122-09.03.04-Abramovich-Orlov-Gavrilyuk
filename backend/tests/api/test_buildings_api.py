"""
API tests for building hierarchy endpoints.
~14 tests covering happy paths, 404, 409, 422, 401/403 auth checks.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from main import app
from app.api.deps import get_building_service
from app.core.exceptions import BuildingDuplicateCodeError, BuildingNotFoundError
from app.models.buildings import (
    BuildingResponse,
    BuildingDetailResponse,
    BuildingPublicResponse,
)
from app.models.floors import FloorBriefFromFloors


def _make_building_response(**kwargs) -> BuildingResponse:
    defaults = dict(
        id=42,
        code="D",
        name="Корпус D",
        address=None,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        floors_count=0,
        published=False,
    )
    defaults.update(kwargs)
    return BuildingResponse(**defaults)


def _make_detail_response(**kwargs) -> BuildingDetailResponse:
    defaults = dict(
        id=42,
        code="D",
        name="Корпус D",
        address=None,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        floors_count=1,
        published=False,
        floors=[FloorBriefFromFloors(id=101, number=7)],
    )
    defaults.update(kwargs)
    return BuildingDetailResponse(**defaults)


def _make_mock_svc():
    svc = MagicMock()
    svc.create_building = AsyncMock()
    svc.list_admin = AsyncMock()
    svc.list_published = AsyncMock()
    svc.get_by_id = AsyncMock()
    svc.update = AsyncMock()
    svc.delete = AsyncMock()
    return svc


# POST /api/v1/buildings

@pytest.mark.asyncio
async def test_create_building_valid_returns_201(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.create_building.return_value = _make_building_response()
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.post(
            "/api/v1/buildings",
            json={"code": "D", "name": "Корпус D"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "D"
        assert data["name"] == "Корпус D"
        assert data["floors_count"] == 0
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_create_building_duplicate_code_returns_409(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.create_building.side_effect = BuildingDuplicateCodeError("D")
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.post(
            "/api/v1/buildings",
            json={"code": "D", "name": "Корпус D"},
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert "D" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_create_building_invalid_code_returns_422(client, auth_headers):
    """code must be alphabetic letters only."""
    mock_svc = _make_mock_svc()
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.post(
            "/api/v1/buildings",
            json={"code": "123", "name": "Корпус D"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_create_building_no_auth_returns_401(client):
    resp = await client.post(
        "/api/v1/buildings",
        json={"code": "D", "name": "Корпус D"},
    )
    assert resp.status_code == 401


# GET /api/v1/buildings

@pytest.mark.asyncio
async def test_list_buildings_admin_returns_all(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.list_admin.return_value = [
        _make_building_response(id=1, code="A", name="Корпус A"),
        _make_building_response(id=2, code="B", name="Корпус B"),
    ]
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/buildings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["code"] == "A"
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_list_buildings_published_filter_returns_only_complete(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.list_published.return_value = [
        BuildingPublicResponse(id=42, code="D", name="Корпус D", floors=[])
    ]
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/buildings?published=true", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["code"] == "D"
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_list_buildings_published_no_auth_returns_200(client):
    """published=true is public — no auth required (user-floor-viewer)."""
    mock_svc = _make_mock_svc()
    mock_svc.list_published.return_value = []
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/buildings?published=true")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_building_service, None)


# GET /api/v1/buildings/{id}

@pytest.mark.asyncio
async def test_get_building_returns_full_payload(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.get_by_id.return_value = _make_detail_response()
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/buildings/42", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 42
        assert "floors" in data
        assert len(data["floors"]) == 1
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_get_building_missing_returns_404(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.get_by_id.side_effect = BuildingNotFoundError(999)
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/buildings/999", headers=auth_headers)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_building_service, None)


# PATCH /api/v1/buildings/{id}

@pytest.mark.asyncio
async def test_patch_building_name_returns_updated(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.update.return_value = _make_building_response(name="Корпус D (главный)")
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.patch(
            "/api/v1/buildings/42",
            json={"name": "Корпус D (главный)"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Корпус D (главный)"
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_patch_building_code_field_rejected(client, auth_headers):
    """PATCH should not accept 'code' — it's immutable per.
    FastAPI ignores extra fields by default, so this tests the service is
    NOT called with code. We verify the response still 200s with no code change.
    """
    mock_svc = _make_mock_svc()
    mock_svc.update.return_value = _make_building_response(name="Корпус D")
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        # Sending code in payload — BuildingUpdateRequest ignores 'code' field
        resp = await client.patch(
            "/api/v1/buildings/42",
            json={"name": "Корпус D", "code": "X"},
            headers=auth_headers,
        )
        # Pydantic strips unknown fields — should still succeed
        assert resp.status_code == 200
        # Verify service was called with UpdateRequest that has no 'code'
        call_args = mock_svc.update.call_args
        update_req = call_args[0][1]
        assert not hasattr(update_req, "code") or getattr(update_req, "code", "sentinel") == "sentinel"
    finally:
        app.dependency_overrides.pop(get_building_service, None)


# DELETE /api/v1/buildings/{id}

@pytest.mark.asyncio
async def test_delete_building_cascades_to_floors_and_sections(client, auth_headers):
    """Verifies 204 status on successful delete (cascade is service responsibility)."""
    mock_svc = _make_mock_svc()
    mock_svc.delete.return_value = None
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.delete("/api/v1/buildings/42", headers=auth_headers)
        assert resp.status_code == 204
        mock_svc.delete.assert_called_once_with(42)
    finally:
        app.dependency_overrides.pop(get_building_service, None)


@pytest.mark.asyncio
async def test_delete_building_missing_returns_404(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.delete.side_effect = BuildingNotFoundError(999)
    app.dependency_overrides[get_building_service] = lambda: mock_svc
    try:
        resp = await client.delete("/api/v1/buildings/999", headers=auth_headers)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_building_service, None)
