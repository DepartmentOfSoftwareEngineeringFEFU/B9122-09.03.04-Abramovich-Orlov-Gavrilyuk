"""Tests for merge.py — model merging and normalization."""

from app.models.domain import VectorizationResult, Wall, Room, Door, Point2D
from app.processing.stitching.merge import (
    merge_models,
    normalize_to_bounding_box,
    check_duplicate_rooms,
)


def test_merge_models_concatenates_walls():
    """Test that merge_models concatenates walls from multiple models."""
    # Arrange
    model_a = VectorizationResult(
        walls=[Wall(id="w1", points=[Point2D(x=0.0, y=0.0), Point2D(x=1.0, y=0.0)])],
        rooms=[],
        doors=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )
    model_b = VectorizationResult(
        walls=[Wall(id="w2", points=[Point2D(x=0.0, y=1.0), Point2D(x=1.0, y=1.0)])],
        rooms=[],
        doors=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )

    # Act
    merged = merge_models([model_a, model_b])

    # Assert
    assert len(merged.walls) == 2
    assert merged.walls[0].id == "w1"
    assert merged.walls[1].id == "w2"


def test_merge_models_concatenates_rooms():
    """Test that merge_models concatenates rooms from multiple models."""
    # Arrange
    model_a = VectorizationResult(
        walls=[],
        rooms=[
            Room(
                id="r1",
                name="Room A",
                polygon=[Point2D(x=0.0, y=0.0), Point2D(x=0.5, y=0.0), Point2D(x=0.5, y=0.5)],
                center=Point2D(x=0.25, y=0.25),
            )
        ],
        doors=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )
    model_b = VectorizationResult(
        walls=[],
        rooms=[
            Room(
                id="r2",
                name="Room B",
                polygon=[Point2D(x=0.5, y=0.5), Point2D(x=1.0, y=0.5), Point2D(x=1.0, y=1.0)],
                center=Point2D(x=0.75, y=0.75),
            )
        ],
        doors=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )

    # Act
    merged = merge_models([model_a, model_b])

    # Assert
    assert len(merged.rooms) == 2
    assert merged.rooms[0].id == "r1"
    assert merged.rooms[1].id == "r2"


def test_merge_models_concatenates_doors():
    """Test that merge_models concatenates doors from multiple models."""
    # Arrange
    model_a = VectorizationResult(
        walls=[],
        rooms=[],
        doors=[Door(id="d1", position=Point2D(x=0.25, y=0.5))],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )
    model_b = VectorizationResult(
        walls=[],
        rooms=[],
        doors=[Door(id="d2", position=Point2D(x=0.75, y=0.5))],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )

    # Act
    merged = merge_models([model_a, model_b])

    # Assert
    assert len(merged.doors) == 2
    assert merged.doors[0].id == "d1"
    assert merged.doors[1].id == "d2"


def test_merge_models_empty_plans_returns_empty():
    """Test that merge_models handles empty list gracefully."""
    # Act
    merged = merge_models([])

    # Assert
    assert len(merged.walls) == 0
    assert len(merged.rooms) == 0
    assert len(merged.doors) == 0
    assert merged.image_size_original == (0, 0)


def test_normalize_to_bounding_box_coords_in_range():
    """Test that normalize_to_bounding_box produces coordinates in [0,1]."""
    # Arrange - use model_construct to bypass validation for input
    model = VectorizationResult.model_construct(
        walls=[
            Wall.model_construct(
                id="w1",
                points=[
                    Point2D.model_construct(x=100.0, y=200.0),
                    Point2D.model_construct(x=500.0, y=200.0),
                ],
            ),
            Wall.model_construct(
                id="w2",
                points=[
                    Point2D.model_construct(x=100.0, y=600.0),
                    Point2D.model_construct(x=500.0, y=600.0),
                ],
            ),
        ],
        rooms=[],
        doors=[],
        text_blocks=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )

    # Act
    normalized = normalize_to_bounding_box(model)

    # Assert
    for wall in normalized.walls:
        for point in wall.points:
            assert 0.0 <= point.x <= 1.0
            assert 0.0 <= point.y <= 1.0


