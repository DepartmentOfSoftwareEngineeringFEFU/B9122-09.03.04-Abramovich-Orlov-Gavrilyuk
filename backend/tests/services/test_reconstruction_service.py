import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from app.services.reconstruction_service import ReconstructionService, STATUS_DISPLAY
from app.models.domain import (
    Point2D,
    Room,
    VectorizationResult,
)


def _make_svc() -> ReconstructionService:
    repo = AsyncMock()
    storage = AsyncMock()
    return ReconstructionService(repo=repo, storage=storage)


def _minimal_vectorization_dict() -> dict:
    return {
        "walls": [],
        "rooms": [],
        "doors": [],
        "text_blocks": [],
        "image_size_original": [800, 600],
        "image_size_cropped": [800, 600],
        "crop_rect": None,
        "crop_applied": False,
        "rotation_angle": 0,
        "wall_thickness_px": 5.0,
        "estimated_pixels_per_meter": 50.0,
        "rooms_with_names": 0,
        "corridors_count": 0,
        "doors_count": 0,
    }


@pytest.mark.asyncio
async def test_get_vectorization_data_returns_vector_model():
    svc = _make_svc()
    mock_rec = MagicMock()
    mock_rec.vectorization_data = json.dumps(_minimal_vectorization_dict())
    svc._repo.get_by_id.return_value = mock_rec

    result = await svc.get_vectorization_data(1)

    assert result is not None
    assert result.model_dump()["rooms"] == []
    assert result.rotation_angle == 0


@pytest.mark.asyncio
async def test_get_vectorization_data_invalid_json_returns_none():
    svc = _make_svc()
    mock_rec = MagicMock()
    mock_rec.vectorization_data = "not valid json"
    svc._repo.get_by_id.return_value = mock_rec

    result = await svc.get_vectorization_data(1)

    assert result is None


@pytest.mark.asyncio
async def test_update_vectorization_data_saves_json():
    svc = _make_svc()
    svc._repo.update_vectorization_data.return_value = MagicMock()
    vr = VectorizationResult(**_minimal_vectorization_dict())

    result = await svc.update_vectorization_data(1, vr)

    assert result is True
    saved = json.loads(svc._repo.update_vectorization_data.call_args[0][1])
    assert saved["image_size_original"] == [800, 600]


# --- build_mesh: elevator floor-link fields (floor-transition-tools) ---

def _elevator_room_dict(**overrides) -> dict:
    base = {
        "id": "elev_1",
        "name": "Лифт",
        "room_type": "elevator",
        "x": 0.4,
        "y": 0.4,
        "width": 0.1,
        "height": 0.1,
        "center": {"x": 0.45, "y": 0.45},
        "floor_from": 1,
        "floor_to": 10,
        "floors_excluded": [5],
    }
    base.update(overrides)
    return base


def _wire_build_mesh_happy_path(svc: ReconstructionService) -> None:
    """Wire repo/storage mocks for a successful build_mesh run."""
    rec = MagicMock()
    rec.id = 7
    rec.status = 3
    svc._repo.create_reconstruction.return_value = rec
    svc._repo.update_vectorization_data.return_value = rec
    svc._repo.update_mesh.return_value = rec
    svc._storage.load_mask.return_value = np.zeros((200, 200), dtype=np.uint8)
    svc._storage.load_text_blocks.return_value = []
    svc._storage.save_mesh_files.return_value = ("/m.obj", "/m.glb")


def _persisted_rooms(svc: ReconstructionService) -> list[dict]:
    """Decode the JSON handed to update_vectorization_data and return rooms."""
    json_str = svc._repo.update_vectorization_data.call_args[0][1]
    return json.loads(json_str)["rooms"]


