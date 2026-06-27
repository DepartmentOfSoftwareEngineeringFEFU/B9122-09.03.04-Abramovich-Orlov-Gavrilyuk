"""Pytest fixtures for stitching tests."""

import pytest
import numpy as np
from app.models.domain import Wall, Room, Door, Point2D


@pytest.fixture
def simple_wall() -> Wall:
    """Single horizontal wall."""
    return Wall(
        id="w1",
        points=[Point2D(x=0.0, y=0.5), Point2D(x=1.0, y=0.5)],
        thickness=0.2,
    )


@pytest.fixture
def simple_room() -> Room:
    """Single rectangular room."""
    return Room(
        id="r1",
        name="A301",
        polygon=[
            Point2D(x=0.2, y=0.2),
            Point2D(x=0.8, y=0.2),
            Point2D(x=0.8, y=0.8),
            Point2D(x=0.2, y=0.8),
        ],
        center=Point2D(x=0.5, y=0.5),
        room_type="room",
        area_normalized=0.36,
    )


@pytest.fixture
def simple_door() -> Door:
    """Single door."""
    return Door(
        id="d1",
        position=Point2D(x=0.5, y=0.5),
        width=0.1,
        connects=["r1", "r2"],
    )


@pytest.fixture
def identity_matrix() -> np.ndarray:
    """Identity transformation matrix."""
    return np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ], dtype=np.float64)
