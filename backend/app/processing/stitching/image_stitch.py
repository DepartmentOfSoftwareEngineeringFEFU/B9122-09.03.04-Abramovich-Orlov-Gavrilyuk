"""Raster image stitching using OpenCV warpAffine."""

import cv2
import numpy as np
from typing import List, Tuple


def stitch_raster_images(
    images: List[np.ndarray],
    transforms: List[np.ndarray],
    z_indices: List[int],
) -> np.ndarray:
    """
    Stitch multiple raster images using affine transforms.

    Args:
        images: List of BGR images (H, W, 3), dtype=uint8
        transforms: List of 3x3 affine matrices (one per image)
        z_indices: List of z-order indices (0 = bottom)

    Returns:
        Composite BGR image (H, W, 3), dtype=uint8

    Raises:
        ValueError: If lists have different lengths or if inputs are empty
    """
    if len(images) != len(transforms) or len(images) != len(z_indices):
        raise ValueError(
            f"Input lists must have same length: "
            f"images={len(images)}, transforms={len(transforms)}, z_indices={len(z_indices)}"
        )

    if len(images) == 0:
        raise ValueError("Cannot stitch empty list of images")

    # Sort by z_index (bottom to top)
    sorted_data = sorted(
        zip(images, transforms, z_indices),
        key=lambda x: x[2]  # Sort by z_index
    )
    sorted_images, sorted_transforms, _ = zip(*sorted_data)

    # Compute bounding box of all transformed corners
    min_x, min_y, max_x, max_y = _compute_bounding_box(
        sorted_images, sorted_transforms
    )

    # Create canvas (white background)
    canvas_width = int(np.ceil(max_x - min_x))
    canvas_height = int(np.ceil(max_y - min_y))
    canvas = np.ones((canvas_height, canvas_width, 3), dtype=np.uint8) * 255

    # Adjust transforms to account for negative offsets
    offset_transform = np.array([
        [1, 0, -min_x],
        [0, 1, -min_y],
        [0, 0, 1],
    ], dtype=np.float64)

    # For each image: apply warpAffine and composite onto canvas
    for img, transform in zip(sorted_images, sorted_transforms):
        # Combine offset with original transform
        adjusted_transform = offset_transform @ transform

        # Extract 2x3 affine matrix for cv2.warpAffine
        affine_2x3 = adjusted_transform[:2, :]

        # Warp image
        warped = cv2.warpAffine(
            img,
            affine_2x3,
            (canvas_width, canvas_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255)  # White border
        )

        # Composite onto canvas (overwrite non-white pixels)
        mask = np.any(warped != 255, axis=2)
        canvas[mask] = warped[mask]

    return canvas


def _compute_bounding_box(
    images: Tuple[np.ndarray, ...],
    transforms: Tuple[np.ndarray, ...],
) -> Tuple[float, float, float, float]:
    """
    Compute bounding box of all transformed image corners.

    Args:
        images: Tuple of BGR images (H, W, 3)
        transforms: Tuple of 3x3 affine matrices

    Returns:
        (min_x, min_y, max_x, max_y) bounding box coordinates
    """
    all_corners = []

    for img, transform in zip(images, transforms):
        h, w = img.shape[:2]

        # Image corners in homogeneous coordinates
        corners = np.array([
            [0, 0, 1],
            [w, 0, 1],
            [w, h, 1],
            [0, h, 1],
        ], dtype=np.float64).T  # Shape: (3, 4)

        # Transform corners
        transformed = transform @ corners  # Shape: (3, 4)

        # Convert from homogeneous to Cartesian
        transformed_xy = transformed[:2, :] / transformed[2, :]

        all_corners.append(transformed_xy.T)  # Shape: (4, 2)

    # Stack all corners and compute bounds
    all_corners_array = np.vstack(all_corners)  # Shape: (N*4, 2)

    min_x = float(np.min(all_corners_array[:, 0]))
    min_y = float(np.min(all_corners_array[:, 1]))
    max_x = float(np.max(all_corners_array[:, 0]))
    max_y = float(np.max(all_corners_array[:, 1]))

    return min_x, min_y, max_x, max_y
