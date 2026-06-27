"""
Pure functions for contour extraction and structural element classification.

Detects and classifies structural elements from binary masks:
- Walls (linear contours)
- Rooms (closed polygons)
- Doors (small openings)
- Stairs (complex shapes)

All functions are PURE — no DB, no HTTP, no file I/O, no state.
"""

import logging
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StructuralElement:
    """Structural element detected from floor plan."""
    id: int
    element_type: str  # wall, room, door, stairs, exit, unknown, noise
    contour: np.ndarray
    area: float
    perimeter: float
    center: Tuple[float, float]
    bounding_box: Tuple[int, int, int, int]  # x, y, width, height
    vertices: int
    aspect_ratio: float


def find_contours(
    binary_image: np.ndarray,
    mode: int = cv2.RETR_TREE,
    method: int = cv2.CHAIN_APPROX_SIMPLE
) -> Tuple[List[np.ndarray], Optional[np.ndarray]]:
    """
    Find contours in binary image.

    Args:
        binary_image: Binary mask (H, W), dtype=uint8. NOT mutated.
        mode: Contour retrieval mode:
            - RETR_EXTERNAL: only outermost contours
            - RETR_LIST: all contours, no hierarchy
            - RETR_TREE: full hierarchy
        method: Contour approximation method:
            - CHAIN_APPROX_NONE: all boundary points
            - CHAIN_APPROX_SIMPLE: only corner points

    Returns:
        Tuple of:
            - contours: List of contours, each (N, 1, 2) int32
            - hierarchy: Contour hierarchy array or None
    """
    contours, hierarchy = cv2.findContours(
        binary_image.copy(),
        mode,
        method
    )
    return list(contours), hierarchy


def approximate_contour(
    contour: np.ndarray,
    epsilon_factor: float = 0.02
) -> np.ndarray:
    """
    Approximate contour with polygon (Douglas-Peucker algorithm).

    Simplifies contour by removing redundant points while preserving shape.

    Args:
        contour: Contour (N, 1, 2), dtype int32. NOT mutated.
        epsilon_factor: Approximation accuracy (0.01-0.05).
            Higher = more aggressive simplification.

    Returns:
        Simplified contour (M, 1, 2), dtype int32, where M <= N.
    """
    epsilon = epsilon_factor * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    return approx


def get_contour_properties(contour: np.ndarray) -> Dict[str, Any]:
    """
    Compute geometric properties of contour.

    Args:
        contour: Contour (N, 1, 2), dtype int32. NOT mutated.

    Returns:
        Dict with keys:
            - area: contour area (pixels²)
            - perimeter: contour perimeter (pixels)
            - center: (cx, cy) center of mass
            - bounding_box: (x, y, w, h) bounding rectangle
            - vertices: number of vertices
            - aspect_ratio: width/height of bounding box
            - extent: area / bounding_box_area
            - solidity: area / convex_hull_area
    """
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)
    x, y, w, h = cv2.boundingRect(contour)

    # Center of mass
    M = cv2.moments(contour)
    if M["m00"] != 0:
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
    else:
        cx, cy = x + w // 2, y + h // 2

    # Aspect ratio
    aspect_ratio = w / h if h > 0 else 0

    # Extent: area / bounding_box_area
    rect_area = w * h
    extent = area / rect_area if rect_area > 0 else 0

    # Solidity: area / convex_hull_area
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)
    solidity = area / hull_area if hull_area > 0 else 0

    return {
        "area": area,
        "perimeter": perimeter,
        "center": (cx, cy),
        "bounding_box": (x, y, w, h),
        "vertices": len(contour),
        "aspect_ratio": aspect_ratio,
        "extent": extent,
        "solidity": solidity
    }


