"""Tests for affine transformation functions."""

import numpy as np
import pytest
from app.processing.stitching.transform import (
    build_affine_matrix,
    apply_affine_to_point,
    apply_affine_to_polygon,
)


def test_build_affine_matrix_identity_returns_identity():
    """Identity transformation (no scale, rotation, or translation)."""
    # Arrange & Act
    matrix = build_affine_matrix(1.0, 1.0, 0.0, 0.0, 0.0)

    # Assert
    expected = np.eye(3)
    np.testing.assert_array_almost_equal(matrix, expected)


def test_build_affine_matrix_translate_only_moves_point():
    """Translation only should move point by offset."""
    # Arrange
    matrix = build_affine_matrix(1.0, 1.0, 0.0, 10.0, 20.0)

    # Act
    x, y = apply_affine_to_point(matrix, 5.0, 5.0)

    # Assert
    assert x == pytest.approx(15.0)
    assert y == pytest.approx(25.0)


def test_build_affine_matrix_scale_only_multiplies_coords():
    """Scale only should multiply coordinates."""
    # Arrange
    matrix = build_affine_matrix(2.0, 3.0, 0.0, 0.0, 0.0)

    # Act
    x, y = apply_affine_to_point(matrix, 4.0, 5.0)

    # Assert
    assert x == pytest.approx(8.0)
    assert y == pytest.approx(15.0)


def test_build_affine_matrix_rotate_90_transforms_correctly():
    """90-degree counterclockwise rotation."""
    # Arrange
    matrix = build_affine_matrix(1.0, 1.0, 90.0, 0.0, 0.0)

    # Act
    x, y = apply_affine_to_point(matrix, 1.0, 0.0)

    # Assert
    # (1, 0) rotated 90° CCW becomes (0, 1)
    assert x == pytest.approx(0.0, abs=1e-10)
    assert y == pytest.approx(1.0, abs=1e-10)


def test_build_affine_matrix_combined_correct_order():
    """Combined transformation: Scale → Rotate → Translate."""
    # Arrange
    # Scale by 2, rotate 90° CCW, translate by (10, 20)
    matrix = build_affine_matrix(2.0, 2.0, 90.0, 10.0, 20.0)

    # Act
    x, y = apply_affine_to_point(matrix, 1.0, 0.0)

    # Assert
    # (1, 0) → scale → (2, 0) → rotate 90° → (0, 2) → translate → (10, 22)
    assert x == pytest.approx(10.0, abs=1e-10)
    assert y == pytest.approx(22.0, abs=1e-10)


def test_apply_affine_to_point_transforms_correctly():
    """Apply affine transformation to a single point."""
    # Arrange
    matrix = build_affine_matrix(1.0, 1.0, 0.0, 5.0, 10.0)

    # Act
    x, y = apply_affine_to_point(matrix, 3.0, 4.0)

    # Assert
    assert x == pytest.approx(8.0)
    assert y == pytest.approx(14.0)


def test_apply_affine_to_polygon_transforms_all_points():
    """Apply affine transformation to all points in a polygon."""
    # Arrange
    matrix = build_affine_matrix(1.0, 1.0, 0.0, 10.0, 20.0)
    points = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]

    # Act
    transformed = apply_affine_to_polygon(matrix, points)

    # Assert
    expected = [[10.0, 20.0], [11.0, 20.0], [11.0, 21.0], [10.0, 21.0]]
    assert len(transformed) == 4
    for actual, exp in zip(transformed, expected):
        assert actual[0] == pytest.approx(exp[0])
        assert actual[1] == pytest.approx(exp[1])


def test_apply_affine_to_polygon_empty_returns_empty():
    """Empty polygon should return empty list."""
    # Arrange
    matrix = build_affine_matrix(1.0, 1.0, 0.0, 0.0, 0.0)
    points = []

    # Act
    transformed = apply_affine_to_polygon(matrix, points)

    # Assert
    assert transformed == []
