"""Model + build-pipeline tests for the stair directional gates (D).

 (Models section):
``connects_up``/``connects_down`` default True, round-trip Room↔VectorRoom, and
survive the ``normalize_coords`` rebuild in the build pipeline (the silent-drop
risk flagged in 03-decisions.md — same class of bug C fixed for elevator fields).
"""

from app.models.domain import Point2D, Room
from app.models.reconstruction_vectors import VectorRoom
from app.processing.pipeline import normalize_coords


def _square() -> list[Point2D]:
    return [
        Point2D(x=0.3, y=0.3),
        Point2D(x=0.45, y=0.3),
        Point2D(x=0.45, y=0.45),
        Point2D(x=0.3, y=0.45),
    ]


def test_room_stair_gates_default_true():
    """A staircase built without the gate fields opens both ways."""
    room = Room(
        id="s1",
        polygon=_square(),
        center=Point2D(x=0.375, y=0.375),
        room_type="staircase",
    )
    assert room.connects_up is True
    assert room.connects_down is True


def test_room_gates_roundtrip_preserved():
    """connects_up=False survives Room → VectorRoom → Room (vectorization_data)."""
    room = Room(
        id="s1",
        polygon=_square(),
        center=Point2D(x=0.375, y=0.375),
        room_type="staircase",
        connects_up=False,
        connects_down=True,
    )
    vroom = VectorRoom(**room.model_dump())
    assert vroom.connects_up is False
    assert vroom.connects_down is True

    back = Room(**vroom.model_dump())
    assert back.connects_up is False
    assert back.connects_down is True


def test_build_preserves_stair_gates():
    """normalize_coords (build pipeline) keeps the gates through the rebuild."""
    room = Room(
        id="s1",
        polygon=_square(),
        center=Point2D(x=0.375, y=0.375),
        room_type="staircase",
        connects_up=False,
        connects_down=True,
    )
    _, rooms, _ = normalize_coords([], [room], [], (200, 150))
    assert len(rooms) == 1
    assert rooms[0].connects_up is False
    assert rooms[0].connects_down is True
