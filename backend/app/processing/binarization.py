"""
Pure functions for image binarization.

Uses Otsu's method for automatic threshold detection.
All functions are PURE — no DB, no HTTP, no file I/O, no state.
"""

import logging
from typing import Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """
    Convert BGR image to grayscale.

    Args:
        image: BGR image (H, W, 3), dtype=uint8. NOT mutated.

    Returns:
        Grayscale image (H, W), dtype=uint8.
    """
    if image.ndim == 3 and image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image.copy()


def binarize_otsu(gray_image: np.ndarray) -> Tuple[np.ndarray, int]:
    """
    Binarize grayscale image using Otsu's method.

    Automatically determines optimal threshold by maximizing inter-class variance.
    Applies Gaussian blur before thresholding to reduce noise.

    Args:
        gray_image: Grayscale image (H, W), dtype=uint8. NOT mutated.

    Returns:
        Tuple of:
            - binary_image: Binary mask (H, W), dtype=uint8, values 0 or 255
            - threshold: Computed threshold value (0-255)
    """
    blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
    threshold, binary = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return binary, int(threshold)


def apply_adaptive_threshold(
    gray_image: np.ndarray,
    block_size: int = 11,
    c: int = 2
) -> np.ndarray:
    """
    Adaptive binarization for images with uneven lighting.

    Uses local neighborhood statistics to compute threshold per pixel.
    Useful for plans with shadows or varying illumination.

    Args:
        gray_image: Grayscale image (H, W), dtype=uint8. NOT mutated.
        block_size: Size of local neighborhood (must be odd, >= 3).
        c: Constant subtracted from weighted mean.

    Returns:
        Binary mask (H, W), dtype=uint8, values 0 or 255.
    """
    return cv2.adaptiveThreshold(
        gray_image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c
    )


def apply_morphology(
    binary_image: np.ndarray,
    kernel_size: int = 3,
    iterations: int = 1
) -> np.ndarray:
    """
    Morphological operations to clean binary mask.

    Applies closing (fills small gaps in walls) followed by opening (removes noise).

    Args:
        binary_image: Binary mask (H, W), dtype=uint8. NOT mutated.
        kernel_size: Morphological kernel size (pixels).
        iterations: Number of iterations for each operation.

    Returns:
        Cleaned binary mask (H, W), dtype=uint8, values 0 or 255.
    """
    img = binary_image.copy()
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (kernel_size, kernel_size)
    )

    # Closing: fill small holes and gaps in walls
    closed = cv2.morphologyEx(
        img,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=iterations
    )

    # Opening: remove small noise
    opened = cv2.morphologyEx(
        closed,
        cv2.MORPH_OPEN,
        kernel,
        iterations=iterations
    )

    return opened


def invert_if_needed(binary_image: np.ndarray) -> np.ndarray:
    """
    Invert binary mask if walls are black (should be white).

    Assumes walls occupy less area than free space.
    If white pixels > 50%, inverts the mask.

    Args:
        binary_image: Binary mask (H, W), dtype=uint8. NOT mutated.

    Returns:
        Binary mask with walls=255, background=0.
    """
    white_pixels = np.sum(binary_image == 255)
    black_pixels = np.sum(binary_image == 0)

    if white_pixels > black_pixels:
        return cv2.bitwise_not(binary_image)

    return binary_image.copy()


def binarize_image(
    image: np.ndarray,
    use_adaptive: bool = False,
    morphology_kernel: int = 3,
    morphology_iterations: int = 2
) -> Tuple[np.ndarray, int]:
    """
    Complete binarization pipeline.

    Steps:
    1. Convert to grayscale
    2. Apply Otsu or adaptive threshold
    3. Morphological cleaning
    4. Invert if needed (walls should be white)

    Args:
        image: BGR image (H, W, 3), dtype=uint8. NOT mutated.
        use_adaptive: Use adaptive threshold instead of Otsu.
        morphology_kernel: Kernel size for morphology (pixels).
        morphology_iterations: Number of morphology iterations.

    Returns:
        Tuple of:
            - mask: Binary mask (H, W), dtype=uint8, walls=255, background=0
            - threshold: Threshold value (0 if adaptive)
    """
    # Step 1: Grayscale
    gray = to_grayscale(image)

    # Step 2: Binarization
    if use_adaptive:
        binary = apply_adaptive_threshold(gray)
        threshold = 0
    else:
        binary, threshold = binarize_otsu(gray)

    logger.debug("Binarization threshold: %d", threshold)

    # Step 3: Morphological cleaning
    cleaned = apply_morphology(
        binary,
        kernel_size=morphology_kernel,
        iterations=morphology_iterations
    )

    # Step 4: Invert if needed
    mask = invert_if_needed(cleaned)

    return mask, threshold
