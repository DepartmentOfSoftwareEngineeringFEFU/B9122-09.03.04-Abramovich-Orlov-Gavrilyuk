"""
Integration tests for the vectorization pipeline.

These tests verify that pipeline components work together end-to-end
using real OpenCV operations on small synthetic images.

No mocks — real function chains only.
"""
import json

import cv2
import numpy as np
import pytest

from app.models.domain import (
    Door,
    Point2D,
    Room,
    TextBlock,
    VectorizationResult,
    Wall,
)
from app.processing.pipeline import (
    auto_crop_suggest,
    classify_rooms,
    color_filter,
    compute_scale_factor,
    compute_wall_thickness,
    door_detect,
    normalize_brightness,
    normalize_coords,
    remove_text_regions,
    room_detect,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_floor_plan_mask(size: int = 200, wall_thickness: int = 5) -> np.ndarray:
    """
    Create a binary mask (walls=255) with an outer border and a dividing wall,
    producing two rooms large enough to pass min_room_area filters.
    """
    mask = np.zeros((size, size), dtype=np.uint8)
    cv2.rectangle(mask, (5, 5), (size - 5, size - 5), 255, wall_thickness)
    cv2.line(mask, (size // 2, 5), (size // 2, size - 5), 255, wall_thickness)
    return mask


def _make_bgr_image(size: int = 200) -> np.ndarray:
    """White BGR image with a dark rectangle — gives auto_crop_suggest something to find."""
    img = np.ones((size, size, 3), dtype=np.uint8) * 240
    cv2.rectangle(img, (20, 20), (size - 20, size - 20), (30, 30, 30), -1)
    return img


# ---------------------------------------------------------------------------
# 1. Steps 1-3 chain: normalize_brightness → color_filter → auto_crop_suggest
# ---------------------------------------------------------------------------

def test_pipeline_steps_1_to_3_chain():
    img = _make_bgr_image(200)

    # Step 1
    brightened = normalize_brightness(img)
    assert brightened.shape == img.shape
    assert brightened.dtype == np.uint8

    # Step 2 — consumes output of step 1
    filtered = color_filter(brightened)
    assert filtered.shape == brightened.shape
    assert filtered.dtype == np.uint8

    # Step 3 — consumes output of step 2
    crop_rect = auto_crop_suggest(filtered, min_area_ratio=0.05)
    # The dark rectangle is large enough to be detected
    assert crop_rect is not None
    assert set(crop_rect.keys()) == {"x", "y", "width", "height"}
    for key, val in crop_rect.items():
        assert 0.0 <= val <= 1.0, f"crop_rect[{key}]={val} out of [0,1]"


# ---------------------------------------------------------------------------
# 2. Steps 5-6 chain: remove_text_regions with fake TextBlocks
# ---------------------------------------------------------------------------

def test_pipeline_steps_5_6_chain():
    mask = _make_floor_plan_mask(200)
    text_blocks = [
        TextBlock(
            text="101",
            center=Point2D(x=0.25, y=0.5),
            confidence=90.0,
            is_room_number=True,
        ),
        TextBlock(
            text="102",
            center=Point2D(x=0.75, y=0.5),
            confidence=85.0,
            is_room_number=True,
        ),
    ]

    cleaned = remove_text_regions(mask, text_blocks, image_size=(200, 200))

    assert cleaned is not None
    assert cleaned.shape == mask.shape
    assert cleaned.dtype == np.uint8
    # Result must be a valid binary-ish mask (values 0 or 255 after inpaint may vary,
    # but all values must be uint8 in range)
    assert cleaned.min() >= 0
    assert cleaned.max() <= 255


# ---------------------------------------------------------------------------
# 3. Steps 7 chain: room_detect → classify_rooms → door_detect
# ---------------------------------------------------------------------------

def test_pipeline_steps_7_chain():
    mask = _make_floor_plan_mask(300, wall_thickness=6)

    # room_detect
    rooms = room_detect(mask, min_room_area=500, max_room_area_ratio=0.8)
    assert len(rooms) >= 1, "Expected at least one room in synthetic floor plan"

    # classify_rooms — consumes room_detect output
    classified = classify_rooms(rooms)
    assert len(classified) == len(rooms)
    for room in classified:
        assert room.room_type in ("room", "corridor")

    # door_detect — consumes original mask + classified rooms
    doors = door_detect(mask, classified)
    assert isinstance(doors, list)
    # doors may or may not be found depending on gap geometry — just verify types
    for door in doors:
        assert isinstance(door, Door)
        assert 0.0 <= door.position.x <= 1.0
        assert 0.0 <= door.position.y <= 1.0


# ---------------------------------------------------------------------------
# 4. Full pipeline assembly into VectorizationResult
# ---------------------------------------------------------------------------

def test_full_vectorization_result_assembly():
    size = 300
    mask = _make_floor_plan_mask(size, wall_thickness=6)

    rooms = room_detect(mask, min_room_area=500, max_room_area_ratio=0.8)
    assert len(rooms) >= 1

    classified_rooms = classify_rooms(rooms)
    doors = door_detect(mask, classified_rooms)
    wall_thickness_px = compute_wall_thickness(mask)
    pixels_per_meter = compute_scale_factor(wall_thickness_px)

    # Build minimal walls list from room polygons (stand-in for ContourService output)
    walls = [
        Wall(
            id=f"wall_{i}",
            points=room.polygon,
            thickness=0.2,
        )
        for i, room in enumerate(classified_rooms)
    ]

    norm_walls, norm_rooms, norm_doors = normalize_coords(
        walls, classified_rooms, doors, image_size=(size, size)
    )

    result = VectorizationResult(
        walls=norm_walls,
        rooms=norm_rooms,
        doors=norm_doors,
        text_blocks=[],
        image_size_original=(size, size),
        image_size_cropped=(size, size),
        crop_rect=None,
        crop_applied=False,
        rotation_angle=0,
        wall_thickness_px=wall_thickness_px,
        estimated_pixels_per_meter=pixels_per_meter,
        rooms_with_names=sum(1 for r in norm_rooms if r.name),
        corridors_count=sum(1 for r in norm_rooms if r.room_type == "corridor"),
        doors_count=len(norm_doors),
    )

    assert len(result.rooms) >= 1
    assert result.wall_thickness_px >= 0.0
    assert result.estimated_pixels_per_meter > 0.0
    assert result.image_size_original == (size, size)
    assert result.image_size_cropped == (size, size)
    assert result.doors_count == len(norm_doors)
    assert result.corridors_count >= 0


# ---------------------------------------------------------------------------
# 5. VectorizationResult serialization roundtrip
# ---------------------------------------------------------------------------

def test_vectorization_result_serialization_roundtrip():
    rooms = [
        Room(
            id="room_1",
            name="101",
            polygon=[
                Point2D(x=0.1, y=0.1),
                Point2D(x=0.4, y=0.1),
                Point2D(x=0.4, y=0.4),
                Point2D(x=0.1, y=0.4),
            ],
            center=Point2D(x=0.25, y=0.25),
            room_type="room",
            area_normalized=0.09,
        )
    ]
    walls = [
        Wall(
            id="wall_0",
            points=[Point2D(x=0.0, y=0.0), Point2D(x=1.0, y=0.0)],
            thickness=0.2,
        )
    ]
    doors = [
        Door(
            id="door_0",
            position=Point2D(x=0.5, y=0.1),
            width=0.05,
            connects=["room_1"],
        )
    ]

    original = VectorizationResult(
        walls=walls,
        rooms=rooms,
        doors=doors,
        text_blocks=[],
        image_size_original=(200, 200),
        image_size_cropped=(200, 200),
        crop_rect={"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        crop_applied=False,
        rotation_angle=0,
        wall_thickness_px=6.0,
        estimated_pixels_per_meter=30.0,
        rooms_with_names=1,
        corridors_count=0,
        doors_count=1,
    )

    serialized = original.model_dump_json()
    deserialized = VectorizationResult.model_validate_json(serialized)

    assert deserialized.image_size_original == original.image_size_original
    assert deserialized.image_size_cropped == original.image_size_cropped
    assert len(deserialized.rooms) == len(original.rooms)
    assert deserialized.rooms[0].id == original.rooms[0].id
    assert deserialized.rooms[0].name == original.rooms[0].name
    assert len(deserialized.walls) == len(original.walls)
    assert len(deserialized.doors) == len(original.doors)
    assert deserialized.wall_thickness_px == original.wall_thickness_px
    assert deserialized.estimated_pixels_per_meter == original.estimated_pixels_per_meter
    assert deserialized.crop_rect == original.crop_rect


# ---------------------------------------------------------------------------
# 6. normalize_coords after room_detect — all coords in [0, 1]
# ---------------------------------------------------------------------------

def test_normalize_coords_after_room_detect():
    size = 300
    mask = _make_floor_plan_mask(size, wall_thickness=6)

    rooms = room_detect(mask, min_room_area=500, max_room_area_ratio=0.8)
    assert len(rooms) >= 1

    walls: list[Wall] = []  # no walls from ContourService in this test
    doors: list[Door] = []

    _, norm_rooms, _ = normalize_coords(walls, rooms, doors, image_size=(size, size))

    for room in norm_rooms:
        assert 0.0 <= room.center.x <= 1.0, f"center.x={room.center.x}"
        assert 0.0 <= room.center.y <= 1.0, f"center.y={room.center.y}"
        for pt in room.polygon:
            assert 0.0 <= pt.x <= 1.0, f"polygon pt.x={pt.x}"
            assert 0.0 <= pt.y <= 1.0, f"polygon pt.y={pt.y}"


# ---------------------------------------------------------------------------
# 7. classify_rooms does not mutate input
# ---------------------------------------------------------------------------

def test_classify_rooms_does_not_mutate_input():
    rooms = [
        Room(
            id="room_1",
            name="",
            polygon=[
                Point2D(x=0.1, y=0.1),
                Point2D(x=0.4, y=0.1),
                Point2D(x=0.4, y=0.4),
                Point2D(x=0.1, y=0.4),
            ],
            center=Point2D(x=0.25, y=0.25),
            room_type="unknown",
            area_normalized=0.09,
        ),
        Room(
            id="room_2",
            name="",
            polygon=[
                Point2D(x=0.05, y=0.45),
                Point2D(x=0.95, y=0.45),
                Point2D(x=0.95, y=0.55),
                Point2D(x=0.05, y=0.55),
            ],
            center=Point2D(x=0.5, y=0.5),
            room_type="unknown",
            area_normalized=0.1,
        ),
    ]

    # Snapshot original state
    original_types = [r.room_type for r in rooms]
    original_ids = [r.id for r in rooms]

    result = classify_rooms(rooms)

    # Input list must not be mutated
    assert [r.room_type for r in rooms] == original_types
    assert [r.id for r in rooms] == original_ids

    # Result is a new list with updated types
    assert result is not rooms
    assert len(result) == len(rooms)
    for room in result:
        assert room.room_type in ("room", "corridor")
