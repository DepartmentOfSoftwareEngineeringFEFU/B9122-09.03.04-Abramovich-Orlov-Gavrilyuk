import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import FileStorageError, ImageProcessingError
from app.db.models.reconstruction import Reconstruction
from app.services.reconstruction_service import ReconstructionService


# --- Helpers ---

def _make_svc() -> ReconstructionService:
    repo = AsyncMock()
    storage = AsyncMock()
    svc = ReconstructionService(
        repo=repo,
        storage=storage,
    )
    return svc


def _make_reconstruction(status: int = 2) -> MagicMock:
    rec = MagicMock(spec=Reconstruction)
    rec.id = 1
    rec.status = status
    return rec


_PIPELINE_PATCHES = [
    ("app.processing.contours.extract_elements", [], {}),
    ("app.processing.pipeline.compute_wall_thickness", 5.0, {}),
    ("app.processing.pipeline.room_detect", [], {}),
    ("app.processing.pipeline.classify_rooms", [], {}),
    ("app.processing.pipeline.door_detect", [], {}),
    ("app.processing.pipeline.normalize_coords", ([], [], []), {}),
    ("app.processing.pipeline.compute_scale_factor", 50.0, {}),
    ("app.processing.pipeline.assign_room_numbers", [], {}),
]


# --- Tests ---

@pytest.mark.asyncio
async def test_build_mesh_success_sets_status_3():
    # Arrange
    svc = _make_svc()

    rec_processing = _make_reconstruction(status=2)
    rec_done = _make_reconstruction(status=3)

    svc._repo.create_reconstruction.return_value = rec_processing
    svc._repo.update_vectorization_data.return_value = rec_processing
    svc._repo.update_mesh.return_value = rec_done
    svc._storage.load_mask.return_value = np.zeros((200, 200), dtype=np.uint8)
    svc._storage.load_text_blocks.return_value = []
    svc._storage.save_mesh_files.return_value = (
        "/path/to/model.obj",
        "/path/to/model.glb",
    )

    fake_mesh = MagicMock()

    with patch(
        "app.processing.contours.extract_elements", return_value=[]
    ), patch(
        "app.processing.pipeline.compute_wall_thickness",
        return_value=5.0,
    ), patch(
        "app.processing.pipeline.room_detect", return_value=[]
    ), patch(
        "app.processing.pipeline.classify_rooms", return_value=[]
    ), patch(
        "app.processing.pipeline.door_detect", return_value=[]
    ), patch(
        "app.processing.pipeline.normalize_coords",
        return_value=([], [], []),
    ), patch(
        "app.processing.pipeline.compute_scale_factor", return_value=50.0
    ), patch(
        "app.services.reconstruction_service.build_mesh_from_mask",
        return_value=fake_mesh,
    ):

        # Act
        result = await svc.build_mesh("plan_id", "mask_id", user_id=1)

    # Assert
    assert result.status == 3
    svc._storage.save_mesh_files.assert_called_once()


@pytest.mark.asyncio
async def test_build_mesh_mask_not_found_sets_status_4():
    # Arrange
    svc = _make_svc()

    rec_processing = _make_reconstruction(status=2)
    rec_error = _make_reconstruction(status=4)

    svc._repo.create_reconstruction.return_value = rec_processing
    svc._repo.update_mesh.return_value = rec_error
    svc._storage.load_mask.side_effect = FileStorageError(
        "missing_mask_id", "pattern"
    )

    # Act
    result = await svc.build_mesh("plan_id", "missing_mask_id", user_id=1)

    # Assert
    assert result.status == 4
    svc._repo.update_mesh.assert_called_once()
    _call = svc._repo.update_mesh.call_args
    assert _call.args == (rec_processing.id, None, None)
    assert _call.kwargs["status"] == 4
    # The message keeps the "Ошибка построения модели" prefix and appends the
    # specific cause (e.g. "...: FileStorageError: ...").
    assert _call.kwargs["error_message"].startswith("Ошибка построения модели")


