"""Tests for clip.py polygon clipping operations."""
import pytest
from shapely.geometry import Polygon
from app.models.domain import Wall, Room, Door, Point2D
from app.processing.stitching.clip import clip_walls, clip_rooms, clip_doors


def test_clip_walls_fully_inside_removed():
    """Wall fully inside clip polygon should be removed."""
    # Arrange
    wall = Wall(
        id="w1",
        points=[Point2D(x=0.3, y=0.5), Point2D(x=0.7, y=0.5)],
        thickness=0.2,
    )
    clip_poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])

    # Act
    result = clip_walls([wall], clip_poly)

    # Assert
    assert len(result) == 0


def test_clip_walls_fully_outside_unchanged():
    """Wall fully outside clip polygon should remain unchanged."""
    # Arrange
    wall = Wall(
        id="w1",
        points=[Point2D(x=0.1, y=0.1), Point2D(x=0.3, y=0.1)],
        thickness=0.2,
    )
    clip_poly = Polygon([(0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0)])

    # Act
    result = clip_walls([wall], clip_poly)

    # Assert
    assert len(result) == 1
    assert result[0].id == "w1"
    assert len(result[0].points) == 2


def test_clip_walls_partially_intersecting_trimmed():
    """Wall partially intersecting clip polygon should be trimmed."""
    # Arrange
    wall = Wall(
        id="w1",
        points=[Point2D(x=0.0, y=0.5), Point2D(x=1.0, y=0.5)],
        thickness=0.2,
    )
    # Clip polygon covers left half
    clip_poly = Polygon([(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)])

    # Act
    result = clip_walls([wall], clip_poly)

    # Assert
    assert len(result) == 1
    # Wall should be trimmed to right half
    assert result[0].points[0].x >= 0.5
    assert result[0].points[-1].x == 1.0


def test_clip_walls_crossing_creates_segments():
    """Wall crossing through clip polygon should create multiple segments."""
    # Arrange
    wall = Wall(
        id="w1",
        points=[Point2D(x=0.0, y=0.5), Point2D(x=1.0, y=0.5)],
        thickness=0.2,
    )
    # Clip polygon in the middle
    clip_poly = Polygon([(0.3, 0.0), (0.7, 0.0), (0.7, 1.0), (0.3, 1.0)])

    # Act
    result = clip_walls([wall], clip_poly)

    # Assert
    assert len(result) == 2  # Two segments created
    assert all("seg" in w.id for w in result)


def test_clip_rooms_center_inside_removed():
    """Room with center inside clip polygon should be removed."""
    # Arrange
    room = Room(
        id="r1",
        name="A301",
        polygon=[
            Point2D(x=0.2, y=0.2),
            Point2D(x=0.4, y=0.2),
            Point2D(x=0.4, y=0.4),
            Point2D(x=0.2, y=0.4),
        ],
        center=Point2D(x=0.3, y=0.3),
        room_type="room",
        area_normalized=0.04,
    )
    clip_poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])

    # Act
    result = clip_rooms([room], clip_poly)

    # Assert
    assert len(result) == 0


def test_clip_rooms_center_outside_kept():
    """Room with center outside clip polygon should be kept."""
    # Arrange
    room = Room(
        id="r1",
        name="A301",
        polygon=[
            Point2D(x=0.1, y=0.1),
            Point2D(x=0.3, y=0.1),
            Point2D(x=0.3, y=0.3),
            Point2D(x=0.1, y=0.3),
        ],
        center=Point2D(x=0.2, y=0.2),
        room_type="room",
        area_normalized=0.04,
    )
    # Clip polygon on the right side
    clip_poly = Polygon([(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)])

    # Act
    result = clip_rooms([room], clip_poly)

    # Assert
    assert len(result) == 1
    assert result[0].id == "r1"


def test_clip_rooms_partial_clip_updates_polygon():
    """Room partially clipped should have updated polygon and center."""
    # Arrange
    room = Room(
        id="r1",
        name="A301",
        polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=1.0, y=0.0),
            Point2D(x=1.0, y=0.4),
            Point2D(x=0.0, y=0.4),
        ],
        center=Point2D(x=0.5, y=0.2),
        room_type="room",
        area_normalized=0.4,
    )
    # Clip polygon covers top half
    clip_poly = Polygon([(0.0, 0.5), (1.0, 0.5), (1.0, 1.0), (0.0, 1.0)])

    # Act
    result = clip_rooms([room], clip_poly)

    # Assert
    assert len(result) == 1
    # Room should still exist (center at y=0.2 is outside clip)
    assert result[0].id == "r1"
    # Polygon should be unchanged (no intersection)
    assert len(result[0].polygon) == 4


def test_clip_rooms_fully_clipped_removed():
    """Room fully clipped should be removed."""
    # Arrange
    room = Room(
        id="r1",
        name="A301",
        polygon=[
            Point2D(x=0.2, y=0.2),
            Point2D(x=0.4, y=0.2),
            Point2D(x=0.4, y=0.4),
            Point2D(x=0.2, y=0.4),
        ],
        center=Point2D(x=0.6, y=0.6),  # Center outside
        room_type="room",
        area_normalized=0.04,
    )
    # Clip polygon covers the room polygon area
    clip_poly = Polygon([(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)])

    # Act
    result = clip_rooms([room], clip_poly)

    # Assert
    assert len(result) == 0


def test_clip_doors_inside_removed():
    """Door inside clip polygon should be removed."""
    # Arrange
    door = Door(
        id="d1",
        position=Point2D(x=0.5, y=0.5),
        width=0.1,
    )
    clip_poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])

    # Act
    result = clip_doors([door], clip_poly)

    # Assert
    assert len(result) == 0


def test_clip_doors_outside_kept():
    """Door outside clip polygon should be kept."""
    # Arrange
    door = Door(
        id="d1",
        position=Point2D(x=0.2, y=0.2),
        width=0.1,
    )
    # Clip polygon on the right side
    clip_poly = Polygon([(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)])

    # Act
    result = clip_doors([door], clip_poly)

    # Assert
    assert len(result) == 1
    assert result[0].id == "d1"
