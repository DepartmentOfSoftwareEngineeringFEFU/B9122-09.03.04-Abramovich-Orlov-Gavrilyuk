"""
Pydantic validation tests for Floor models.
"""

import pytest
from pydantic import ValidationError

from app.models.floors import CropBboxModel, FloorCreateRequest, FloorWallsUpdateRequest


def test_floor_create_request_valid():
    req = FloorCreateRequest(number=7)
    assert req.number == 7


def test_floor_create_request_zero_valid():
    req = FloorCreateRequest(number=0)
    assert req.number == 0


def test_floor_create_request_number_too_high():
    with pytest.raises(ValidationError):
        FloorCreateRequest(number=51)


def test_floor_create_request_negative():
    with pytest.raises(ValidationError):
        FloorCreateRequest(number=-1)


def test_crop_bbox_valid():
    bbox = CropBboxModel(x=0.05, y=0.10, width=0.85, height=0.70, rotation=0)
    assert bbox.rotation == 0


def test_crop_bbox_rotation_90():
    bbox = CropBboxModel(x=0.0, y=0.0, width=1.0, height=1.0, rotation=90)
    assert bbox.rotation == 90


def test_crop_bbox_invalid_rotation():
    with pytest.raises(ValidationError):
        CropBboxModel(x=0.0, y=0.0, width=1.0, height=1.0, rotation=45)


def test_crop_bbox_invalid_x_out_of_range():
    with pytest.raises(ValidationError):
        CropBboxModel(x=1.5, y=0.0, width=0.5, height=0.5)


def test_crop_bbox_zero_width_rejected():
    with pytest.raises(ValidationError):
        CropBboxModel(x=0.0, y=0.0, width=0.0, height=0.5)


def test_floor_walls_update_valid():
    req = FloorWallsUpdateRequest(wall_polygons=[[[0.1, 0.2], [0.4, 0.2]]])
    assert len(req.wall_polygons) == 1


def test_floor_walls_update_single_point_polygon_rejected():
    with pytest.raises(ValidationError):
        FloorWallsUpdateRequest(wall_polygons=[[[0.1, 0.2]]])


def test_floor_walls_update_out_of_range_rejected():
    with pytest.raises(ValidationError):
        FloorWallsUpdateRequest(wall_polygons=[[[1.5, 0.2], [0.4, 0.2]]])
