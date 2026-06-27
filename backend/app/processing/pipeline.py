"""
Vectorization pipeline — pure functions for 8-step image processing.

Steps 1-3: Brightness normalization, color filtering, auto-crop suggestion.
Steps 4-6: Text detection, text removal.
Steps 7-8: Room detection, classification, door detection, normalization.

All functions are PURE — no DB, no HTTP, no side effects.
"""
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.core.exceptions import ImageProcessingError
from app.models.domain import Door, Point2D, Room, TextBlock, Wall

logger = logging.getLogger(__name__)

# Room number regex patterns (GOST standard)
ROOM_NUMBER_PATTERNS = [
    re.compile(r"^\d{3,4}[А-Яа-яA-Za-z]?$"),   # 1103, 1103А
    re.compile(r"^[A-ZА-Я]\d{3,4}$"),            # A304, Б201
]


def _is_room_number(text: str) -> bool:
    """Check if text matches a room number pattern."""
    return any(p.match(text.strip()) for p in ROOM_NUMBER_PATTERNS)


# Step 1: Brightness Normalization

def normalize_brightness(
    image: np.ndarray,
    clip_limit: float = 2.0,
    tile_size: int = 8,
) -> np.ndarray:
    """
    Normalize brightness using CLAHE on L channel.

    Args:
        image: BGR image (H, W, 3), dtype=uint8
        clip_limit: CLAHE clip limit
        tile_size: CLAHE tile grid size

    Returns:
        Normalized BGR image (H, W, 3), dtype=uint8
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("normalize_brightness", "Empty image")
    if image.dtype != np.uint8:
        raise ImageProcessingError(
            "normalize_brightness", f"Expected uint8, got {image.dtype}"
        )

    start = time.perf_counter()

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)

    clahe = cv2.createCLAHE(
        clipLimit=clip_limit, tileGridSize=(tile_size, tile_size)
    )
    l_clahe = clahe.apply(l_ch)

    lab_clahe = cv2.merge([l_clahe, a_ch, b_ch])
    normalized = cv2.cvtColor(lab_clahe, cv2.COLOR_LAB2BGR)

    elapsed = time.perf_counter() - start
    logger.info("normalize_brightness completed in %.3fs", elapsed)
    return normalized


# Step 1b: Multi-pass Adaptive Threshold

def multi_pass_threshold(
    gray: np.ndarray,
    passes: list[tuple[int, int, int]] | None = None,
) -> np.ndarray:
    """
    Несколько проходов adaptive threshold с разными параметрами,
    объединённых через bitwise_OR.

    Проход 1 — пользовательские параметры (толстые стены).
    Проход 2 — мелкое окно (тонкие линии, перегородки).
    Проход 3 — среднее окно (промежуточные элементы).

    Args:
        gray: grayscale (uint8)
        passes: list of (adaptiveMethod, blockSize, C).
                blockSize будет скорректирован до нечётного >= 3.
                Если None — default 3 прохода.
    Returns:
        Бинарная маска (uint8, 0 или 255)
    """
    t0 = time.perf_counter()

    if passes is None:
        passes = [
            (cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 15, 10),
            (cv2.ADAPTIVE_THRESH_MEAN_C, 7, 3),
            (cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 11, 5),
        ]

    result = np.zeros_like(gray)

    for method, block_size, c in passes:
        bs = max(3, block_size if block_size % 2 == 1 else block_size + 1)
        mask = cv2.adaptiveThreshold(
            gray, 255, method, cv2.THRESH_BINARY_INV, bs, c
        )
        result = cv2.bitwise_or(result, mask)

    logger.info("multi_pass_threshold: %d passes, %.1fms",
                len(passes), (time.perf_counter() - t0) * 1000)
    return result


# Step 1c: Directional Morphological Close

def directional_morph_close(
    binary: np.ndarray,
    kernel_length: int = 3,
    iterations: int = 1,
) -> np.ndarray:
    """
    MORPH_CLOSE с линейными ядрами (H + V) вместо квадратного.
    Закрывает разрывы в линиях вдоль горизонтали и вертикали,
    не скругляя прямые углы стен.

    Args:
        binary: бинарная маска (uint8, 0/255)
        kernel_length: длина линейного ядра (default 3)
        iterations: количество итераций (default 1)
    Returns:
        Обработанная маска (uint8, 0/255)
    """
    t0 = time.perf_counter()

    kernel_h = np.ones((1, kernel_length), np.uint8)
    kernel_v = np.ones((kernel_length, 1), np.uint8)

    closed_h = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_h, iterations=iterations)
    closed_v = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_v, iterations=iterations)

    result = cv2.bitwise_or(closed_h, closed_v)

    logger.info("directional_morph_close: kernel=%d, %.1fms",
                kernel_length, (time.perf_counter() - t0) * 1000)
    return result


# Step 2: Color Filtering

def color_filter(
    image: np.ndarray,
    saturation_threshold: int = 50,
    inpaint_radius: int = 3,
) -> np.ndarray:
    """
    Remove colored elements (green arrows, red symbols) via HSV saturation mask + inpaint.

    Args:
        image: BGR image (H, W, 3), dtype=uint8
        saturation_threshold: pixels with S > threshold are colored
        inpaint_radius: inpainting radius (pixels)

    Returns:
        Filtered BGR image (H, W, 3), dtype=uint8
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("color_filter", "Empty image")
    if image.dtype != np.uint8:
        raise ImageProcessingError(
            "color_filter", f"Expected uint8, got {image.dtype}"
        )

    start = time.perf_counter()

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    _, s_ch, _ = cv2.split(hsv)

    mask = (s_ch > saturation_threshold).astype(np.uint8) * 255
    filtered = cv2.inpaint(image, mask, inpaint_radius, cv2.INPAINT_TELEA)

    elapsed = time.perf_counter() - start
    logger.info("color_filter completed in %.3fs", elapsed)
    return filtered