def test_normalize_to_bounding_box_uses_all_walls():
    """Test that bounding box is computed from all wall points."""
    # Arrange - use model_construct to bypass validation for input
    model = VectorizationResult.model_construct(
        walls=[
            Wall.model_construct(
                id="w1",
                points=[
                    Point2D.model_construct(x=100.0, y=200.0),
                    Point2D.model_construct(x=500.0, y=200.0),
                ],
            ),
            Wall.model_construct(
                id="w2",
                points=[
                    Point2D.model_construct(x=100.0, y=600.0),
                    Point2D.model_construct(x=500.0, y=600.0),
                ],
            ),
        ],
        rooms=[],
        doors=[],
        text_blocks=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )

    # Act
    normalized = normalize_to_bounding_box(model)

    # Assert - corners should map to (0,0) and (1,1)
    # Min point (100, 200) -> (0, 0)
    # Max point (500, 600) -> (1, 1)
    assert normalized.walls[0].points[0].x == 0.0
    assert normalized.walls[0].points[0].y == 0.0
    assert normalized.walls[1].points[1].x == 1.0
    assert normalized.walls[1].points[1].y == 1.0


def test_normalize_to_bounding_box_consistent_scale():
    """Test that normalization preserves aspect ratio."""
    # Arrange - use model_construct to bypass validation for input
    model = VectorizationResult.model_construct(
        walls=[
            Wall.model_construct(
                id="w1",
                points=[
                    Point2D.model_construct(x=0.0, y=0.0),
                    Point2D.model_construct(x=400.0, y=0.0),
                ],
            ),
            Wall.model_construct(
                id="w2",
                points=[
                    Point2D.model_construct(x=0.0, y=200.0),
                    Point2D.model_construct(x=400.0, y=200.0),
                ],
            ),
        ],
        rooms=[],
        doors=[],
        text_blocks=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )

    # Act
    normalized = normalize_to_bounding_box(model)

    # Assert - width is 400px, height is 200px (2:1 ratio)
    # After normalization, both should span [0,1] in their respective dimensions
    # Top-left corner
    assert normalized.walls[0].points[0].x == 0.0
    assert normalized.walls[0].points[0].y == 0.0
    # Top-right corner
    assert normalized.walls[0].points[1].x == 1.0
    assert normalized.walls[0].points[1].y == 0.0
    # Bottom-right corner
    assert normalized.walls[1].points[1].x == 1.0
    assert normalized.walls[1].points[1].y == 1.0


def test_check_duplicate_rooms_close_detected():
    """Test that duplicate rooms within threshold are detected."""
    # Arrange - use model_validate to bypass validation for input
    rooms = [
        Room.model_validate({
            "id": "r1",
            "name": "101",
            "polygon": [],
            "center": {"x": 0.1, "y": 0.1},
        }, strict=False),
        Room.model_validate({
            "id": "r2",
            "name": "101",
            "polygon": [],
            "center": {"x": 0.11, "y": 0.11},  # ~0.014 units away
        }, strict=False),
    ]

    # Act
    warnings = check_duplicate_rooms(rooms, distance_threshold=0.03)

    # Assert
    assert len(warnings) == 1
    assert "101" in warnings[0]
    assert "r1" in warnings[0]
    assert "r2" in warnings[0]


def test_check_duplicate_rooms_far_not_detected():
    """Test that rooms beyond threshold are not flagged as duplicates."""
    # Arrange - use model_validate to bypass validation for input
    rooms = [
        Room.model_validate({
            "id": "r1",
            "name": "101",
            "polygon": [],
            "center": {"x": 0.1, "y": 0.1},
        }, strict=False),
        Room.model_validate({
            "id": "r2",
            "name": "101",
            "polygon": [],
            "center": {"x": 0.2, "y": 0.2},  # ~0.141 units away
        }, strict=False),
    ]

    # Act
    warnings = check_duplicate_rooms(rooms, distance_threshold=0.03)

    # Assert
    assert len(warnings) == 0


def test_check_duplicate_rooms_threshold_configurable():
    """Test that distance threshold is configurable."""
    # Arrange - use model_validate to bypass validation for input
    rooms = [
        Room.model_validate({
            "id": "r1",
            "name": "101",
            "polygon": [],
            "center": {"x": 0.1, "y": 0.1},
        }, strict=False),
        Room.model_validate({
            "id": "r2",
            "name": "101",
            "polygon": [],
            "center": {"x": 0.15, "y": 0.1},  # 0.05 units away
        }, strict=False),
    ]

    # Act - with threshold 0.03, should not detect
    warnings_30 = check_duplicate_rooms(rooms, distance_threshold=0.03)
    # Act - with threshold 0.06, should detect
    warnings_60 = check_duplicate_rooms(rooms, distance_threshold=0.06)

    # Assert
    assert len(warnings_30) == 0
    assert len(warnings_60) == 1
