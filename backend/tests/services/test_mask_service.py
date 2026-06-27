import json
import os
import shutil
import tempfile
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.core.exceptions import FileStorageError, ImageProcessingError
from app.models.domain import Point2D, TextBlock
from app.services.mask_service import MaskService


@pytest.fixture
def ascii_tmp_dir():
    """Provide a temp directory with ASCII-only path (avoids cv2.imread Unicode issues on Windows)."""
    base = tempfile.gettempdir()
    # Use a simple ASCII path under the system temp dir
    dirpath = os.path.join(base, "diplom_tests_mask")
    os.makedirs(os.path.join(dirpath, "plans"), exist_ok=True)
    os.makedirs(os.path.join(dirpath, "masks"), exist_ok=True)
    yield dirpath
    shutil.rmtree(dirpath, ignore_errors=True)


@pytest.mark.asyncio
async def test_calculate_mask_valid_file_returns_filename(ascii_tmp_dir):
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (10, 10), (90, 90), (0, 0, 0), thickness=3)
    plan_path = os.path.join(ascii_tmp_dir, "plans", "test-id.jpg")
    cv2.imwrite(plan_path, img)

    svc = MaskService(upload_dir=ascii_tmp_dir)
    filename = await svc.calculate_mask("test-id")
    assert filename == "test-id.png"
    assert os.path.exists(os.path.join(ascii_tmp_dir, "masks", "test-id.png"))


@pytest.mark.asyncio
async def test_calculate_mask_default_pipeline_produces_visible_walls(ascii_tmp_dir):
    """Regression: default pipeline must not destroy walls with normalize/color_filter/auto_crop."""
    # Create a synthetic plan: white background with black rectangle (walls)
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (30, 30), (170, 170), (0, 0, 0), thickness=4)
    cv2.rectangle(img, (60, 60), (140, 140), (0, 0, 0), thickness=3)
    plan_path = os.path.join(ascii_tmp_dir, "plans", "regression.jpg")
    cv2.imwrite(plan_path, img)

    svc = MaskService(upload_dir=ascii_tmp_dir)
    filename = await svc.calculate_mask("regression")

    mask = cv2.imread(os.path.join(ascii_tmp_dir, "masks", filename), cv2.IMREAD_GRAYSCALE)
    white_ratio = np.sum(mask == 255) / mask.size

    # Walls should be visible: at least 3% white pixels (was ~0% when bug was present)
    assert white_ratio > 0.03, f"Mask is too dark ({white_ratio:.1%} white), walls not detected"


@pytest.mark.asyncio
async def test_calculate_mask_no_auto_crop_when_crop_is_none(ascii_tmp_dir):
    """Regression: auto_crop_suggest must NOT run when crop=None."""
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (20, 20), (180, 180), (0, 0, 0), thickness=3)
    plan_path = os.path.join(ascii_tmp_dir, "plans", "nocrop.jpg")
    cv2.imwrite(plan_path, img)

    svc = MaskService(upload_dir=ascii_tmp_dir)
    filename = await svc.calculate_mask("nocrop", crop=None)

    mask = cv2.imread(os.path.join(ascii_tmp_dir, "masks", filename), cv2.IMREAD_GRAYSCALE)
    # Without auto-crop, mask should be same size as input
    assert mask.shape == (200, 200)


@pytest.mark.asyncio
async def test_calculate_mask_missing_file_raises_not_found(tmp_path):
    (tmp_path / "plans").mkdir()
    (tmp_path / "masks").mkdir()
    svc = MaskService(upload_dir=str(tmp_path))
    with pytest.raises(FileStorageError):
        await svc.calculate_mask("nonexistent-id")


# ---: Service integration tests ---

def _write_plan(dirpath: str, file_id: str) -> np.ndarray:
    """Create a synthetic plan image and write it to plans/. Returns the image."""
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (10, 10), (90, 90), (0, 0, 0), thickness=3)
    cv2.imwrite(os.path.join(dirpath, "plans", f"{file_id}.jpg"), img)
    return img


@pytest.mark.asyncio
@patch("app.services.mask_service.remove_colored_elements")
async def test_calculate_mask_calls_color_removal(mock_color_rm, ascii_tmp_dir):
    img = _write_plan(ascii_tmp_dir, "test-color")
    mock_color_rm.return_value = img

    svc = MaskService(upload_dir=ascii_tmp_dir)
    await svc.calculate_mask("test-color")

    mock_color_rm.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.mask_service.remove_text_regions")