# Step 2b: Targeted Color Removal (green arrows, red symbols)

def remove_green_elements(
    image: np.ndarray,
    hue_low: int = 35,
    hue_high: int = 85,
    sat_min: int = 40,
    val_min: int = 40,
    inpaint_radius: int = 3,
) -> np.ndarray:
    """
    Remove green elements (evacuation arrows) via HSV filtering + inpaint.

    Args:
        image: BGR image (H, W, 3), dtype=uint8
        hue_low: lower bound of green hue (OpenCV 0-180)
        hue_high: upper bound of green hue
        sat_min: minimum saturation
        val_min: minimum value
        inpaint_radius: inpainting radius (pixels)

    Returns:
        BGR image (H, W, 3), dtype=uint8 with green elements replaced
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("remove_green_elements", "Empty image")
    if image.dtype != np.uint8:
        raise ImageProcessingError(
            "remove_green_elements", f"Expected uint8, got {image.dtype}"
        )
    if image.ndim != 3 or image.shape[2] != 3:
        raise ImageProcessingError(
            "remove_green_elements",
            f"Expected BGR (H,W,3), got shape {image.shape}",
        )

    start = time.perf_counter()
    result = image.copy()

    hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
    lower = np.array([hue_low, sat_min, val_min], dtype=np.uint8)
    upper = np.array([hue_high, 255, 255], dtype=np.uint8)
    green_mask = cv2.inRange(hsv, lower, upper)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    green_mask = cv2.dilate(green_mask, kernel, iterations=2)

    result = cv2.inpaint(result, green_mask, 7, cv2.INPAINT_TELEA)

    elapsed = time.perf_counter() - start
    logger.info("remove_green_elements completed in %.3fs", elapsed)
    return result


def remove_red_elements(
    image: np.ndarray,
    hue_low1: int = 0,
    hue_high1: int = 10,
    hue_low2: int = 170,
    hue_high2: int = 180,
    sat_min: int = 50,
    val_min: int = 50,
    inpaint_radius: int = 3,
) -> np.ndarray:
    """
    Remove red elements (fire extinguisher symbols) via HSV filtering + inpaint.

    Red wraps around H=0/180 in OpenCV HSV, so two ranges are needed.

    Args:
        image: BGR image (H, W, 3), dtype=uint8
        hue_low1: lower red range start
        hue_high1: lower red range end
        hue_low2: upper red range start
        hue_high2: upper red range end
        sat_min: minimum saturation
        val_min: minimum value
        inpaint_radius: inpainting radius (pixels)

    Returns:
        BGR image (H, W, 3), dtype=uint8 with red elements replaced
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("remove_red_elements", "Empty image")
    if image.dtype != np.uint8:
        raise ImageProcessingError(
            "remove_red_elements", f"Expected uint8, got {image.dtype}"
        )
    if image.ndim != 3 or image.shape[2] != 3:
        raise ImageProcessingError(
            "remove_red_elements",
            f"Expected BGR (H,W,3), got shape {image.shape}",
        )

    start = time.perf_counter()
    result = image.copy()

    hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)

    lower1 = np.array([hue_low1, sat_min, val_min], dtype=np.uint8)
    upper1 = np.array([hue_high1, 255, 255], dtype=np.uint8)
    mask1 = cv2.inRange(hsv, lower1, upper1)

    lower2 = np.array([hue_low2, sat_min, val_min], dtype=np.uint8)
    upper2 = np.array([hue_high2, 255, 255], dtype=np.uint8)
    mask2 = cv2.inRange(hsv, lower2, upper2)

    red_mask = mask1 | mask2

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    red_mask = cv2.dilate(red_mask, kernel, iterations=2)

    result = cv2.inpaint(result, red_mask, 7, cv2.INPAINT_TELEA)

    elapsed = time.perf_counter() - start
    logger.info("remove_red_elements completed in %.3fs", elapsed)
    return result


