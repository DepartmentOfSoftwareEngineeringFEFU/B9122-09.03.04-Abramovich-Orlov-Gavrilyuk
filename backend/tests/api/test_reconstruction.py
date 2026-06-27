import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from main import app
from app.api.deps import get_reconstruction_service, get_mask_service


def _make_mock_reconstruction(id=1, name="Test", status=3):
    r = MagicMock()
    r.id = id
    r.name = name
    r.status = status
    r.created_at = datetime.utcnow()
    r.created_by = 1
    r.error_message = None
    r.mesh_file_id_glb = None
    r.mesh_file_id_obj = None
    return r


@pytest.mark.asyncio
async def test_get_reconstructions_without_auth_returns_403(client):
    response = await client.get("/api/v1/reconstruction/reconstructions")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_reconstructions_with_auth_returns_200(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.get_saved_reconstructions.return_value = []
    mock_svc.build_mesh_url.return_value = None

    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        response = await client.get(
            "/api/v1/reconstruction/reconstructions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_get_reconstruction_by_id_existing_returns_200(client, auth_headers):
    from app.db.models.reconstruction import Reconstruction
    mock_reconstruction = MagicMock(spec=Reconstruction)
    mock_reconstruction.id = 42
    mock_reconstruction.name = "Test"
    mock_reconstruction.status = 3
    mock_reconstruction.created_at = datetime.utcnow()
    mock_reconstruction.created_by = 1
    mock_reconstruction.saved_at = None
    mock_reconstruction.error_message = None

    mock_svc = AsyncMock()
    mock_svc.get_reconstruction.return_value = mock_reconstruction
    mock_svc.get_status_display = MagicMock(return_value="Готово")
    mock_svc.build_mesh_url = MagicMock(return_value=None)
    mock_svc.get_vectorization_data.return_value = None

    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        response = await client.get(
            "/api/v1/reconstruction/reconstructions/42",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["id"] == 42
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_get_reconstruction_by_id_missing_returns_404(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.get_reconstruction.return_value = None

    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        response = await client.get(
            "/api/v1/reconstruction/reconstructions/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_post_initial_masks_without_auth_returns_403(client):
    response = await client.post(
        "/api/v1/reconstruction/initial-masks",
        json={"file_id": "some-id"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_post_initial_masks_with_auth_returns_200(client, auth_headers):
    from app.models.reconstruction import CalculateMaskResponse
    mock_response = CalculateMaskResponse(
        id="some-id",
        source_upload_file_id="some-id",
        created_at=datetime.utcnow(),
        created_by=1,
        url="/api/v1/uploads/masks/some-id.png",
    )
    mock_svc = AsyncMock()
    mock_svc.calculate_mask_endpoint.return_value = mock_response

    app.dependency_overrides[get_mask_service] = lambda: mock_svc
    try:
        response = await client.post(
            "/api/v1/reconstruction/initial-masks",
            json={"file_id": "some-id"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "some-id"
    finally:
        app.dependency_overrides.pop(get_mask_service, None)


@pytest.mark.asyncio
async def test_post_reconstructions_without_auth_returns_403(client):
    response = await client.post(
        "/api/v1/reconstruction/reconstructions",
        json={"plan_file_id": "p-id", "user_mask_file_id": "m-id"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_delete_reconstruction_missing_id_returns_404(client, auth_headers):
    mock_svc = AsyncMock()
    mock_svc.delete_reconstruction.return_value = False

    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        response = await client.delete(
            "/api/v1/reconstruction/reconstructions/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


# === Section-local control points ===

_CP_URL = "/api/v1/reconstruction/reconstructions/7/control-points"


@pytest.mark.asyncio
async def test_get_reconstruction_control_points_echoes_nullable_image_size(
    client, auth_headers
):
    """The GET echoes image_size_cropped — both the populated and the null case."""
    from app.models.floor_assembly import ControlPoint, ControlPointsResponse

    mock_svc = AsyncMock()
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        # Populated → round-trips as [w, h].
        mock_svc.get_control_points.return_value = ControlPointsResponse(
            reconstruction_id=7,
            image_size_cropped=(800, 600),
            points=[ControlPoint(id="cp-1", x=0.5, y=0.5)],
        )
        resp = await client.get(_CP_URL, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["reconstruction_id"] == 7
        assert data["image_size_cropped"] == [800, 600]
        assert data["points"][0]["id"] == "cp-1"

        # Null → round-trips as null (the field is Optional).
        mock_svc.get_control_points.return_value = ControlPointsResponse(
            reconstruction_id=7, image_size_cropped=None, points=[]
        )
        resp = await client.get(_CP_URL, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["image_size_cropped"] is None
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_get_reconstruction_control_points_missing_returns_404(
    client, auth_headers
):
    mock_svc = AsyncMock()
    mock_svc.get_control_points.return_value = None  # unknown reconstruction
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        resp = await client.get(_CP_URL, headers=auth_headers)
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_put_reconstruction_control_points_happy_returns_200(
    client, auth_headers
):
    from app.models.floor_assembly import ControlPoint, ControlPointsResponse

    mock_svc = AsyncMock()
    mock_svc.save_control_points.return_value = ControlPointsResponse(
        reconstruction_id=7,
        image_size_cropped=(800, 600),
        points=[ControlPoint(id="cp-1", x=0.2, y=0.3)],
    )
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        resp = await client.put(
            _CP_URL,
            json={"points": [{"id": "cp-1", "x": 0.2, "y": 0.3}]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["points"][0]["id"] == "cp-1"
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_put_section_control_points_duplicate_id_returns_422(
    client, auth_headers
):
    """Duplicate control-point ids are rejected by the request model (422)."""
    mock_svc = AsyncMock()
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        resp = await client.put(
            _CP_URL,
            json={
                "points": [
                    {"id": "cp-1", "x": 0.1, "y": 0.1},
                    {"id": "cp-1", "x": 0.2, "y": 0.2},
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        mock_svc.save_control_points.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)


@pytest.mark.asyncio
async def test_put_section_control_points_out_of_range_returns_422(
    client, auth_headers
):
    """A coordinate outside [0, 1] is rejected by the ControlPoint model (422)."""
    mock_svc = AsyncMock()
    app.dependency_overrides[get_reconstruction_service] = lambda: mock_svc
    try:
        resp = await client.put(
            _CP_URL,
            json={"points": [{"id": "cp-1", "x": 1.5, "y": 0.1}]},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        mock_svc.save_control_points.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_reconstruction_service, None)
