"""
API tests for stitching endpoints.
"""
import pytest
from unittest.mock import AsyncMock

from main import app
from app.api.deps import get_stitching_service
from app.models.stitching import StitchingResponse


def _make_mock_stitching_service(stitch_result=None, should_raise=None):
    """Create mock StitchingService."""
    svc = AsyncMock()
    if should_raise:
        svc.stitch_plans.side_effect = should_raise
    else:
        svc.stitch_plans.return_value = stitch_result
    return svc


# --- POST /stitching/ ---

@pytest.mark.asyncio
async def test_post_stitching_valid_request_returns_201(client, auth_headers):
    """Test successful stitching with valid request."""
    # Arrange
    mock_response = StitchingResponse(
        id=123,
        name="Merged Floor 3",
        status=3,
        source_reconstruction_ids=[1, 2],
        building_id="550e8400-e29b-41d4-a716-446655440000",
        floor_number=3,
        rooms_count=5,
        walls_count=20,
        warnings=None,
    )
    mock_svc = _make_mock_stitching_service(stitch_result=mock_response)
    app.dependency_overrides[get_stitching_service] = lambda: mock_svc

    request = {
        "name": "Merged Floor 3",
        "building_id": "550e8400-e29b-41d4-a716-446655440000",
        "floor_number": 3,
        "source_plans": [
            {
                "reconstruction_id": "1",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 0,
            },
            {
                "reconstruction_id": "2",
                "transform": {
                    "translate_x": 500,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 1,
            },
        ],
    }

    try:
        # Act
        response = await client.post("/api/v1/stitching/", json=request, headers=auth_headers)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Merged Floor 3"
        assert data["rooms_count"] == 5
        assert data["walls_count"] == 20
    finally:
        app.dependency_overrides.pop(get_stitching_service, None)


@pytest.mark.asyncio
async def test_post_stitching_invalid_transform_returns_400(client, auth_headers):
    """Test stitching with invalid transform (negative scale)."""
    # Arrange
    request = {
        "name": "Invalid Transform",
        "building_id": "550e8400-e29b-41d4-a716-446655440000",
        "floor_number": 1,
        "source_plans": [
            {
                "reconstruction_id": "1",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": -1.0,  # Invalid: must be > 0
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 0,
            },
            {
                "reconstruction_id": "2",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 1,
            },
        ],
    }

    # Act
    response = await client.post("/api/v1/stitching/", json=request, headers=auth_headers)

    # Assert
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_post_stitching_less_than_two_plans_returns_400(client, auth_headers):
    """Test stitching with less than 2 source plans."""
    # Arrange
    request = {
        "name": "Single Plan",
        "building_id": "550e8400-e29b-41d4-a716-446655440000",
        "floor_number": 1,
        "source_plans": [
            {
                "reconstruction_id": "1",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 0,
            },
        ],
    }

    # Act
    response = await client.post("/api/v1/stitching/", json=request, headers=auth_headers)

    # Assert
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_post_stitching_source_not_found_returns_404(client, auth_headers):
    """Test stitching when source reconstruction not found."""
    # Arrange
    mock_svc = _make_mock_stitching_service(
        should_raise=ValueError("Reconstruction 999 not found")
    )
    app.dependency_overrides[get_stitching_service] = lambda: mock_svc

    request = {
        "name": "Missing Source",
        "building_id": "550e8400-e29b-41d4-a716-446655440000",
        "floor_number": 1,
        "source_plans": [
            {
                "reconstruction_id": "999",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 0,
            },
            {
                "reconstruction_id": "2",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 1,
            },
        ],
    }

    try:
        # Act
        response = await client.post("/api/v1/stitching/", json=request, headers=auth_headers)

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_stitching_service, None)


@pytest.mark.asyncio
async def test_post_stitching_processing_error_returns_500(client, auth_headers):
    """Test stitching when processing error occurs."""
    # Arrange
    mock_svc = _make_mock_stitching_service(
        should_raise=RuntimeError("Unexpected processing error")
    )
    app.dependency_overrides[get_stitching_service] = lambda: mock_svc

    request = {
        "name": "Processing Error",
        "building_id": "550e8400-e29b-41d4-a716-446655440000",
        "floor_number": 1,
        "source_plans": [
            {
                "reconstruction_id": "1",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 0,
            },
            {
                "reconstruction_id": "2",
                "transform": {
                    "translate_x": 0,
                    "translate_y": 0,
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "rotation_deg": 0,
                },
                "clip_polygons": [],
                "rect_crop": None,
                "image_width_px": 1000,
                "image_height_px": 800,
                "z_index": 1,
            },
        ],
    }

    try:
        # Act
        response = await client.post("/api/v1/stitching/", json=request, headers=auth_headers)

        # Assert
        assert response.status_code == 500
        assert "stitching failed" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_stitching_service, None)