def classify_element(
    contour: np.ndarray,
    properties: Dict[str, Any],
    min_wall_aspect: float = 4.0,
    min_room_area: float = 1000,
    max_door_area: float = 500
) -> str:
    """
    Classify contour by structural element type.

    Uses geometric heuristics:
    - Walls: elongated (aspect ratio > 4)
    - Rooms: large closed polygons (area > 1000, 4-8 vertices, high solidity)
    - Doors: small openings (area < 500)
    - Stairs: complex shapes (many vertices, low solidity)
    - Noise: tiny objects (area < 50)

    Args:
        contour: Contour (N, 1, 2), dtype int32. NOT mutated.
        properties: Geometric properties from get_contour_properties().
        min_wall_aspect: Minimum aspect ratio for walls.
        min_room_area: Minimum area for rooms (pixels²).
        max_door_area: Maximum area for doors (pixels²).

    Returns:
        Element type: "wall", "room", "door", "stairs", "unknown", "noise".
    """
    area = properties["area"]
    aspect = properties["aspect_ratio"]
    vertices = properties["vertices"]
    solidity = properties["solidity"]

    # Noise: too small
    if area < 50:
        return "noise"

    # Wall: elongated shape
    if aspect > min_wall_aspect or aspect < 1 / min_wall_aspect:
        return "wall"

    # Room: large closed polygon
    if area > min_room_area and 4 <= vertices <= 8 and solidity > 0.8:
        return "room"

    # Door: small opening
    if area < max_door_area and vertices <= 6:
        return "door"

    # Stairs: complex shape
    if vertices > 8 and solidity < 0.6:
        return "stairs"

    return "unknown"


def extract_elements(
    binary_image: np.ndarray,
    min_area: int = 100,
    epsilon_factor: float = 0.02
) -> List[StructuralElement]:
    """
    Extract and classify all structural elements from binary mask.

    Pipeline:
    1. Find contours
    2. Approximate each contour
    3. Compute geometric properties
    4. Classify by type
    5. Filter noise

    Args:
        binary_image: Binary mask (H, W), dtype=uint8. NOT mutated.
        min_area: Minimum contour area to consider (pixels²).
        epsilon_factor: Contour approximation accuracy (0.01-0.05).

    Returns:
        List of StructuralElement (excludes noise).
    """
    contours, hierarchy = find_contours(binary_image)
    elements = []
    element_id = 0

    for contour in contours:
        # Approximate
        approx = approximate_contour(contour, epsilon_factor)

        # Properties
        props = get_contour_properties(approx)

        # Filter by area
        if props["area"] < min_area:
            continue

        # Classify
        element_type = classify_element(approx, props)

        if element_type == "noise":
            continue

        # Create element
        element_id += 1
        element = StructuralElement(
            id=element_id,
            element_type=element_type,
            contour=approx,
            area=props["area"],
            perimeter=props["perimeter"],
            center=props["center"],
            bounding_box=props["bounding_box"],
            vertices=props["vertices"],
            aspect_ratio=props["aspect_ratio"]
        )
        elements.append(element)

    logger.info(
        "Extracted %d elements: walls=%d, rooms=%d, doors=%d",
        len(elements),
        sum(1 for e in elements if e.element_type == "wall"),
        sum(1 for e in elements if e.element_type == "room"),
        sum(1 for e in elements if e.element_type == "door"),
    )

    return elements


def draw_contours(
    image: np.ndarray,
    elements: List[StructuralElement],
    show_labels: bool = True
) -> np.ndarray:
    """
    Visualize contours on image.

    Args:
        image: BGR or grayscale image (H, W, 3) or (H, W), dtype=uint8. NOT mutated.
        elements: List of structural elements to draw.
        show_labels: Draw element type labels at centers.

    Returns:
        BGR image with drawn contours (H, W, 3), dtype=uint8.
    """
    result = image.copy()
    if len(result.shape) == 2:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

    colors = {
        "wall": (0, 255, 0),      # Green
        "room": (255, 0, 0),      # Blue
        "door": (0, 255, 255),    # Yellow
        "stairs": (255, 0, 255),  # Magenta
        "unknown": (128, 128, 128) # Gray
    }

    for element in elements:
        color = colors.get(element.element_type, (255, 255, 255))
        cv2.drawContours(result, [element.contour], -1, color, 2)

        if show_labels:
            cx, cy = element.center
            label = f"{element.element_type[:1].upper()}{element.id}"
            cv2.putText(
                result, label, (int(cx) - 10, int(cy) + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1
            )

    return result


def get_wall_contours(elements: List[StructuralElement]) -> List[np.ndarray]:
    """
    Extract only wall contours from elements.

    Args:
        elements: List of structural elements.

    Returns:
        List of wall contours, each (N, 1, 2) int32.
    """
    return [e.contour for e in elements if e.element_type == "wall"]