@patch("app.services.mask_service.text_detect")
async def test_calculate_mask_calls_text_removal(mock_text_detect, mock_remove_regions, ascii_tmp_dir):
    img = _write_plan(ascii_tmp_dir, "test-text")
    tb = TextBlock(
        text="101",
        center=Point2D(x=0.5, y=0.5),
        confidence=0.9,
        is_room_number=True,
    )
    mock_text_detect.return_value = [tb]
    mask_placeholder = np.zeros((100, 100), dtype=np.uint8)
    mock_remove_regions.return_value = mask_placeholder

    svc = MaskService(upload_dir=ascii_tmp_dir)
    await svc.calculate_mask("test-text")

    mock_text_detect.assert_called_once()
    mock_remove_regions.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.mask_service.remove_colored_elements")
async def test_calculate_mask_color_removal_disabled(mock_color_rm, ascii_tmp_dir):
    _write_plan(ascii_tmp_dir, "test-no-color")

    svc = MaskService(upload_dir=ascii_tmp_dir)
    await svc.calculate_mask("test-no-color", enable_color_removal=False)

    mock_color_rm.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.mask_service.text_detect")
async def test_calculate_mask_text_removal_disabled(mock_text_detect, ascii_tmp_dir):
    _write_plan(ascii_tmp_dir, "test-no-text")

    svc = MaskService(upload_dir=ascii_tmp_dir)
    await svc.calculate_mask("test-no-text", enable_text_removal=False)

    mock_text_detect.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.mask_service.remove_text_regions")
@patch("app.services.mask_service.text_detect")
async def test_calculate_mask_saves_text_json(mock_text_detect, mock_remove_regions, ascii_tmp_dir):
    img = _write_plan(ascii_tmp_dir, "test-json")
    tb = TextBlock(
        text="202",
        center=Point2D(x=0.3, y=0.7),
        confidence=0.85,
        is_room_number=True,
    )
    mock_text_detect.return_value = [tb]
    mock_remove_regions.return_value = np.zeros((100, 100), dtype=np.uint8)

    svc = MaskService(upload_dir=ascii_tmp_dir)
    await svc.calculate_mask("test-json")

    json_path = os.path.join(ascii_tmp_dir, "masks", "test-json_text.json")
    assert os.path.exists(json_path)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["text"] == "202"
    assert data[0]["center"] == {"x": 0.3, "y": 0.7}
    assert data[0]["is_room_number"] is True


@pytest.mark.asyncio
@patch("app.services.mask_service.text_detect")
async def test_calculate_mask_no_text_blocks_skips_json(mock_text_detect, ascii_tmp_dir):
    _write_plan(ascii_tmp_dir, "test-no-json")
    mock_text_detect.return_value = []

    svc = MaskService(upload_dir=ascii_tmp_dir)
    await svc.calculate_mask("test-no-json")

    json_path = os.path.join(ascii_tmp_dir, "masks", "test-no-json_text.json")
    assert not os.path.exists(json_path)
    assert os.path.exists(os.path.join(ascii_tmp_dir, "masks", "test-no-json.png"))


@pytest.mark.asyncio
async def test_calculate_mask_corrupt_file_raises_processing_error(ascii_tmp_dir):
    corrupt_path = os.path.join(ascii_tmp_dir, "plans", "corrupt.jpg")
    with open(corrupt_path, "wb") as f:
        f.write(b"not an image")

    svc = MaskService(upload_dir=ascii_tmp_dir)
    with pytest.raises(ImageProcessingError):
        await svc.calculate_mask("corrupt")


@pytest.mark.asyncio
async def test_calculate_mask_crop_out_of_bounds_still_produces_mask(ascii_tmp_dir):
    """Crop params that exceed image bounds are clamped — service must not crash."""
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (10, 10), (90, 90), (0, 0, 0), thickness=3)
    cv2.imwrite(os.path.join(ascii_tmp_dir, "plans", "oob.jpg"), img)

    svc = MaskService(upload_dir=ascii_tmp_dir)
    # x=0.9, width=0.5 → clamped to available pixels, should not raise
    filename = await svc.calculate_mask("oob", crop={"x": 0.9, "y": 0.0, "width": 0.5, "height": 1.0})

    assert filename == "oob.png"
    assert os.path.exists(os.path.join(ascii_tmp_dir, "masks", "oob.png"))
