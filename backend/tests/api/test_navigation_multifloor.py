"""
API tests for POST /navigation/multifloor-route.
"""

import pytest
from unittest.mock import AsyncMock, patch

from main import app
from app.api.deps import get_nav_service
from app.models.floor_transition import (
    MultifloorRouteResponse,
    PathSegment3D,
)
from app.services.nav_service import NavService
from app.core.exceptions import NavGraphNotFoundError


def _override_nav(mock_svc):
    app.dependency_overrides[get_nav_service] = lambda: mock_svc


def _clear_nav():
    app.dependency_overrides.pop(get_nav_service, None)


VALID_PAYLOAD = {
    "building_id": "A",
    "from_reconstruction_id": 1,
    "from_room_id": "101",
    "to_reconstruction_id": 2,
    "to_room_id": "201",
}


@pytest.mark.asyncio
async def test_multifloor_route_valid_returns_success(client, auth_headers):
    # Arrange
    mock_svc = AsyncMock(spec=NavService)
    mock_svc.find_multifloor_route.return_value = MultifloorRouteResponse(
        status="success",
        total_distance_meters=45.2,
        estimated_time_seconds=36,
        path_segments=[
            PathSegment3D(
                reconstruction_id=1,
                floor_number=1,
                floor_name="Floor 1",
                coordinates_3d=[[1.2, 0.1, -2.5], [1.8, 0.1, -2.5]],
            ),
            PathSegment3D(
                reconstruction_id=2,
                floor_number=2,
                floor_name="Floor 2",
                coordinates_3d=[[2.4, 3.6, -3.0]],
            ),
        ],
        transitions_used=[],
    )
    _override_nav(mock_svc)
    try:
        response = await client.post(
            "/api/v1/navigation/multifloor-route", json=VALID_PAYLOAD
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["path_segments"]) == 2
    finally:
        _clear_nav()


@pytest.mark.asyncio
async def test_multifloor_route_no_transitions_returns_no_path(client, auth_headers):
    # Arrange
    mock_svc = AsyncMock(spec=NavService)
    mock_svc.find_multifloor_route.return_value = MultifloorRouteResponse(
        status="no_path",
        message="No path found between rooms",
    )
    _override_nav(mock_svc)
    try:
        response = await client.post(
            "/api/v1/navigation/multifloor-route", json=VALID_PAYLOAD
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_path"
        assert data["path_segments"] == []
    finally:
        _clear_nav()


@pytest.mark.asyncio
async def test_multifloor_route_missing_nav_graph_400(client, auth_headers):
    # Arrange — service raises NavGraphNotFoundError
    mock_svc = AsyncMock(spec=NavService)
    mock_svc.find_multifloor_route.side_effect = NavGraphNotFoundError(1)
    _override_nav(mock_svc)
    try:
        response = await client.post(
            "/api/v1/navigation/multifloor-route", json=VALID_PAYLOAD
        )
        assert response.status_code == 400
        assert "Nav graph not found" in response.json()["detail"]
    finally:
        _clear_nav()


@pytest.mark.asyncio
async def test_multifloor_route_invalid_body_422(client, auth_headers):
    # Arrange — missing required fields
    mock_svc = AsyncMock(spec=NavService)
    _override_nav(mock_svc)
    try:
        response = await client.post(
            "/api/v1/navigation/multifloor-route",
            json={"building_id": "A"},  # missing from/to fields
        )
        assert response.status_code == 422
    finally:
        _clear_nav()
