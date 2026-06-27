"""
Regression tests for auth behavior of building hierarchy endpoints
and the already-public multifloor-route endpoint.

Covers of user-floor-viewer feature:
- GET /api/v1/buildings?published=true is public (no auth required).
- GET /api/v1/buildings  (published=false / default) still requires auth.
- POST /api/v1/navigation/multifloor-route stays public.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from main import app
from app.api.deps import get_building_service, get_nav_service
from app.models.buildings import BuildingPublicResponse, BuildingResponse
from app.models.floor_transition import MultifloorRouteResponse
from app.services.nav_service import NavService


# Helpers


def _make_mock_building_svc() -> MagicMock:
    svc = MagicMock()
    svc.list_admin = AsyncMock(return_value=[])
    svc.list_published = AsyncMock(return_value=[])
    return svc


def _override_building_svc(svc) -> None:
    app.dependency_overrides[get_building_service] = lambda: svc


def _clear_building_svc() -> None:
    app.dependency_overrides.pop(get_building_service, None)


# GET /api/v1/buildings?published=true — public access


@pytest.mark.asyncio
async def test_list_buildings_published_no_auth_returns_200(client):
    # Arrange
    mock_svc = _make_mock_building_svc()
    mock_svc.list_published.return_value = [
        BuildingPublicResponse(id=1, code="D", name="Корпус D", floors=[])
    ]
    _override_building_svc(mock_svc)
    try:
        # Act
        resp = await client.get("/api/v1/buildings?published=true")
        # Assert
        assert resp.status_code == 200
        mock_svc.list_published.assert_awaited_once()
    finally:
        _clear_building_svc()


@pytest.mark.asyncio
async def test_list_buildings_published_invalid_token_returns_200(client):
    """A malformed/garbage Bearer token must be ignored for the public branch."""
    # Arrange
    mock_svc = _make_mock_building_svc()
    mock_svc.list_published.return_value = []
    _override_building_svc(mock_svc)
    try:
        # Act
        resp = await client.get(
            "/api/v1/buildings?published=true",
            headers={"Authorization": "Bearer total-garbage"},
        )
        # Assert
        assert resp.status_code == 200
    finally:
        _clear_building_svc()


@pytest.mark.asyncio
async def test_list_buildings_published_valid_token_returns_200_same_body(client, auth_headers):
    """Same payload regardless of whether a valid Authorization header is present."""
    # Arrange
    mock_svc = _make_mock_building_svc()
    mock_svc.list_published.return_value = [
        BuildingPublicResponse(id=1, code="D", name="Корпус D", floors=[])
    ]
    _override_building_svc(mock_svc)
    try:
        # Act
        resp_no_auth = await client.get("/api/v1/buildings?published=true")
        resp_with_auth = await client.get(
            "/api/v1/buildings?published=true", headers=auth_headers
        )
        # Assert
        assert resp_no_auth.status_code == 200
        assert resp_with_auth.status_code == 200
        assert resp_no_auth.json() == resp_with_auth.json()
    finally:
        _clear_building_svc()


# GET /api/v1/buildings — admin mode still requires auth


@pytest.mark.asyncio
async def test_list_buildings_admin_no_auth_returns_401(client):
    # Arrange
    mock_svc = _make_mock_building_svc()
    _override_building_svc(mock_svc)
    try:
        # Act
        resp = await client.get("/api/v1/buildings?published=false")
        # Assert
        assert resp.status_code == 401
        mock_svc.list_admin.assert_not_awaited()
    finally:
        _clear_building_svc()


@pytest.mark.asyncio
async def test_list_buildings_default_no_auth_returns_401(client):
    """Default (no ?published param) is admin mode → 401 without auth."""
    # Arrange
    mock_svc = _make_mock_building_svc()
    _override_building_svc(mock_svc)
    try:
        # Act
        resp = await client.get("/api/v1/buildings")
        # Assert
        assert resp.status_code == 401
    finally:
        _clear_building_svc()


@pytest.mark.asyncio
async def test_list_buildings_admin_valid_token_returns_200(client, auth_headers):
    # Arrange
    from datetime import datetime

    mock_svc = _make_mock_building_svc()
    mock_svc.list_admin.return_value = [
        BuildingResponse(
            id=1,
            code="A",
            name="Корпус A",
            address=None,
            created_at=datetime(2026, 1, 1, 10, 0, 0),
            floors_count=0,
            published=False,
        )
    ]
    _override_building_svc(mock_svc)
    try:
        # Act
        resp = await client.get("/api/v1/buildings", headers=auth_headers)
        # Assert
        assert resp.status_code == 200
        mock_svc.list_admin.assert_awaited_once()
    finally:
        _clear_building_svc()


# POST /api/v1/navigation/multifloor-route — public baseline


@pytest.mark.asyncio
async def test_multifloor_route_no_auth_returns_200(client):
    """The endpoint has no auth dependency — verify status != 401.

    A real graph traversal needs a fully seeded DB (floor transitions, sections,
    reconstructions, navigation graphs). To keep this regression cheap we mock
    NavService and only assert "no 401" — which is sufficient to detect a
    regression where Depends(security) is added back to the route.
    """
    # Arrange
    mock_svc = AsyncMock(spec=NavService)
    mock_svc.find_multifloor_route.return_value = MultifloorRouteResponse(
        status="no_path",
        message="stub",
    )
    app.dependency_overrides[get_nav_service] = lambda: mock_svc
    try:
        # Act
        resp = await client.post(
            "/api/v1/navigation/multifloor-route",
            json={
                "building_id": "A",
                "from_reconstruction_id": 1,
                "from_room_id": "101",
                "to_reconstruction_id": 2,
                "to_room_id": "201",
            },
        )
        # Assert
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_nav_service, None)