@pytest.mark.asyncio
async def test_build_mesh_processing_error_sets_status_4():
    # Arrange
    svc = _make_svc()

    rec_processing = _make_reconstruction(status=2)
    rec_error = _make_reconstruction(status=4)

    svc._repo.create_reconstruction.return_value = rec_processing
    svc._repo.update_vectorization_data.return_value = rec_processing
    svc._repo.update_mesh.return_value = rec_error
    svc._storage.load_mask.return_value = np.zeros((200, 200), dtype=np.uint8)
    svc._storage.load_text_blocks.return_value = []

    with patch(
        "app.processing.contours.extract_elements", return_value=[]
    ), patch(
        "app.processing.pipeline.compute_wall_thickness",
        return_value=5.0,
    ), patch(
        "app.processing.pipeline.room_detect", return_value=[]
    ), patch(
        "app.processing.pipeline.classify_rooms", return_value=[]
    ), patch(
        "app.processing.pipeline.door_detect", return_value=[]
    ), patch(
        "app.processing.pipeline.normalize_coords",
        return_value=([], [], []),
    ), patch(
        "app.processing.pipeline.compute_scale_factor", return_value=50.0
    ), patch(
        "app.services.reconstruction_service.build_mesh_from_mask",
        side_effect=ImageProcessingError(
            "build_mesh_from_mask", "No wall contours found in mask"
        ),
    ):

        # Act
        result = await svc.build_mesh("plan_id", "mask_id", user_id=1)

    # Assert
    assert result.status == 4
    svc._repo.update_mesh.assert_called_once()
    _call = svc._repo.update_mesh.call_args
    assert _call.args == (rec_processing.id, None, None)
    assert _call.kwargs["status"] == 4
    # The message keeps the "Ошибка построения модели" prefix and appends the
    # specific cause (e.g. "...: FileStorageError: ...").
    assert _call.kwargs["error_message"].startswith("Ошибка построения модели")


@pytest.mark.asyncio
async def test_build_mesh_uses_default_floor_height_3m():
    # Arrange
    svc = _make_svc()

    rec_processing = _make_reconstruction(status=2)
    rec_done = _make_reconstruction(status=3)

    svc._repo.create_reconstruction.return_value = rec_processing
    svc._repo.update_vectorization_data.return_value = rec_processing
    svc._repo.update_mesh.return_value = rec_done
    svc._storage.load_mask.return_value = np.zeros((200, 200), dtype=np.uint8)
    svc._storage.load_text_blocks.return_value = []
    svc._storage.save_mesh_files.return_value = (
        "/path/to/model.obj",
        "/path/to/model.glb",
    )

    fake_mesh = MagicMock()
    mock_build = MagicMock(return_value=fake_mesh)

    with patch(
        "app.processing.contours.extract_elements", return_value=[]
    ), patch(
        "app.processing.pipeline.compute_wall_thickness",
        return_value=5.0,
    ), patch(
        "app.processing.pipeline.room_detect", return_value=[]
    ), patch(
        "app.processing.pipeline.classify_rooms", return_value=[]
    ), patch(
        "app.processing.pipeline.door_detect", return_value=[]
    ), patch(
        "app.processing.pipeline.normalize_coords",
        return_value=([], [], []),
    ), patch(
        "app.processing.pipeline.compute_scale_factor", return_value=50.0
    ), patch(
        "app.services.reconstruction_service.build_mesh_from_mask",
        mock_build,
    ):

        # Act
        await svc.build_mesh("plan_id", "mask_id", user_id=1)

    # Assert
    mock_build.assert_called_once()
    _, kwargs = mock_build.call_args
    assert kwargs.get("floor_height") == 3.0, (
        f"Expected floor_height=3.0, got {kwargs.get('floor_height')}"
    )
