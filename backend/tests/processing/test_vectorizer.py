from app.processing.vectorizer import find_contours
from app.core.exceptions import ImageProcessingError


def test_find_contours_rectangle_returns_contour(binary_rectangle_mask):
    result = find_contours(binary_rectangle_mask)
    assert len(result) >= 1, "Vectorizer must find at least one contour for a rectangle"


def test_find_contours_empty_mask_returns_empty_list(empty_mask):
    result = find_contours(empty_mask)
    assert result == [], "Empty mask should return no contours"
