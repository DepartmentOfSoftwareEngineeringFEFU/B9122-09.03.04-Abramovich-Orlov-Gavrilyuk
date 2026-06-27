import numpy as np
import pytest
from app.processing.preprocessor import preprocess_image
from app.core.exceptions import ImageProcessingError


def test_preprocess_valid_bgr_returns_binary_uint8(simple_room_image):
    result = preprocess_image(simple_room_image)
    assert result.dtype == np.uint8, "Result must be uint8"
    assert set(np.unique(result)).issubset({0, 255}), "Only 0 and 255 values expected"
    assert result.ndim == 2, "Result must be grayscale (2D)"


def test_preprocess_does_not_mutate_input(simple_room_image):
    original = simple_room_image.copy()
    preprocess_image(simple_room_image)
    assert np.array_equal(simple_room_image, original), "Input array must not be mutated"


def test_preprocess_empty_image_raises_error():
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    with pytest.raises(ImageProcessingError):
        preprocess_image(empty)


def test_preprocess_with_crop_returns_smaller_shape(simple_room_image):
    crop = {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5}
    result = preprocess_image(simple_room_image, crop=crop)
    assert result.shape[0] <= 100, "Height after crop must be <= 100px"
    assert result.shape[1] <= 100, "Width after crop must be <= 100px"