@pytest.mark.asyncio
async def test_build_mesh_persists_elevator_floor_fields():
    svc = _make_svc()
    _wire_build_mesh_happy_path(svc)

    with patch(
        "app.processing.contours.extract_elements", return_value=[]
    ), patch(
        "app.processing.pipeline.compute_wall_thickness", return_value=5.0
    ), patch(
        "app.processing.pipeline.normalize_coords",
        side_effect=lambda w, r, d, size: (w, r, d),
    ), patch(
        "app.processing.pipeline.compute_scale_factor", return_value=50.0
    ), patch(
        "app.services.reconstruction_service.build_mesh_from_mask",
        return_value=MagicMock(),
    ):
        await svc.build_mesh(
            "plan_id", "mask_id", user_id=1,
            manual_rooms=[_elevator_room_dict()],
        )

    rooms = _persisted_rooms(svc)
    assert len(rooms) == 1
    assert rooms[0]["room_type"] == "elevator"
    assert rooms[0]["floor_from"] == 1
    assert rooms[0]["floor_to"] == 10
    assert rooms[0]["floors_excluded"] == [5]


@pytest.mark.asyncio
async def test_build_mesh_floor_fields_survive_normalize():
    # Uses the REAL normalize_coords (NOT patched) to prove the rebuild
    # preserves floor_from/floor_to/floors_excluded (round-trip).
    svc = _make_svc()
    _wire_build_mesh_happy_path(svc)

    with patch(
        "app.processing.contours.extract_elements", return_value=[]
    ), patch(
        "app.processing.pipeline.compute_wall_thickness", return_value=5.0
    ), patch(
        "app.processing.pipeline.compute_scale_factor", return_value=50.0
    ), patch(
        "app.services.reconstruction_service.build_mesh_from_mask",
        return_value=MagicMock(),
    ):
        await svc.build_mesh(
            "plan_id", "mask_id", user_id=1,
            manual_rooms=[_elevator_room_dict()],
        )

    rooms = _persisted_rooms(svc)
    assert rooms[0]["floor_from"] == 1
    assert rooms[0]["floor_to"] == 10
    assert rooms[0]["floors_excluded"] == [5]


@pytest.mark.asyncio
async def test_build_mesh_staircase_no_floor_fields():
    svc = _make_svc()
    _wire_build_mesh_happy_path(svc)
    stair = {
        "id": "stair_1",
        "name": "Лестница",
        "room_type": "staircase",
        "x": 0.1,
        "y": 0.1,
        "width": 0.1,
        "height": 0.1,
    }

    with patch(
        "app.processing.contours.extract_elements", return_value=[]
    ), patch(
        "app.processing.pipeline.compute_wall_thickness", return_value=5.0
    ), patch(
        "app.processing.pipeline.normalize_coords",
        side_effect=lambda w, r, d, size: (w, r, d),
    ), patch(
        "app.processing.pipeline.compute_scale_factor", return_value=50.0
    ), patch(
        "app.services.reconstruction_service.build_mesh_from_mask",
        return_value=MagicMock(),
    ):
        await svc.build_mesh(
            "plan_id", "mask_id", user_id=1, manual_rooms=[stair]
        )

    rooms = _persisted_rooms(svc)
    assert rooms[0]["room_type"] == "staircase"
    assert rooms[0]["floor_from"] is None
    assert rooms[0]["floor_to"] is None
    assert rooms[0]["floors_excluded"] == []


def test_get_room_labels_elevator_has_color():
    vr = VectorizationResult(
        walls=[],
        rooms=[
            Room(
                id="elev_1",
                name="Лифт",
                polygon=[Point2D(x=0.4, y=0.4), Point2D(x=0.6, y=0.6)],
                center=Point2D(x=0.5, y=0.5),
                room_type="elevator",
                area_normalized=0.04,
            ),
            Room(
                id="stair_1",
                name="Лестница",
                polygon=[Point2D(x=0.1, y=0.1), Point2D(x=0.2, y=0.2)],
                center=Point2D(x=0.15, y=0.15),
                room_type="staircase",
                area_normalized=0.01,
            ),
        ],
        doors=[],
        text_blocks=[],
        image_size_original=(800, 600),
        image_size_cropped=(800, 600),
    )

    labels = ReconstructionService.get_room_labels(vr)

    by_id = {label["id"]: label for label in labels}
    assert by_id["elev_1"]["color"] == "#6A1B9A"
    # Distinct from room/grey and from each other.
    assert by_id["stair_1"]["color"] == "#2E7D32"
    assert by_id["elev_1"]["color"] != by_id["stair_1"]["color"]
    assert by_id["elev_1"]["color"] != "#c8c8c8"
