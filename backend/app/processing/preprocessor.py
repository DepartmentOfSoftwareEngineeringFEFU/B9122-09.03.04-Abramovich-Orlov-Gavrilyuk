import logging

import cv2
import numpy as np

from app.core.exceptions import ImageProcessingError

logger = logging.getLogger(__name__)


def preprocess_image(
    image: np.ndarray,
    crop: dict | None = None,
    rotation: int = 0,
) -> np.ndarray:
    """
    Preprocessing: rotate → crop → grayscale → GaussianBlur → Otsu → morphology → noise removal.

    Args:
        image: BGR изображение (H, W, 3), dtype=uint8. НЕ мутируется.
        crop: dict с ключами x, y, width, height (0-1 нормализованные). None = не кропать.
        rotation: поворот в градусах (0, 90, 180, 270).

    Returns:
        Бинарная маска (H, W), dtype=uint8, значения 0 или 255. Стены = 255, фон = 0.

    Raises:
        ImageProcessingError: если входное изображение пустое или имеет неверный формат.
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("preprocess_image", "Empty image")

    # Never mutate input
    img = image.copy()

    # 1. Rotate if provided
    if rotation:
        r = rotation % 360
        if r == 90:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            logger.debug("Rotated 90 degrees clockwise")
        elif r == 180:
            img = cv2.rotate(img, cv2.ROTATE_180)
            logger.debug("Rotated 180 degrees")
        elif r == 270:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            logger.debug("Rotated 90 degrees counter-clockwise")

    # 2. Apply crop if provided
    if crop:
        h, w = img.shape[:2]
        x = int(crop["x"] * w)
        y = int(crop["y"] * h)
        crop_w = int(crop["width"] * w)
        crop_h = int(crop["height"] * h)

        # Ensure bounds
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        crop_w = max(1, min(crop_w, w - x))
        crop_h = max(1, min(crop_h, h - y))

        img = img[y : y + crop_h, x : x + crop_w]
        logger.debug("Applied crop: x=%d, y=%d, w=%d, h=%d", x, y, crop_w, crop_h)

    # 3. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 4. GaussianBlur for noise reduction
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # 5. Binarization (Otsu) — inverted: dark lines (walls) → white (255)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 6. Morphology — close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 7. Noise removal via connected components (preserves holes inside frames)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(morph, connectivity=8)

    mask = np.zeros_like(morph)
    for i in range(1, num_labels):  # label 0 is background
        area = stats[i, cv2.CC_STAT_AREA]
        if area > 50:
            mask[labels == i] = 255

    logger.debug(
        "preprocess_image done: input shape=%s, output shape=%s, labels=%d",
        image.shape,
        mask.shape,
        num_labels,
    )
    return mask
