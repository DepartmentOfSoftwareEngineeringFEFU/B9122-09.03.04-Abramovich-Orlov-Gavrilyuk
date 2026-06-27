import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from main import app
from app.api.deps import get_reconstruction_service
from app.models.domain import VectorizationResult
from app.services.reconstruction_service import ReconstructionService


def _minimal_vectorization_result() -> VectorizationResult:
    return VectorizationResult(
        walls=[],
        rooms=[],
        doors=[],
        text_blocks=[],
        image_size_original=(800, 600),
        image_size_cropped=(800, 600),
    )


def _make_mock_svc(vectorization_result=None, update_result=None):
    svc = AsyncMock()
    svc.get_vectorization_data.return_value = vectorization_result
    svc.update_vectorization_data.return_value = update_result
    svc.get_status_display = MagicMock(return_value="Готово")
    svc.build_mesh_url = MagicMock(return_value=None)
    return svc


# --- GET /reconstructions/{id}/vectors ---

@pytest.mark.asyncio
async def test_get_vectors_success(client, auth_headers):
    mock_svc = _make_mock_svc(vectorization_result=_minimal_vectorization_result())
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        response = await client.get(
            "/api/v1/reconstruction/reconstructions/1/vectors",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["image_size_original"] == [800, 600]
        assert "walls" in data
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_get_vectors_not_found(client, auth_headers):
    mock_svc = _make_mock_svc(vectorization_result=None)
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        response = await client.get(
            "/api/v1/reconstruction/reconstructions/99/vectors",
            headers=auth_headers,
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


# --- PUT /reconstructions/{id}/vectors ---

@pytest.mark.asyncio
async def test_put_vectors_success(client, auth_headers):
    mock_rec = MagicMock()
    mock_rec.id = 1
    mock_svc = _make_mock_svc(update_result=mock_rec)
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        payload = _minimal_vectorization_result().model_dump()
        response = await client.put(
            "/api/v1/reconstruction/reconstructions/1/vectors",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Vectorization data updated"
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_put_vectors_not_found(client, auth_headers):
    mock_svc = _make_mock_svc(update_result=None)
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        payload = _minimal_vectorization_result().model_dump()
        response = await client.put(
            "/api/v1/reconstruction/reconstructions/99/vectors",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


# --- POST /reconstructions: elevator floor fields (floor-transition-tools) ---

def _mesh_request_with_elevator(floor_from=1, floor_to=10, floors_excluded=None):
    return {
        "plan_file_id": "plan_1",
        "user_mask_file_id": "mask_1",
        "rooms": [
            {
                "id": "elev_1",
                "name": "Лифт",
                "room_type": "elevator",
                "x": 0.4, "y": 0.4, "width": 0.1, "height": 0.1,
                "center": {"x": 0.45, "y": 0.45},
                "floor_from": floor_from,
                "floor_to": floor_to,
                "floors_excluded": floors_excluded or [],
            }
        ],
    }


@pytest.mark.asyncio
async def test_calculate_mesh_accepts_elevator_fields_200(client, auth_headers):
    rec = MagicMock()
    rec.id = 42
    rec.name = ""
    rec.status = 3
    rec.created_at = datetime(2026, 1, 1)
    rec.created_by = 1
    rec.mask_file_id = "mask_1"
    rec.plan_file = None
    rec.mask_file = None
    rec.error_message = None

    mock_svc = AsyncMock()
    mock_svc.build_mesh.return_value = rec
    mock_svc.get_reconstruction.return_value = rec
    mock_svc.get_vectorization_data.return_value = None
    mock_svc.get_status_display = MagicMock(return_value="Готово")
    mock_svc.build_mesh_url = MagicMock(return_value=None)

    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        response = await client.post(
            "/api/v1/reconstruction/reconstructions",
            headers=auth_headers,
            json=_mesh_request_with_elevator(floors_excluded=[5]),
        )
        assert response.status_code == 200, response.text
        # Elevator fields must pass through the endpoint to build_mesh.
        sent_rooms = mock_svc.build_mesh.call_args.kwargs["manual_rooms"]
        assert sent_rooms[0]["floor_from"] == 1
        assert sent_rooms[0]["floor_to"] == 10
        assert sent_rooms[0]["floors_excluded"] == [5]
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_calculate_mesh_invalid_elevator_range_rejected(client, auth_headers):
    # Real service + mocked deps: the up-front validator raises ValueError on a
    # bad range, which the endpoint maps to 400 (no DB record created).
    real_svc = ReconstructionService(repo=AsyncMock(), storage=AsyncMock())
    app.dependency_overrides[get_reconstruction_service] = lambda: real_svc
    try:
        response = await client.post(
            "/api/v1/reconstruction/reconstructions",
            headers=auth_headers,
            json=_mesh_request_with_elevator(floor_from=8, floor_to=3),
        )
        assert response.status_code == 400, response.text
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
