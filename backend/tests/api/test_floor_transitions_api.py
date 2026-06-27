"""
API tests for floor transitions CRUD — full stack with in-memory SQLite.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from main import app
from app.api.deps import get_floor_transition_service
from app.core.exceptions import FloorTransitionNotFoundError, FloorTransitionError


def _make_transition_mock(id: int = 1):
    t = MagicMock()
    t.id = id
    t.name = "Лестница А"
    t.building_id = "A"
    t.from_reconstruction_id = 1
    t.from_x = 0.25
    t.from_y = 0.60
    t.to_reconstruction_id = 2
    t.to_x = 0.30
    t.to_y = 0.65
    t.created_at = datetime(2026, 4, 24, 12, 0, 0)
    return t


def _override_service(mock_svc):
    app.dependency_overrides[get_floor_transition_service] = lambda: mock_svc


def _clear_overrides():
    app.dependency_overrides.pop(get_floor_transition_service, None)


VALID_PAYLOAD = {
    "name": "Лестница А",
    "from_reconstruction_id": 1,
    "from_x": 0.25,
    "from_y": 0.60,
    "to_reconstruction_id": 2,
    "to_x": 0.30,
    "to_y": 0.65,
}


@pytest.mark.asyncio
async def test_create_transition_valid_201(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.create.return_value = _make_transition_mock(1)
    _override_service(mock_svc)
    try:
        response = await client.post("/api/v1/floor-transitions/", json=VALID_PAYLOAD)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Лестница А"
        assert data["id"] == 1
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_create_transition_missing_fields_422(client, auth_headers):
    mock_svc = AsyncMock()
    _override_service(mock_svc)
    try:
        response = await client.post("/api/v1/floor-transitions/", json={"name": "X"})
        assert response.status_code == 422
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_create_transition_same_reconstruction_400(client, auth_headers):
    mock_svc = AsyncMock()
    _override_service(mock_svc)
    try:
        payload = {**VALID_PAYLOAD, "to_reconstruction_id": 1}
        response = await client.post("/api/v1/floor-transitions/", json=payload)
        assert response.status_code == 422
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_create_transition_unknown_from_reconstruction_404(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.create.side_effect = FloorTransitionError("Reconstruction 99 not found")
    _override_service(mock_svc)
    try:
        response = await client.post("/api/v1/floor-transitions/", json=VALID_PAYLOAD)
        assert response.status_code == 404
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_create_transition_unknown_to_reconstruction_404(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.create.side_effect = FloorTransitionError("Reconstruction 99 not found")
    _override_service(mock_svc)
    try:
        response = await client.post("/api/v1/floor-transitions/", json=VALID_PAYLOAD)
        assert response.status_code == 404
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_list_transitions_by_building_200(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.get_by_building.return_value = [_make_transition_mock(1)]
    _override_service(mock_svc)
    try:
        response = await client.get("/api/v1/floor-transitions/?building_id=A")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Лестница А"
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_list_transitions_empty_building_returns_empty(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.get_by_building.return_value = []
    _override_service(mock_svc)
    try:
        response = await client.get("/api/v1/floor-transitions/?building_id=Z")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_delete_transition_existing_204(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.delete.return_value = None
    _override_service(mock_svc)
    try:
        response = await client.delete("/api/v1/floor-transitions/1")
        assert response.status_code == 204
    finally:
        _clear_overrides()


@pytest.mark.asyncio
async def test_delete_transition_nonexistent_404(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.delete.side_effect = FloorTransitionNotFoundError(999)
    _override_service(mock_svc)
    try:
        response = await client.delete("/api/v1/floor-transitions/999")
        assert response.status_code == 404
    finally:
        _clear_overrides()
