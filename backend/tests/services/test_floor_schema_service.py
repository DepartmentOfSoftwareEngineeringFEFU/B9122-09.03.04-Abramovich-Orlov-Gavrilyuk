"""
Tests for FloorSchemaService.

CV functions are mocked — no actual image processing.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from app.core.exceptions import FloorNotFoundError, FloorSchemaError
from app.models.floors import CropBboxModel
from app.services.floor_schema_service import FloorSchemaService


# Helpers


def _make_floor(
    id: int = 101,
    schema_image_id: str | None = None,
    schema_crop_bbox: dict | None = None,
    wall_polygons: list | None = None,
) -> MagicMock:
    f = MagicMock()
    f.id = id
    f.schema_image_id = schema_image_id
    f.schema_crop_bbox = schema_crop_bbox
    f.wall_polygons = wall_polygons
    f.created_at = datetime(2026, 1, 1)
    return f


def _make_svc(floor: MagicMock | None = None) -> FloorSchemaService:
    floor_repo = AsyncMock()
    floor_repo.get_by_id.return_value = floor
    floor_repo.update_schema.return_value = floor
    floor_repo.update_wall_polygons.return_value = floor
    svc = FloorSchemaService(floor_repo=floor_repo, upload_dir="/tmp/uploads")
    return svc


# Tests


@pytest.mark.asyncio
async def test_upload_schema_sets_image_id():
    """upload_schema persists schema_image_id via floor_repo.update_schema."""
    floor = _make_floor(id=101)
    svc = _make_svc(floor=floor)

    # Make _find_image return a fake path so validation passes
    with patch.object(svc, "_find_image", return_value="/tmp/uploads/plans/abc123.jpg"):
        await svc.upload_schema(floor_id=101, image_id="abc123")

    svc._floor_repo.update_schema.assert_awaited_once()
    call_kwargs = svc._floor_repo.update_schema.call_args
    assert call_kwargs.kwargs["schema_image_id"] == "abc123"


@pytest.mark.asyncio
async def test_update_crop_persists_bbox():
    """update_crop saves CropBboxModel as dict via floor_repo.update_schema."""
    floor = _make_floor(id=101, schema_image_id="img-1")
    svc = _make_svc(floor=floor)

    bbox = CropBboxModel(x=0.05, y=0.10, width=0.85, height=0.70, rotation=0)
    await svc.update_crop(floor_id=101, bbox=bbox)

    svc._floor_repo.update_schema.assert_awaited_once()
    call_kwargs = svc._floor_repo.update_schema.call_args.kwargs
    assert call_kwargs["schema_crop_bbox"]["x"] == pytest.approx(0.05)
    assert call_kwargs["schema_crop_bbox"]["height"] == pytest.approx(0.70)


@pytest.mark.asyncio
async def test_extract_walls_calls_cv_and_saves_polygons():
    """extract_walls calls preprocess_image + find_contours and stores result."""
    floor = _make_floor(id=101, schema_image_id="schema-1")
    svc = _make_svc(floor=floor)

    # Mock _find_image to return a fake path
    fake_path = "/tmp/uploads/plans/schema-1.jpg"
    # Create a minimal 10x10 white binary image for cv2.imread mock
    fake_image = np.ones((10, 10, 3), dtype=np.uint8) * 255
    fake_binary = np.ones((10, 10), dtype=np.uint8) * 255
    # One fake contour: 4-point rectangle
    fake_contour = np.array([[[0, 0]], [[9, 0]], [[9, 9]], [[0, 9]]], dtype=np.int32)

    with (
        patch.object(svc, "_find_image", return_value=fake_path),
        patch("app.services.floor_schema_service.cv2.imread", return_value=fake_image),
        patch(
            "app.services.floor_schema_service.preprocess_image",
            return_value=fake_binary,
        ),
        patch(
            "app.services.floor_schema_service.vectorizer_find_contours",
            return_value=[fake_contour],
        ),
    ):
        polygons = await svc.extract_walls(floor_id=101)

    # Should have saved + returned at least the one polygon (perimeter large enough)
    svc._floor_repo.update_wall_polygons.assert_awaited_once_with(101, polygons)
    assert isinstance(polygons, list)


@pytest.mark.asyncio
async def test_extract_walls_no_image_raises_validation():
    """extract_walls raises FloorSchemaError when schema_image_id is None."""
    floor = _make_floor(id=101, schema_image_id=None)
    svc = _make_svc(floor=floor)

    with pytest.raises(FloorSchemaError, match="schema image not uploaded"):
        await svc.extract_walls(floor_id=101)

    svc._floor_repo.update_wall_polygons.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_walls_persists_manual_polygons():
    """update_walls saves manually provided polygons via floor_repo."""
    floor = _make_floor(id=101, schema_image_id="img-1")
    svc = _make_svc(floor=floor)

    polygons = [[[0.1, 0.2], [0.4, 0.2], [0.4, 0.5]]]
    await svc.update_walls(floor_id=101, polygons=polygons)

    svc._floor_repo.update_wall_polygons.assert_awaited_once_with(101, polygons)


@pytest.mark.asyncio
async def test_update_mask_persists_mask_file_id():
    """update_mask links the uploaded mask via floor_repo.update_mask."""
    floor = _make_floor(id=101, schema_image_id="img-1")
    svc = _make_svc(floor=floor)

    await svc.update_mask(floor_id=101, mask_file_id="mask-uuid")

    svc._floor_repo.update_mask.assert_awaited_once_with(101, "mask-uuid")


@pytest.mark.asyncio
async def test_update_mask_missing_floor_raises_not_found():
    """update_mask raises FloorNotFoundError when the floor is absent."""
    svc = _make_svc(floor=None)  # floor_repo.get_by_id returns None

    with pytest.raises(FloorNotFoundError):
        await svc.update_mask(floor_id=999, mask_file_id="mask-uuid")

    svc._floor_repo.update_mask.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_schema_same_image_preserves_derived():
    """Re-saving the SAME image keeps crop and does not clear walls/mask."""
    floor = _make_floor(id=101, schema_image_id="img-1", schema_crop_bbox={"x": 0.1})
    svc = _make_svc(floor=floor)

    with patch.object(svc, "_find_image", return_value="/tmp/uploads/plans/img-1.jpg"):
        await svc.upload_schema(floor_id=101, image_id="img-1")

    call_kwargs = svc._floor_repo.update_schema.call_args.kwargs
    assert call_kwargs["schema_crop_bbox"] == {"x": 0.1}  # crop preserved
    svc._floor_repo.update_wall_polygons.assert_not_awaited()
    svc._floor_repo.update_mask.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_schema_new_image_clears_derived():
    """Uploading a DIFFERENT image drops the stale crop, walls and mask."""
    floor = _make_floor(id=101, schema_image_id="old-img", schema_crop_bbox={"x": 0.1})
    svc = _make_svc(floor=floor)

    with patch.object(svc, "_find_image", return_value="/tmp/uploads/plans/new.jpg"):
        await svc.upload_schema(floor_id=101, image_id="new-img")

    call_kwargs = svc._floor_repo.update_schema.call_args.kwargs
    assert call_kwargs["schema_image_id"] == "new-img"
    assert call_kwargs["schema_crop_bbox"] is None  # old crop dropped
    svc._floor_repo.update_wall_polygons.assert_awaited_once_with(101, [])
    svc._floor_repo.update_mask.assert_awaited_once_with(101, None)


@pytest.mark.asyncio
async def test_reset_schema_clears_all_fields():
    """reset_schema nulls schema image, crop, walls and mask."""
    floor = _make_floor(
        id=101,
        schema_image_id="img-1",
        schema_crop_bbox={"x": 0.1},
        wall_polygons=[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]],
    )
    svc = _make_svc(floor=floor)

    await svc.reset_schema(floor_id=101)

    schema_kwargs = svc._floor_repo.update_schema.call_args.kwargs
    assert schema_kwargs["schema_image_id"] is None
    assert schema_kwargs["schema_crop_bbox"] is None
    svc._floor_repo.update_wall_polygons.assert_awaited_once_with(101, [])
    svc._floor_repo.update_mask.assert_awaited_once_with(101, None)


@pytest.mark.asyncio
async def test_reset_schema_missing_floor_raises_not_found():
    """reset_schema raises FloorNotFoundError when the floor is absent."""
    svc = _make_svc(floor=None)

    with pytest.raises(FloorNotFoundError):
        await svc.reset_schema(floor_id=999)

    svc._floor_repo.update_schema.assert_not_awaited()
