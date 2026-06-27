"""
Pydantic validation tests for elevator floor-link fields on the room models
(floor-transition-tools): VectorRoom (persisted) and domain Room.
"""

import pytest
from pydantic import ValidationError

from app.models.domain import Point2D, Room
from app.models.reconstruction_vectors import VectorRoom


def _vector_room_kwargs(**overrides) -> dict:
    base = {
        "id": "elev_1",
        "name": "Лифт",
        "room_type": "elevator",
        "center": {"x": 0.5, "y": 0.5},
        "polygon": [
            {"x": 0.4, "y": 0.4},
            {"x": 0.6, "y": 0.4},
            {"x": 0.6, "y": 0.6},
            {"x": 0.4, "y": 0.6},
        ],
        "area_normalized": 0.04,
    }
    base.update(overrides)
    return base


def _room_kwargs(**overrides) -> dict:
    base = {
        "id": "elev_1",
        "name": "Лифт",
        "room_type": "elevator",
        "center": Point2D(x=0.5, y=0.5),
        "polygon": [Point2D(x=0.4, y=0.4), Point2D(x=0.6, y=0.6)],
        "area_normalized": 0.04,
    }
    base.update(overrides)
    return base


# --- VectorRoom ---

def test_vectorroom_elevator_fields_valid_accepted():
    room = VectorRoom(
        **_vector_room_kwargs(floor_from=1, floor_to=10, floors_excluded=[5])
    )
    assert room.floor_from == 1
    assert room.floor_to == 10
    assert room.floors_excluded == [5]


def test_vectorroom_elevator_from_gt_to_raises():
    with pytest.raises(ValidationError):
        VectorRoom(**_vector_room_kwargs(floor_from=8, floor_to=3))


def test_vectorroom_excluded_out_of_range_raises():
    with pytest.raises(ValidationError):
        VectorRoom(
            **_vector_room_kwargs(floor_from=1, floor_to=5, floors_excluded=[9])
        )


def test_vectorroom_missing_fields_defaults():
    # Old documents without the new keys must load with safe defaults.
    room = VectorRoom(**_vector_room_kwargs(room_type="room", name=""))
    assert room.floor_from is None
    assert room.floor_to is None
    assert room.floors_excluded == []


# --- domain Room ---

def test_room_elevator_invalid_range_raises():
    with pytest.raises(ValidationError):
        Room(**_room_kwargs(floor_from=10, floor_to=2))


def test_room_staircase_no_floor_fields_ok():
    room = Room(**_room_kwargs(room_type="staircase", name="Лестница"))
    assert room.floor_from is None
    assert room.floor_to is None
    assert room.floors_excluded == []