def remove_colored_elements(image: np.ndarray) -> np.ndarray:
    """
    Remove green and red colored elements from evacuation plan.

    Orchestrator: calls remove_green_elements then remove_red_elements.
    Order matters — green arrows may overlap red symbols.

    Args:
        image: BGR image (H, W, 3), dtype=uint8

    Returns:
        BGR image (H, W, 3), dtype=uint8 with colored elements removed
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("remove_colored_elements", "Empty image")
    if image.dtype != np.uint8:
        raise ImageProcessingError(
            "remove_colored_elements", f"Expected uint8, got {image.dtype}"
        )
    if image.ndim != 3 or image.shape[2] != 3:
        raise ImageProcessingError(
            "remove_colored_elements",
            f"Expected BGR (H,W,3), got shape {image.shape}",
        )

    start = time.perf_counter()

    img = remove_green_elements(image)
    img = remove_red_elements(img)

    elapsed = time.perf_counter() - start
    logger.info("remove_colored_elements completed in %.3fs", elapsed)
    return img


# Step 3: Auto-Crop Suggestion

def auto_crop_suggest(
    image: np.ndarray,
    min_area_ratio: float = 0.2,
    margin_ratio: float = 0.05,
) -> Optional[Dict[str, float]]:
    """
    Suggest crop rectangle around building boundary.

    Args:
        image: BGR image (H, W, 3), dtype=uint8
        min_area_ratio: minimum contour area as ratio of image area
        margin_ratio: margin to add around bounding box

    Returns:
        Crop rect {x, y, width, height} normalized [0,1], or None
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("auto_crop_suggest", "Empty image")

    start = time.perf_counter()

    h, w = image.shape[:2]
    image_area = h * w

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    large_contours = [c for c in contours if cv2.contourArea(c) > image_area * min_area_ratio]

    if not large_contours:
        logger.info("auto_crop_suggest: no large contour found")
        return None

    largest = max(large_contours, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(largest)

    margin_x = int(bw * margin_ratio)
    margin_y = int(bh * margin_ratio)
    x = max(0, x - margin_x)
    y = max(0, y - margin_y)
    bw = min(w - x, bw + 2 * margin_x)
    bh = min(h - y, bh + 2 * margin_y)

    crop_rect = {
        "x": x / w,
        "y": y / h,
        "width": bw / w,
        "height": bh / h,
    }

    elapsed = time.perf_counter() - start
    logger.info("auto_crop_suggest completed in %.3fs, crop=%s", elapsed, crop_rect)
    return crop_rect


# Step 5: Text Detection (pytesseract — optional)

try:
    import pytesseract
    _TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    _TESSERACT_AVAILABLE = False


def text_detect(
    image: np.ndarray,
    binary_mask: np.ndarray,
    confidence_threshold: int = 60,
) -> List[TextBlock]:
    """
    Detect text via OCR, mark room numbers.

    Args:
        image: BGR image (H, W, 3), dtype=uint8 (original, before binarization)
        binary_mask: binary mask (H, W), dtype=uint8
        confidence_threshold: minimum OCR confidence (0-100)

    Returns:
        List of TextBlock with coordinates and room number flag.
        Empty list if pytesseract is not installed.
    """
    if image is None or image.size == 0:
        raise ImageProcessingError("text_detect", "Empty image")

    if not _TESSERACT_AVAILABLE:
        logger.warning("pytesseract not available, skipping text detection")
        return []

    start = time.perf_counter()
    h, w = image.shape[:2]
    text_blocks: List[TextBlock] = []

    try:
        data = pytesseract.image_to_data(
            image, lang="rus+eng", config="--psm 6", output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        logger.warning("OCR failed: %s", e)
        return []

    n_boxes = len(data["text"])
    for i in range(n_boxes):
        text = data["text"][i].strip()
        if not text:
            continue

        conf = int(data["conf"][i])
        if conf < confidence_threshold:
            continue

        bx = int(data["left"][i])
        by = int(data["top"][i])
        bw = int(data["width"][i])
        bh = int(data["height"][i])

        cx = (bx + bw / 2) / w
        cy = (by + bh / 2) / h
        cx = max(0.0, min(1.0, cx))
        cy = max(0.0, min(1.0, cy))

        text_blocks.append(TextBlock(
            text=text,
            center=Point2D(x=cx, y=cy),
            confidence=float(conf),
            is_room_number=_is_room_number(text),
        ))

    elapsed = time.perf_counter() - start
    logger.info(
        "text_detect completed in %.3fs, found %d blocks (%d room numbers)",
        elapsed,
        len(text_blocks),
        sum(1 for tb in text_blocks if tb.is_room_number),
    )
    return text_blocks


# Step 6: Text Removal (inpaint)

def remove_text_regions(
    binary_mask: np.ndarray,
    text_blocks: List[TextBlock],
    image_size: Tuple[int, int],
    inpaint_radius: int = 5,
    text_height_px: int = 20,
    char_width_px: int = 10,
) -> np.ndarray:
    """
    Remove text regions from binary mask via inpainting.

    Args:
        binary_mask: binary mask (H, W), dtype=uint8
        text_blocks: detected text blocks
        image_size: (width, height) of the image used for denormalization
        inpaint_radius: inpainting radius
        text_height_px: estimated text height in pixels
        char_width_px: estimated character width in pixels

    Returns:
        Cleaned binary mask (H, W), dtype=uint8
    """
    if binary_mask is None or binary_mask.size == 0:
        raise ImageProcessingError("remove_text_regions", "Empty mask")

    if not text_blocks:
        return binary_mask

    start = time.perf_counter()
    w, h = image_size
    removal_mask = np.zeros((binary_mask.shape[0], binary_mask.shape[1]), dtype=np.uint8)

    for tb in text_blocks:
        cx_px = int(tb.center.x * w)
        cy_px = int(tb.center.y * h)
        text_w = max(len(tb.text) * char_width_px, char_width_px)
        text_h = text_height_px

        x1 = max(0, cx_px - text_w // 2)
        y1 = max(0, cy_px - text_h // 2)
        x2 = min(w, cx_px + text_w // 2)
        y2 = min(h, cy_px + text_h // 2)

        cv2.rectangle(removal_mask, (x1, y1), (x2, y2), 255, -1)

    cleaned = cv2.inpaint(binary_mask, removal_mask, inpaint_radius, cv2.INPAINT_TELEA)

    elapsed = time.perf_counter() - start
    logger.info(
        "remove_text_regions completed in %.3fs, removed %d blocks",
        elapsed, len(text_blocks)
    )
    return cleaned


# Step 7a: Compute Wall Thickness

def compute_wall_thickness(binary_mask: np.ndarray) -> float:
    """
    Compute median wall thickness via distance transform.

    Args:
        binary_mask: binary mask (H, W), dtype=uint8, walls=255

    Returns:
        Median wall thickness in pixels. 0.0 if no walls.
    """
    if binary_mask is None or binary_mask.size == 0:
        raise ImageProcessingError("compute_wall_thickness", "Empty mask")

    dist = cv2.distanceTransform(binary_mask, cv2.DIST_L2, 5)
    nonzero = dist[dist > 0]
    if nonzero.size == 0:
        logger.warning("compute_wall_thickness: no wall pixels found")
        return 0.0

    thickness = float(np.median(nonzero))
    logger.info("compute_wall_thickness: %.1f px", thickness)
    return thickness


# Step 7c: Room Detection (invert mask + connected components)

def room_detect(
    binary_mask: np.ndarray,
    min_room_area: int = 1000,
    max_room_area_ratio: float = 0.8,
) -> List[Room]:
    """
    Detect rooms by inverting mask and finding connected components.

    Args:
        binary_mask: binary mask (H, W), dtype=uint8, walls=255, background=0
        min_room_area: minimum room area in pixels
        max_room_area_ratio: maximum room area as ratio of image area

    Returns:
        List of Room with polygons normalized to [0, 1].
    """
    if binary_mask is None or binary_mask.size == 0:
        raise ImageProcessingError("room_detect", "Empty mask")

    start = time.perf_counter()
    h, w = binary_mask.shape[:2]
    image_area = h * w
    max_area = int(image_area * max_room_area_ratio)

    inverted = cv2.bitwise_not(binary_mask)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        inverted, connectivity=8
    )

    rooms: List[Room] = []
    for label_idx in range(1, num_labels):  # skip 0 = background
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if area < min_room_area or area > max_area:
            continue

        component_mask = (labels == label_idx).astype(np.uint8) * 255
        contours, _ = cv2.findContours(
            component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            continue

        contour = max(contours, key=cv2.contourArea)
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        polygon = [
            Point2D(x=float(pt[0][0]) / w, y=float(pt[0][1]) / h)
            for pt in approx
        ]
        if len(polygon) < 3:
            continue

        cx = float(centroids[label_idx][0]) / w
        cy = float(centroids[label_idx][1]) / h
        area_norm = area / image_area

        rooms.append(Room(
            id=f"room_{label_idx}",
            name="",
            polygon=polygon,
            center=Point2D(x=min(1.0, max(0.0, cx)), y=min(1.0, max(0.0, cy))),
            room_type="unknown",
            area_normalized=area_norm,
        ))

    elapsed = time.perf_counter() - start
    logger.info("room_detect completed in %.3fs, found %d rooms", elapsed, len(rooms))
    return rooms


# Step 7d: Classify Rooms

def classify_rooms(
    rooms: List[Room],
    corridor_aspect_ratio: float = 3.0,
) -> List[Room]:
    """
    Classify rooms as 'room' or 'corridor' by bounding box aspect ratio.

    Args:
        rooms: list of Room (polygon must be populated)
        corridor_aspect_ratio: threshold — if aspect > this, it's a corridor

    Returns:
        New list of Room objects with room_type updated.
    """
    start = time.perf_counter()
    result: List[Room] = []
    for room in rooms:
        if len(room.polygon) < 3:
            result.append(room.model_copy(update={"room_type": "room"}))
            continue

        xs = [p.x for p in room.polygon]
        ys = [p.y for p in room.polygon]
        bbox_w = max(xs) - min(xs)
        bbox_h = max(ys) - min(ys)

        if bbox_w == 0 or bbox_h == 0:
            result.append(room.model_copy(update={"room_type": "room"}))
            continue

        aspect = max(bbox_w, bbox_h) / min(bbox_w, bbox_h)
        room_type = "corridor" if aspect > corridor_aspect_ratio else "room"
        result.append(room.model_copy(update={"room_type": room_type}))

    elapsed = time.perf_counter() - start
    logger.info("classify_rooms completed in %.3fs", elapsed)
    return result


# Step 7e: Door Detection

def door_detect(
    binary_mask: np.ndarray,
    rooms: List[Room],
    dilate_kernel: int = 5,
    dilate_iterations: int = 1,
    adjacency_threshold: float = 0.05,
) -> List[Door]:
    """
    Detect doors by dilating walls and finding gaps that close.

    Args:
        binary_mask: binary mask (H, W), dtype=uint8, walls=255
        rooms: detected rooms
        dilate_kernel: dilation kernel size
        dilate_iterations: dilation iterations
        adjacency_threshold: distance threshold for room adjacency (normalized)

    Returns:
        List of Door.
    """
    if binary_mask is None or binary_mask.size == 0:
        raise ImageProcessingError("door_detect", "Empty mask")

    start = time.perf_counter()
    h, w = binary_mask.shape[:2]

    kernel = np.ones((dilate_kernel, dilate_kernel), np.uint8)
    dilated = cv2.dilate(binary_mask, kernel, iterations=dilate_iterations)

    # Gaps = pixels that were 0 in original but became 255 after dilation
    gaps = cv2.bitwise_and(dilated, cv2.bitwise_not(binary_mask))

    contours, _ = cv2.findContours(gaps, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    doors: List[Door] = []
    door_idx = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 10:  # noise filter
            continue

        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue
        cx = float(M["m10"] / M["m00"]) / w
        cy = float(M["m01"] / M["m00"]) / h

        # Find adjacent rooms
        connected_rooms: List[str] = []
        for room in rooms:
            dist = ((room.center.x - cx) ** 2 + (room.center.y - cy) ** 2) ** 0.5
            if dist < adjacency_threshold * 5:  # rough proximity check
                # More precise: check if door is near room polygon
                min_dist = min(
                    ((p.x - cx) ** 2 + (p.y - cy) ** 2) ** 0.5
                    for p in room.polygon
                )
                if min_dist < adjacency_threshold:
                    connected_rooms.append(room.id)

        if len(connected_rooms) >= 2:
            _, _, bw, bh = cv2.boundingRect(contour)
            door_width = max(bw / w, bh / h)

            doors.append(Door(
                id=f"door_{door_idx}",
                position=Point2D(x=min(1.0, max(0.0, cx)), y=min(1.0, max(0.0, cy))),
                width=door_width,
                connects=connected_rooms[:2],
            ))
            door_idx += 1

    elapsed = time.perf_counter() - start
    logger.info("door_detect completed in %.3fs, found %d doors", elapsed, len(doors))
    return doors


# Step 7f: Assign Room Numbers

def assign_room_numbers(
    rooms: List[Room],
    text_blocks: List[TextBlock],
) -> List[Room]:
    """
    Assign room names from text blocks that are room numbers.

    Uses point-in-polygon test (ray casting) to match text to rooms.

    Args:
        rooms: detected rooms with polygons
        text_blocks: detected text blocks

    Returns:
        New list of Room objects with names assigned where text center falls inside polygon.
    """
    start = time.perf_counter()
    room_numbers = [tb for tb in text_blocks if tb.is_room_number]

    # Build a mutable dict so we can assign names without mutating originals
    names: dict = {room.id: room.name for room in rooms}

    for tb in room_numbers:
        for room in rooms:
            if names[room.id]:  # already assigned
                continue
            if _point_in_polygon(tb.center, room.polygon):
                names[room.id] = tb.text
                break

    result = [
        room.model_copy(update={"name": names[room.id]}) for room in rooms
    ]

    elapsed = time.perf_counter() - start
    logger.info("assign_room_numbers completed in %.3fs", elapsed)
    return result


def _point_in_polygon(point: Point2D, polygon: List[Point2D]) -> bool:
    """Ray casting algorithm for point-in-polygon test."""
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    px, py = point.x, point.y
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y

        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


# Step 8: Scale Computation

def compute_scale_factor(wall_thickness_px: float) -> float:
    """
    Estimate pixels per meter from wall thickness.

    Standard interior wall ~ 0.2m (GOST 21.501-2018).

    Args:
        wall_thickness_px: median wall thickness in pixels

    Returns:
        Estimated pixels per meter.
    """
    if wall_thickness_px <= 0:
        return 50.0
    return wall_thickness_px / 0.2


# Step 8: Coordinate Normalization

def normalize_coords(
    walls: List[Wall],
    rooms: List[Room],
    doors: List[Door],
    image_size: Tuple[int, int],
) -> Tuple[List[Wall], List[Room], List[Door]]:
    """
    Normalize all pixel coordinates to [0, 1] relative to image_size.

    Note: room_detect() already produces normalized coords, so this function
    is a safety pass that clamps values to [0, 1].

    Args:
        walls: walls (may have pixel coords from ContourService)
        rooms: rooms (already normalized from room_detect)
        doors: doors (already normalized from door_detect)
        image_size: (width, height)

    Returns:
        Tuple of (walls, rooms, doors) with all coords in [0, 1].
    """
    w, h = image_size
    if w <= 0 or h <= 0:
        raise ImageProcessingError("normalize_coords", f"Invalid image_size: {image_size}")

    normalized_walls: List[Wall] = []
    for wall in walls:
        norm_points = [
            Point2D(
                x=max(0.0, min(1.0, p.x)),
                y=max(0.0, min(1.0, p.y)),
            )
            for p in wall.points
        ]
        normalized_walls.append(Wall(
            id=wall.id,
            points=norm_points,
            thickness=wall.thickness,
        ))

    # Rooms and doors are already normalized from room_detect/door_detect
    # Just clamp for safety
    normalized_rooms: List[Room] = []
    for room in rooms:
        norm_polygon = [
            Point2D(x=max(0.0, min(1.0, p.x)), y=max(0.0, min(1.0, p.y)))
            for p in room.polygon
        ]
        normalized_rooms.append(Room(
            id=room.id,
            name=room.name,
            polygon=norm_polygon,
            center=Point2D(
                x=max(0.0, min(1.0, room.center.x)),
                y=max(0.0, min(1.0, room.center.y)),
            ),
            room_type=room.room_type,
            area_normalized=room.area_normalized,
            # Carry inter-floor link fields through the rebuild so elevator
            # data is not silently dropped (floor-transition-tools), and the
            # stair directional gates likewise (multifloor-routing, D).
            floor_from=room.floor_from,
            floor_to=room.floor_to,
            floors_excluded=list(room.floors_excluded),
            connects_up=room.connects_up,
            connects_down=room.connects_down,
        ))

    normalized_doors: List[Door] = []
    for door in doors:
        normalized_doors.append(Door(
            id=door.id,
            position=Point2D(
                x=max(0.0, min(1.0, door.position.x)),
                y=max(0.0, min(1.0, door.position.y)),
            ),
            width=door.width,
            connects=door.connects,
        ))

    return normalized_walls, normalized_rooms, normalized_doors
