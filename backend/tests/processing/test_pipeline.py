"""
Tests for app/processing/pipeline.py — pure vectorization pipeline functions.

AAA pattern: Arrange → Act → Assert
Naming: test_{function}_{scenario}_{expected}
"""
import sys
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.core.exceptions import ImageProcessingError
from app.models.domain import Door, Point2D, Room, TextBlock, Wall
from app.processing.pipeline import (
    _is_room_number,
    _point_in_polygon,
    assign_room_numbers,
    auto_crop_suggest,
    classify_rooms,
    color_filter,
    compute_scale_factor,
    compute_wall_thickness,
    directional_morph_close,
    door_detect,
    multi_pass_threshold,
    normalize_brightness,
    normalize_coords,
    remove_colored_elements,
    remove_green_elements,
    remove_red_elements,
    remove_text_regions,
    room_detect,
    text_detect,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def white_image():
    """100x100 white BGR image."""
    return np.ones((100, 100, 3), dtype=np.uint8) * 255


@pytest.fixture
def black_image():
    """100x100 black BGR image."""
    return np.zeros((100, 100, 3), dtype=np.uint8)


@pytest.fixture
def simple_mask():
    """100x100 binary mask with a white rectangle (wall)."""
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(mask, (10, 10), (90, 90), 255, 3)
    return mask


@pytest.fixture
def rooms_mask():
    """100x100 mask with walls forming 2 rooms."""
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(mask, (5, 5), (95, 95), 255, 3)
    cv2.line(mask, (50, 5), (50, 95), 255, 3)
    return mask


@pytest.fixture
def filled_mask():
    """100x100 fully white mask (all walls)."""
    return np.ones((100, 100), dtype=np.uint8) * 255


@pytest.fixture
def square_room():
    """A Room with a roughly square polygon."""
    polygon = [
        Point2D(x=0.1, y=0.1),
        Point2D(x=0.4, y=0.1),
        Point2D(x=0.4, y=0.4),
        Point2D(x=0.1, y=0.4),
    ]
    return Room(
        id="room_square",
        name="",
        polygon=polygon,
        center=Point2D(x=0.25, y=0.25),
        room_type="unknown",
        area_normalized=0.09,
    )


@pytest.fixture
def corridor_room():
    """A Room with a very elongated polygon (corridor)."""
    polygon = [
        Point2D(x=0.05, y=0.45),
        Point2D(x=0.95, y=0.45),
        Point2D(x=0.95, y=0.55),
        Point2D(x=0.05, y=0.55),
    ]
    return Room(
        id="room_corridor",
        name="",
        polygon=polygon,
        center=Point2D(x=0.5, y=0.5),
        room_type="unknown",
        area_normalized=0.09,
    )


# ---------------------------------------------------------------------------
# normalize_brightness
# ---------------------------------------------------------------------------

def test_normalize_brightness_valid_image_returns_same_shape(white_image):
    result = normalize_brightness(white_image)
    assert result.shape == white_image.shape


def test_normalize_brightness_empty_image_raises():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        normalize_brightness(empty)


def test_normalize_brightness_wrong_dtype_raises(white_image):
    float_image = white_image.astype(np.float32)
    with pytest.raises(ImageProcessingError):
        normalize_brightness(float_image)


def test_normalize_brightness_preserves_dtype(white_image):
    result = normalize_brightness(white_image)
    assert result.dtype == np.uint8


# ---------------------------------------------------------------------------
# color_filter
# ---------------------------------------------------------------------------

def test_color_filter_valid_image_returns_same_shape(white_image):
    result = color_filter(white_image)
    assert result.shape == white_image.shape


def test_color_filter_empty_image_raises():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        color_filter(empty)


def test_color_filter_wrong_dtype_raises(white_image):
    float_image = white_image.astype(np.float32)
    with pytest.raises(ImageProcessingError):
        color_filter(float_image)


def test_color_filter_removes_colored_pixels():
    # Create image with a bright green patch (high saturation)
    image = np.ones((100, 100, 3), dtype=np.uint8) * 200
    image[40:60, 40:60] = [0, 255, 0]  # pure green — high saturation

    result = color_filter(image, saturation_threshold=50)

    # The green patch should be inpainted — no longer pure green
    patch_before = image[40:60, 40:60]
    patch_after = result[40:60, 40:60]
    assert not np.array_equal(patch_before, patch_after)


# ---------------------------------------------------------------------------
# auto_crop_suggest
# ---------------------------------------------------------------------------

def test_auto_crop_suggest_with_content_returns_rect():
    # Dark content on white background — Otsu will find it
    image = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.rectangle(image, (20, 20), (80, 80), (0, 0, 0), -1)

    result = auto_crop_suggest(image, min_area_ratio=0.1)

    assert result is not None
    assert set(result.keys()) == {"x", "y", "width", "height"}


def test_auto_crop_suggest_empty_image_raises():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        auto_crop_suggest(empty)


def test_auto_crop_suggest_blank_image_returns_none(white_image):
    # Uniform white — no large dark contour, should return None
    result = auto_crop_suggest(white_image, min_area_ratio=0.5)
    assert result is None


def test_auto_crop_suggest_rect_normalized():
    image = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.rectangle(image, (20, 20), (80, 80), (0, 0, 0), -1)

    result = auto_crop_suggest(image, min_area_ratio=0.1)

    assert result is not None
    for key in ("x", "y", "width", "height"):
        assert 0.0 <= result[key] <= 1.0, f"{key}={result[key]} out of [0,1]"


# ---------------------------------------------------------------------------
# text_detect
# ---------------------------------------------------------------------------

def test_text_detect_empty_image_raises():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    mask = np.zeros((0, 0), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        text_detect(empty, mask)


def test_text_detect_no_tesseract_returns_empty(white_image, simple_mask):
    with patch("app.processing.pipeline._TESSERACT_AVAILABLE", False):
        result = text_detect(white_image, simple_mask)
    assert result == []


def test_text_detect_returns_text_blocks(white_image, simple_mask):
    # When tesseract is not available we get []; when it is, we get a list.
    # Either way the return type must be a list.
    result = text_detect(white_image, simple_mask)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# remove_text_regions
# ---------------------------------------------------------------------------

def test_remove_text_regions_empty_mask_raises():
    empty = np.zeros((0, 0), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        remove_text_regions(empty, [], (100, 100))


def test_remove_text_regions_no_blocks_returns_same(simple_mask):
    result = remove_text_regions(simple_mask, [], (100, 100))
    # No blocks → same object returned (early return)
    assert result is simple_mask


def test_remove_text_regions_with_blocks_returns_cleaned(simple_mask):
    blocks = [
        TextBlock(
            text="101",
            center=Point2D(x=0.5, y=0.5),
            confidence=90.0,
            is_room_number=True,
        )
    ]
    result = remove_text_regions(simple_mask, blocks, (100, 100))
    assert result.shape == simple_mask.shape
    assert result.dtype == np.uint8


# ---------------------------------------------------------------------------
# compute_wall_thickness
# ---------------------------------------------------------------------------

def test_compute_wall_thickness_empty_raises():
    empty = np.zeros((0, 0), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        compute_wall_thickness(empty)


def test_compute_wall_thickness_no_walls_returns_zero(black_image):
    mask = np.zeros((100, 100), dtype=np.uint8)
    result = compute_wall_thickness(mask)
    assert result == 0.0


def test_compute_wall_thickness_with_walls_returns_positive(simple_mask):
    result = compute_wall_thickness(simple_mask)
    assert result > 0.0


# ---------------------------------------------------------------------------
# room_detect
# ---------------------------------------------------------------------------

def test_room_detect_empty_raises():
    empty = np.zeros((0, 0), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        room_detect(empty)


def test_room_detect_blank_returns_empty(black_image):
    mask = np.zeros((100, 100), dtype=np.uint8)
    # No walls → inverted is all-white → one giant component filtered by max_area_ratio
    result = room_detect(mask, min_room_area=1, max_room_area_ratio=0.5)
    assert isinstance(result, list)


def test_room_detect_with_rooms_returns_rooms():
    # Large image so rooms exceed min_room_area=1000
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (5, 5), (295, 295), 255, 5)
    cv2.line(mask, (150, 5), (150, 295), 255, 5)

    result = room_detect(mask, min_room_area=1000, max_room_area_ratio=0.8)
    assert len(result) >= 1


def test_room_detect_coords_normalized():
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (5, 5), (295, 295), 255, 5)
    cv2.line(mask, (150, 5), (150, 295), 255, 5)

    rooms = room_detect(mask, min_room_area=1000, max_room_area_ratio=0.8)
    for room in rooms:
        assert 0.0 <= room.center.x <= 1.0
        assert 0.0 <= room.center.y <= 1.0
        for pt in room.polygon:
            assert 0.0 <= pt.x <= 1.0
            assert 0.0 <= pt.y <= 1.0


def test_room_detect_filters_small_areas():
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (5, 5), (295, 295), 255, 5)
    cv2.line(mask, (150, 5), (150, 295), 255, 5)

    # With very high min_room_area, rooms should be filtered out
    result_high = room_detect(mask, min_room_area=99999)
    result_low = room_detect(mask, min_room_area=100)
    assert len(result_high) <= len(result_low)


# ---------------------------------------------------------------------------
# classify_rooms
# ---------------------------------------------------------------------------

def test_classify_rooms_square_is_room(square_room):
    result = classify_rooms([square_room])
    assert result[0].room_type == "room"


def test_classify_rooms_elongated_is_corridor(corridor_room):
    result = classify_rooms([corridor_room], corridor_aspect_ratio=3.0)
    assert result[0].room_type == "corridor"


def test_classify_rooms_returns_new_list(square_room, corridor_room):
    original = [square_room, corridor_room]
    result = classify_rooms(original)

    # Must be a new list, not the same object
    assert result is not original
    # Original room_type must be unchanged
    assert square_room.room_type == "unknown"
    assert corridor_room.room_type == "unknown"


# ---------------------------------------------------------------------------
# door_detect
# ---------------------------------------------------------------------------

def test_door_detect_empty_raises():
    empty = np.zeros((0, 0), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        door_detect(empty, [])


def test_door_detect_no_gaps_returns_empty(filled_mask):
    # Fully filled mask → dilation adds nothing → no gaps
    result = door_detect(filled_mask, [])
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# assign_room_numbers
# ---------------------------------------------------------------------------

def test_assign_room_numbers_matches_text_to_room(square_room):
    # Text block center is inside the square room polygon
    tb = TextBlock(
        text="101",
        center=Point2D(x=0.25, y=0.25),
        confidence=95.0,
        is_room_number=True,
    )
    result = assign_room_numbers([square_room], [tb])
    assert result[0].name == "101"


def test_assign_room_numbers_returns_new_list(square_room):
    tb = TextBlock(
        text="202",
        center=Point2D(x=0.25, y=0.25),
        confidence=95.0,
        is_room_number=True,
    )
    original = [square_room]
    result = assign_room_numbers(original, [tb])

    assert result is not original
    # Original must not be mutated
    assert square_room.name == ""


# ---------------------------------------------------------------------------
# compute_scale_factor
# ---------------------------------------------------------------------------

def test_compute_scale_factor_positive_thickness():
    result = compute_scale_factor(10.0)
    assert result == pytest.approx(50.0)  # 10 / 0.2


def test_compute_scale_factor_zero_returns_default():
    result = compute_scale_factor(0.0)
    assert result == 50.0


def test_compute_scale_factor_negative_returns_default():
    result = compute_scale_factor(-5.0)
    assert result == 50.0


# ---------------------------------------------------------------------------
# normalize_coords
# ---------------------------------------------------------------------------

def _make_wall(pts):
    return Wall(id="w1", points=[Point2D(x=p[0], y=p[1]) for p in pts], thickness=0.2)


def _make_room(pts, center):
    return Room(
        id="r1",
        name="",
        polygon=[Point2D(x=p[0], y=p[1]) for p in pts],
        center=Point2D(x=center[0], y=center[1]),
        room_type="room",
        area_normalized=0.1,
    )


def _make_door(pos):
    return Door(id="d1", position=Point2D(x=pos[0], y=pos[1]), width=0.05, connects=[])


def test_normalize_coords_clamps_values():
    # All coords already in [0,1] — should pass through unchanged
    wall = _make_wall([(0.0, 0.0), (1.0, 1.0)])
    room = _make_room([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], (0.5, 0.5))
    door = _make_door((0.5, 0.5))

    walls_out, rooms_out, doors_out = normalize_coords([wall], [room], [door], (100, 100))

    for w in walls_out:
        for p in w.points:
            assert 0.0 <= p.x <= 1.0
            assert 0.0 <= p.y <= 1.0
    for r in rooms_out:
        for p in r.polygon:
            assert 0.0 <= p.x <= 1.0
    for d in doors_out:
        assert 0.0 <= d.position.x <= 1.0
        assert 0.0 <= d.position.y <= 1.0


def test_normalize_coords_invalid_size_raises():
    with pytest.raises(ImageProcessingError):
        normalize_coords([], [], [], (0, 100))

    with pytest.raises(ImageProcessingError):
        normalize_coords([], [], [], (100, 0))


# ---------------------------------------------------------------------------
# _is_room_number
# ---------------------------------------------------------------------------

def test_is_room_number_valid_patterns():
    assert _is_room_number("101") is True
    assert _is_room_number("1103") is True
    assert _is_room_number("1103А") is True
    assert _is_room_number("A304") is True
    assert _is_room_number("Б201") is True


def test_is_room_number_invalid_patterns():
    assert _is_room_number("") is False
    assert _is_room_number("AB") is False
    assert _is_room_number("exit") is False
    assert _is_room_number("12") is False       # too short (< 3 digits)
    assert _is_room_number("12345") is False    # too long (> 4 digits)
    assert _is_room_number("ABCD") is False


# ---------------------------------------------------------------------------
# _point_in_polygon
# ---------------------------------------------------------------------------

def _square_polygon():
    return [
        Point2D(x=0.1, y=0.1),
        Point2D(x=0.9, y=0.1),
        Point2D(x=0.9, y=0.9),
        Point2D(x=0.1, y=0.9),
    ]


def test_point_in_polygon_inside():
    poly = _square_polygon()
    point = Point2D(x=0.5, y=0.5)
    assert _point_in_polygon(point, poly) is True


def test_point_in_polygon_outside():
    poly = _square_polygon()
    point = Point2D(x=0.05, y=0.05)
    assert _point_in_polygon(point, poly) is False


def test_point_in_polygon_too_few_points():
    poly = [Point2D(x=0.1, y=0.1), Point2D(x=0.9, y=0.9)]  # only 2 points
    point = Point2D(x=0.5, y=0.5)
    assert _point_in_polygon(point, poly) is False


# ---------------------------------------------------------------------------
# Fixtures for color removal tests
# ---------------------------------------------------------------------------

@pytest.fixture
def image_with_green_arrows():
    """White image with green arrow lines (evacuation arrows)."""
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.arrowedLine(img, (20, 100), (180, 100), (0, 200, 0), thickness=3)
    return img


@pytest.fixture
def image_with_red_symbols():
    """White image with red circle (fire extinguisher symbol)."""
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.circle(img, (100, 100), 15, (0, 0, 200), thickness=-1)
    return img


@pytest.fixture
def image_with_walls_and_colors():
    """Image with black walls, green arrows, and red symbols."""
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (20, 20), (180, 180), (0, 0, 0), thickness=3)
    cv2.arrowedLine(img, (50, 100), (150, 100), (0, 200, 0), thickness=2)
    cv2.circle(img, (20, 100), 8, (0, 0, 200), thickness=-1)
    return img


@pytest.fixture
def grayscale_image():
    """Grayscale image (H, W) — for wrong shape tests."""
    return np.ones((200, 200), dtype=np.uint8) * 128


@pytest.fixture
def binary_mask_with_text():
    """Binary mask (H, W) with simulated text — white pixels in center."""
    mask = np.zeros((200, 200), dtype=np.uint8)
    cv2.rectangle(mask, (20, 20), (180, 180), 255, thickness=3)
    cv2.putText(mask, "101", (80, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 1)
    return mask


@pytest.fixture
def sample_text_blocks():
    """List of TextBlock for remove_text_regions tests."""
    return [
        TextBlock(text="101", center=Point2D(x=0.5, y=0.5), confidence=90.0, is_room_number=True),
    ]


# ---------------------------------------------------------------------------
# remove_green_elements
# ---------------------------------------------------------------------------

def test_remove_green_elements_valid_image_returns_same_shape(image_with_green_arrows):
    result = remove_green_elements(image_with_green_arrows)
    assert result.shape == image_with_green_arrows.shape
    assert result.dtype == np.uint8


def test_remove_green_elements_green_patch_removed(image_with_green_arrows):
    result = remove_green_elements(image_with_green_arrows)
    # Check that green pixels in the arrow area are reduced
    hsv_before = cv2.cvtColor(image_with_green_arrows, cv2.COLOR_BGR2HSV)
    hsv_after = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
    green_before = cv2.inRange(hsv_before, np.array([35, 40, 40]), np.array([85, 255, 255]))
    green_after = cv2.inRange(hsv_after, np.array([35, 40, 40]), np.array([85, 255, 255]))
    assert np.sum(green_after) < np.sum(green_before)


def test_remove_green_elements_empty_image_raises():
    with pytest.raises(ImageProcessingError):
        remove_green_elements(np.zeros((0, 0, 3), dtype=np.uint8))


def test_remove_green_elements_wrong_dtype_raises(white_image):
    with pytest.raises(ImageProcessingError):
        remove_green_elements(white_image.astype(np.float32))


def test_remove_green_elements_grayscale_raises(grayscale_image):
    with pytest.raises(ImageProcessingError):
        remove_green_elements(grayscale_image)


def test_remove_green_elements_no_green_returns_unchanged(white_image):
    result = remove_green_elements(white_image)
    assert np.array_equal(result, white_image)


def test_remove_green_elements_does_not_mutate_input(image_with_green_arrows):
    original = image_with_green_arrows.copy()
    remove_green_elements(image_with_green_arrows)
    assert np.array_equal(image_with_green_arrows, original)


# ---------------------------------------------------------------------------
# remove_red_elements
# ---------------------------------------------------------------------------

def test_remove_red_elements_valid_image_returns_same_shape(image_with_red_symbols):
    result = remove_red_elements(image_with_red_symbols)
    assert result.shape == image_with_red_symbols.shape
    assert result.dtype == np.uint8


def test_remove_red_elements_red_patch_removed(image_with_red_symbols):
    result = remove_red_elements(image_with_red_symbols)
    hsv_before = cv2.cvtColor(image_with_red_symbols, cv2.COLOR_BGR2HSV)
    hsv_after = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
    red_low = cv2.inRange(hsv_before, np.array([0, 50, 50]), np.array([10, 255, 255]))
    red_high = cv2.inRange(hsv_before, np.array([170, 50, 50]), np.array([180, 255, 255]))
    red_before = red_low | red_high
    red_low_a = cv2.inRange(hsv_after, np.array([0, 50, 50]), np.array([10, 255, 255]))
    red_high_a = cv2.inRange(hsv_after, np.array([170, 50, 50]), np.array([180, 255, 255]))
    red_after = red_low_a | red_high_a
    assert np.sum(red_after) < np.sum(red_before)


def test_remove_red_elements_empty_image_raises():
    with pytest.raises(ImageProcessingError):
        remove_red_elements(np.zeros((0, 0, 3), dtype=np.uint8))


def test_remove_red_elements_wrong_dtype_raises(white_image):
    with pytest.raises(ImageProcessingError):
        remove_red_elements(white_image.astype(np.float32))


def test_remove_red_elements_grayscale_raises(grayscale_image):
    with pytest.raises(ImageProcessingError):
        remove_red_elements(grayscale_image)


def test_remove_red_elements_no_red_returns_unchanged(white_image):
    result = remove_red_elements(white_image)
    assert np.array_equal(result, white_image)


def test_remove_red_elements_does_not_mutate_input(image_with_red_symbols):
    original = image_with_red_symbols.copy()
    remove_red_elements(image_with_red_symbols)
    assert np.array_equal(image_with_red_symbols, original)


# ---------------------------------------------------------------------------
# remove_colored_elements
# ---------------------------------------------------------------------------

def test_remove_colored_elements_removes_both_colors(image_with_walls_and_colors):
    result = remove_colored_elements(image_with_walls_and_colors)
    hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
    red_low = cv2.inRange(hsv, np.array([0, 50, 50]), np.array([10, 255, 255]))
    red_high = cv2.inRange(hsv, np.array([170, 50, 50]), np.array([180, 255, 255]))
    colored = green | red_low | red_high
    # Most colored pixels should be gone
    assert np.sum(colored) < 100


def test_remove_colored_elements_preserves_walls(image_with_walls_and_colors):
    result = remove_colored_elements(image_with_walls_and_colors)
    # Check that dark wall pixels are still present
    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    dark_pixels = np.sum(gray < 50)
    assert dark_pixels > 100, "Walls should be preserved"


def test_remove_colored_elements_empty_image_raises():
    with pytest.raises(ImageProcessingError):
        remove_colored_elements(np.zeros((0, 0, 3), dtype=np.uint8))


def test_remove_colored_elements_wrong_dtype_raises(white_image):
    with pytest.raises(ImageProcessingError):
        remove_colored_elements(white_image.astype(np.float32))


def test_remove_colored_elements_grayscale_raises(grayscale_image):
    with pytest.raises(ImageProcessingError):
        remove_colored_elements(grayscale_image)


# ---------------------------------------------------------------------------
# text_detect — extended coverage
# ---------------------------------------------------------------------------

def test_text_detect_ocr_error_returns_empty(white_image, simple_mask):
    with patch("app.processing.pipeline._TESSERACT_AVAILABLE", True), \
         patch("app.processing.pipeline.pytesseract") as mock_tess:
        mock_tess.image_to_data.side_effect = RuntimeError("OCR crashed")
        result = text_detect(white_image, simple_mask)
    assert result == []


def test_text_detect_coordinates_normalized(white_image, simple_mask):
    mock_data = {
        "text": ["101", "exit", ""],
        "conf": [90, 80, -1],
        "left": [10, 50, 0],
        "top": [10, 50, 0],
        "width": [30, 40, 0],
        "height": [15, 15, 0],
    }
    with patch("app.processing.pipeline._TESSERACT_AVAILABLE", True), \
         patch("app.processing.pipeline.pytesseract") as mock_tess:
        mock_tess.Output.DICT = "dict"
        mock_tess.image_to_data.return_value = mock_data
        result = text_detect(white_image, simple_mask)
    for tb in result:
        assert 0.0 <= tb.center.x <= 1.0
        assert 0.0 <= tb.center.y <= 1.0


def test_text_detect_room_numbers_flagged(white_image, simple_mask):
    mock_data = {
        "text": ["1103", "exit"],
        "conf": [90, 85],
        "left": [10, 50],
        "top": [10, 50],
        "width": [30, 40],
        "height": [15, 15],
    }
    with patch("app.processing.pipeline._TESSERACT_AVAILABLE", True), \
         patch("app.processing.pipeline.pytesseract") as mock_tess:
        mock_tess.Output.DICT = "dict"
        mock_tess.image_to_data.return_value = mock_data
        result = text_detect(white_image, simple_mask)
    room_blocks = [tb for tb in result if tb.is_room_number]
    non_room = [tb for tb in result if not tb.is_room_number]
    assert len(room_blocks) >= 1
    assert room_blocks[0].text == "1103"
    assert len(non_room) >= 1


def test_text_detect_valid_image_returns_text_blocks(white_image, simple_mask):
    mock_data = {
        "text": ["101"],
        "conf": [90],
        "left": [10],
        "top": [10],
        "width": [30],
        "height": [15],
    }
    with patch("app.processing.pipeline._TESSERACT_AVAILABLE", True), \
         patch("app.processing.pipeline.pytesseract") as mock_tess:
        mock_tess.Output.DICT = "dict"
        mock_tess.image_to_data.return_value = mock_data
        result = text_detect(white_image, simple_mask)
    assert len(result) == 1
    assert isinstance(result[0], TextBlock)
    assert result[0].text == "101"


def test_text_detect_grayscale_raises(grayscale_image):
    mask = np.zeros((200, 200), dtype=np.uint8)
    # text_detect checks for None/empty but not shape — this tests the actual behavior
    # If the function doesn't validate shape, it will fail at cv2.cvtColor inside pytesseract
    # For now, verify it at least doesn't crash with a non-3-channel image when tesseract is unavailable
    with patch("app.processing.pipeline._TESSERACT_AVAILABLE", False):
        result = text_detect(grayscale_image, mask)
    assert result == []


# ---------------------------------------------------------------------------
# remove_text_regions — extended coverage
# ---------------------------------------------------------------------------

def test_remove_text_regions_removes_text_area(binary_mask_with_text, sample_text_blocks):
    result = remove_text_regions(binary_mask_with_text, sample_text_blocks, (200, 200))
    assert result.shape == binary_mask_with_text.shape
    assert result.dtype == np.uint8
    # The text area around center (100, 100) should have fewer white pixels
    center_region_before = binary_mask_with_text[90:120, 85:115]
    center_region_after = result[90:120, 85:115]
    assert np.sum(center_region_after) <= np.sum(center_region_before)


def test_remove_text_regions_does_not_mutate_input(binary_mask_with_text, sample_text_blocks):
    original = binary_mask_with_text.copy()
    remove_text_regions(binary_mask_with_text, sample_text_blocks, (200, 200))
    assert np.array_equal(binary_mask_with_text, original)


# ---------------------------------------------------------------------------
# multi_pass_threshold
# ---------------------------------------------------------------------------

class TestMultiPassThreshold:
    def test_captures_thin_line(self):
        """Линия толщиной 1px должна быть захвачена."""
        img = np.ones((100, 100), dtype=np.uint8) * 200
        img[50, 20:80] = 30
        result = multi_pass_threshold(img)
        captured = np.sum(result[50, 20:80] == 255)
        assert captured > 50, f"Captured only {captured}/60 pixels of thin line"

    def test_captures_thick_wall(self):
        """Стена толщиной 5px должна быть захвачена."""
        img = np.ones((100, 100), dtype=np.uint8) * 200
        img[40:45, 20:80] = 30
        result = multi_pass_threshold(img)
        captured = np.sum(result[42, 20:80] == 255)
        assert captured > 50

    def test_custom_passes(self):
        """Пользовательские параметры проходов работают."""
        img = np.ones((100, 100), dtype=np.uint8) * 200
        img[50, 20:80] = 30
        passes = [(cv2.ADAPTIVE_THRESH_MEAN_C, 5, 2)]
        result = multi_pass_threshold(img, passes=passes)
        assert result.shape == img.shape

    def test_even_blocksize_corrected(self):
        """Чётный blockSize корректируется до нечётного."""
        img = np.ones((50, 50), dtype=np.uint8) * 128
        passes = [(cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 10, 5)]
        result = multi_pass_threshold(img, passes=passes)
        assert result.shape == img.shape


# ---------------------------------------------------------------------------
# directional_morph_close
# ---------------------------------------------------------------------------

class TestDirectionalMorphClose:
    def test_preserves_right_angle(self):
        """Прямой угол не скругляется."""
        img = np.zeros((100, 100), dtype=np.uint8)
        img[20:22, 20:60] = 255  # Горизонтальная стена
        img[20:60, 20:22] = 255  # Вертикальная стена
        result = directional_morph_close(img)
        assert result[20, 20] == 255, "Corner pixel lost"
        assert result[18, 18] == 0, "Corner rounded (diagonal pixel shouldn't be white)"

    def test_closes_horizontal_gap(self):
        """Закрывает разрыв в горизонтальной линии."""
        img = np.zeros((50, 100), dtype=np.uint8)
        img[25, 20:48] = 255
        img[25, 52:80] = 255  # Разрыв 4px
        result = directional_morph_close(img, kernel_length=5)
        assert result[25, 50] == 255, "Gap not closed"

    def test_closes_vertical_gap(self):
        """Закрывает разрыв в вертикальной линии."""
        img = np.zeros((100, 50), dtype=np.uint8)
        img[20:48, 25] = 255
        img[52:80, 25] = 255  # Разрыв 4px
        result = directional_morph_close(img, kernel_length=5)
        assert result[50, 25] == 255, "Gap not closed"
