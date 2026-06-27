import logging

import cv2
import numpy as np
from typing import List

from app.core.exceptions import ImageProcessingError

logger = logging.getLogger(__name__)

MIN_CONTOUR_AREA = 50


def find_contours(
    mask: np.ndarray,
    min_area: int = MIN_CONTOUR_AREA,
) -> List[np.ndarray]:
    """
    Находит контуры стен на бинарной маске.

    Args:
        mask: Бинарная маска (H, W), dtype=uint8, значения 0/255. НЕ мутируется.
        min_area: Минимальная площадь контура в пикселях (фильтр шума).

    Returns:
        Список контуров как ndarray формата (N, 1, 2), dtype=int32.
        Координаты в пространстве пикселей (НЕ нормализованы к [0,1]).
        Нормализация — ответственность вызывающего кода при экспозиции вовне.
        Может быть пустым списком.

    Raises:
        ImageProcessingError: если mask пустая или неверного dtype.
    """
    if mask is None or mask.size == 0:
        raise ImageProcessingError("find_contours", "Empty mask")

    if mask.dtype != np.uint8:
        raise ImageProcessingError(
            "find_contours",
            f"Expected uint8, got {mask.dtype}",
        )

    contours, _ = cv2.findContours(
        mask.copy(),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    filtered: List[np.ndarray] = [
        c for c in contours if cv2.contourArea(c) > min_area
    ]

    return filtered
