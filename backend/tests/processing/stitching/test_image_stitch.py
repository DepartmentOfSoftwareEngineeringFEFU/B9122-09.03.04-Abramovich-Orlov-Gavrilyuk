"""Tests for raster image stitching."""

import numpy as np
import pytest

from app.processing.stitching.image_stitch import stitch_raster_images


def test_stitch_raster_images_applies_transform():
    """Test that transforms are correctly applied during stitching."""
    # Arrange
    img1 = np.ones((100, 100, 3), dtype=np.uint8) * 255  # White
    img2 = np.zeros((100, 100, 3), dtype=np.uint8)       # Black

    identity = np.eye(3, dtype=np.float64)
    translate = np.array([
        [1, 0, 100],
        [0, 1, 0],
        [0, 0, 1],
    ], dtype=np.float64)

    # Act
    result = stitch_raster_images(
        images=[img1, img2],
        transforms=[identity, translate],
        z_indices=[0, 1],
    )

    # Assert
    assert result.shape[0] >= 100  # Height
    assert result.shape[1] >= 200  # Width (100 + 100 translation)
    assert result.shape[2] == 3    # BGR
    assert result.dtype == np.uint8


def test_stitch_raster_images_respects_z_order():
    """Test that z-order determines which image appears on top."""
    # Arrange
    # Create two overlapping colored squares
    img1 = np.zeros((100, 100, 3), dtype=np.uint8)
    img1[:, :] = [255, 0, 0]  # Blue (BGR)

    img2 = np.zeros((100, 100, 3), dtype=np.uint8)
    img2[:, :] = [0, 255, 0]  # Green (BGR)

    identity = np.eye(3, dtype=np.float64)
    translate_small = np.array([
        [1, 0, 50],
        [0, 1, 50],
        [0, 0, 1],
    ], dtype=np.float64)

    # Act - img1 on bottom (z=0), img2 on top (z=1)
    result = stitch_raster_images(
        images=[img1, img2],
        transforms=[identity, translate_small],
        z_indices=[0, 1],
    )

    # Assert - Check overlap region (should be green from img2)
    # Overlap is at approximately (50, 50) to (100, 100) in result
    overlap_pixel = result[75, 75]  # Center of overlap
    assert overlap_pixel[1] > 200  # Green channel dominant
    assert overlap_pixel[0] < 50   # Blue channel minimal


def test_stitch_raster_images_correct_size():
    """Test that output canvas has correct dimensions."""
    # Arrange
    img1 = np.ones((100, 200, 3), dtype=np.uint8) * 255
    img2 = np.ones((150, 100, 3), dtype=np.uint8) * 255

    identity = np.eye(3, dtype=np.float64)
    translate = np.array([
        [1, 0, 200],
        [0, 1, 100],
        [0, 0, 1],
    ], dtype=np.float64)

    # Act
    result = stitch_raster_images(
        images=[img1, img2],
        transforms=[identity, translate],
        z_indices=[0, 1],
    )

    # Assert
    # img1: (0,0) to (200, 100)
    # img2: (200, 100) to (300, 250)
    # Expected canvas: width=300, height=250
    assert result.shape[1] == 300  # Width
    assert result.shape[0] == 250  # Height
    assert result.shape[2] == 3    # BGR


def test_stitch_raster_images_empty_list_raises():
    """Test that empty input raises ValueError."""
    with pytest.raises(ValueError, match="Cannot stitch empty list"):
        stitch_raster_images(images=[], transforms=[], z_indices=[])


def test_stitch_raster_images_mismatched_lengths_raises():
    """Test that mismatched input lengths raise ValueError."""
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    transform = np.eye(3, dtype=np.float64)

    with pytest.raises(ValueError, match="Input lists must have same length"):
        stitch_raster_images(
            images=[img, img],
            transforms=[transform],  # Only one transform
            z_indices=[0, 1],
        )


def test_stitch_raster_images_handles_negative_translation():
    """Test that negative translations are handled correctly."""
    # Arrange
    img1 = np.ones((100, 100, 3), dtype=np.uint8) * 255
    img2 = np.zeros((100, 100, 3), dtype=np.uint8)

    identity = np.eye(3, dtype=np.float64)
    translate_negative = np.array([
        [1, 0, -50],
        [0, 1, -50],
        [0, 0, 1],
    ], dtype=np.float64)

    # Act
    result = stitch_raster_images(
        images=[img1, img2],
        transforms=[identity, translate_negative],
        z_indices=[0, 1],
    )

    # Assert
    # Canvas should include negative offset
    assert result.shape[1] >= 100  # Width includes negative offset
    assert result.shape[0] >= 100  # Height includes negative offset
    assert result.shape[2] == 3
