"""Affine transformation functions for coordinate transformation."""

import numpy as np
from typing import Tuple, List


def build_affine_matrix(
    scale_x: float,
    scale_y: float,
    rotation_deg: float,
    translate_x: float,
    translate_y: float,
) -> np.ndarray:
    """
    Build 3x3 affine transformation matrix.

    Order: Scale → Rotate → Translate

    Args:
        scale_x: Horizontal scale factor
        scale_y: Vertical scale factor
        rotation_deg: Rotation angle in degrees (counterclockwise)
        translate_x: Horizontal translation
        translate_y: Vertical translation

    Returns:
        3x3 numpy array (float64)
    """
    # Convert degrees to radians
    rotation_rad = np.deg2rad(rotation_deg)
    cos_theta = np.cos(rotation_rad)
    sin_theta = np.sin(rotation_rad)

    # Scale matrix
    S = np.array([
        [scale_x, 0, 0],
        [0, scale_y, 0],
        [0, 0, 1],
    ], dtype=np.float64)

    # Rotation matrix (counterclockwise)
    R = np.array([
        [cos_theta, -sin_theta, 0],
        [sin_theta, cos_theta, 0],
        [0, 0, 1],
    ], dtype=np.float64)

    # Translation matrix
    T = np.array([
        [1, 0, translate_x],
        [0, 1, translate_y],
        [0, 0, 1],
    ], dtype=np.float64)

    # Combine: T @ R @ S (order matters!)
    return T @ R @ S


def apply_affine_to_point(
    matrix: np.ndarray,
    x: float,
    y: float,
) -> Tuple[float, float]:
    """
    Apply affine matrix to a single point.

    Args:
        matrix: 3x3 affine matrix
        x: X coordinate
        y: Y coordinate

    Returns:
        Tuple of (x_transformed, y_transformed)
    """
    # Create homogeneous point [x, y, 1]
    point = np.array([x, y, 1.0], dtype=np.float64)

    # Multiply: result = matrix @ point
    result = matrix @ point

    # Return (x, y) without homogeneous coordinate
    return (float(result[0]), float(result[1]))


def apply_affine_to_polygon(
    matrix: np.ndarray,
    points: List[List[float]],
) -> List[List[float]]:
    """
    Apply affine matrix to all points in a polygon.

    Args:
        matrix: 3x3 affine matrix
        points: List of [x, y] coordinates

    Returns:
        List of transformed [x, y] coordinates
    """
    transformed = []
    for point in points:
        x, y = apply_affine_to_point(matrix, point[0], point[1])
        transformed.append([x, y])
    return transformed
