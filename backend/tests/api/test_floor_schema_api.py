"""
API tests for Floor schema editor endpoints.
8 tests covering PUT /schema, POST /extract-walls, PUT /walls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from main import app
from app.api.deps import get_floor_schema_service, get_floor_service
from app.core.exceptions import FloorNotFoundError, FloorSchemaError, ImageProcessingError
from app.models.floors import (
    BuildingBrief,
    FloorWithBuildingResponse,
    CropBboxModel,
)


def _floor_with_schema(**kwargs) -> FloorWithBuildingResponse:
    defaults = dict(
        id=101,
        building_id=42,
        number=7,
        sections_count=0,
        reconstructions_unbound_count=0,
        created_at=datetime(2026, 1, 1),
        building=BuildingBrief(id=42, code="D", name="Корпус D"),
        schema_image_id="abc-uuid",
        schema_image_url="/uploads/abc-uuid.jpg",
        schema_crop_bbox=CropBboxModel(x=0.05, y=0.10, width=0.85, height=0.70, rotation=0),
        wall_polygons=None,
    )
    defaults.update(kwargs)
    return FloorWithBuildingResponse(**defaults)


def _make_schema_svc():
    svc = MagicMock()
    svc.upload_schema = AsyncMock()
    svc.update_crop = AsyncMock()
    svc.extract_walls = AsyncMock()
    svc.update_walls = AsyncMock()
    svc.update_mask = AsyncMock()
    return svc


def _make_floor_svc():
    svc = MagicMock()
    svc.get_by_id = AsyncMock()
    svc.create_floor = AsyncMock()
    svc.list_by_building = AsyncMock()
    svc.delete = AsyncMock()
    return svc


# PUT /api/v1/floors/{id}/schema

@pytest.mark.asyncio
async def test_upload_floor_schema_returns_200(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.upload_schema.return_value = None
    schema_svc.update_crop.return_value = None
    floor_svc = _make_floor_svc()
    floor_svc.get_by_id.return_value = _floor_with_schema()
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/floors/101/schema",
            json={
                "schema_image_id": "abc-uuid",
                "schema_crop_bbox": {
                    "x": 0.05, "y": 0.10,
                    "width": 0.85, "height": 0.70,
                    "rotation": 0,
                },
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_image_id"] == "abc-uuid"
        assert data["schema_image_url"] == "/uploads/abc-uuid.jpg"
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_upload_floor_schema_missing_floor_returns_404(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.upload_schema.side_effect = FloorNotFoundError(999)
    floor_svc = _make_floor_svc()
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/floors/999/schema",
            json={"schema_image_id": "abc-uuid"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_upload_floor_schema_invalid_image_id_returns_422(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.upload_schema.side_effect = FloorSchemaError("Image file 'bad-id' not found in storage")
    floor_svc = _make_floor_svc()
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/floors/101/schema",
            json={"schema_image_id": "bad-id"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert "bad-id" in resp.json()["detail"] or "not found" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


# POST /api/v1/floors/{id}/extract-walls

@pytest.mark.asyncio
async def test_extract_walls_returns_polygons(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.extract_walls.return_value = [
        [[0.10, 0.20], [0.45, 0.20], [0.45, 0.55]],
    ]
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    try:
        resp = await client.post(
            "/api/v1/floors/101/extract-walls",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "wall_polygons" in data
        assert len(data["wall_polygons"]) == 1
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)


@pytest.mark.asyncio
async def test_extract_walls_no_schema_returns_422(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.extract_walls.side_effect = FloorSchemaError("Floor schema image not uploaded")
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    try:
        resp = await client.post(
            "/api/v1/floors/101/extract-walls",
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert "schema" in resp.json()["detail"].lower() or "uploaded" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)


@pytest.mark.asyncio
async def test_extract_walls_missing_floor_returns_404(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.extract_walls.side_effect = FloorNotFoundError(999)
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    try:
        resp = await client.post(
            "/api/v1/floors/999/extract-walls",
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)


# PUT /api/v1/floors/{id}/walls

@pytest.mark.asyncio
async def test_update_walls_manual_returns_200(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.update_walls.return_value = None
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    try:
        polygons = [[[0.10, 0.20], [0.45, 0.20], [0.45, 0.55]]]
        resp = await client.put(
            "/api/v1/floors/101/walls",
            json={"wall_polygons": polygons},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["wall_polygons"] == polygons
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)


@pytest.mark.asyncio
async def test_update_walls_missing_floor_returns_404(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.update_walls.side_effect = FloorNotFoundError(999)
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    try:
        resp = await client.put(
            "/api/v1/floors/999/walls",
            json={"wall_polygons": [[[0.1, 0.2], [0.5, 0.2]]]},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)


# PUT /api/v1/floors/{id}/mask

@pytest.mark.asyncio
async def test_update_floor_mask_returns_200(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.update_mask.return_value = None
    floor_svc = _make_floor_svc()
    floor_svc.get_by_id.return_value = _floor_with_schema(
        mask_file_id="mask-uuid",
        mask_file_url="/api/v1/uploads/masks/mask-uuid.png",
    )
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/floors/101/mask",
            json={"mask_file_id": "mask-uuid"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mask_file_id"] == "mask-uuid"
        assert data["mask_file_url"] == "/api/v1/uploads/masks/mask-uuid.png"
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_update_floor_mask_missing_floor_returns_404(client, auth_headers):
    schema_svc = _make_schema_svc()
    schema_svc.update_mask.side_effect = FloorNotFoundError(999)
    floor_svc = _make_floor_svc()
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/floors/999/mask",
            json={"mask_file_id": "mask-uuid"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)
        app.dependency_overrides.pop(get_floor_service, None)


@pytest.mark.asyncio
async def test_update_floor_mask_empty_id_returns_422(client, auth_headers):
    schema_svc = _make_schema_svc()
    floor_svc = _make_floor_svc()
    app.dependency_overrides[get_floor_schema_service] = lambda: schema_svc
    app.dependency_overrides[get_floor_service] = lambda: floor_svc
    try:
        resp = await client.put(
            "/api/v1/floors/101/mask",
            json={"mask_file_id": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_floor_schema_service, None)
        app.dependency_overrides.pop(get_floor_service, None)
