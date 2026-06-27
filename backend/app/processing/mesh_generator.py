"""
Pure functions for 3D mesh generation from floor plan geometry.

Input: Shapely polygons, trimesh objects, room data.
Output: trimesh.Trimesh meshes with vertex colors.
No state, no file I/O, no DB access.
"""

import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import trimesh
    from trimesh import creation as trimesh_creation
    TRIMESH_AVAILABLE = True
except ImportError:
    trimesh = None  # type: ignore[assignment]
    TRIMESH_AVAILABLE = False
    logger.warning("trimesh not installed")

try:
    from shapely.geometry import Polygon, MultiPolygon, box as shapely_box
    SHAPELY_AVAILABLE = True
except ImportError:
    Polygon = None  # type: ignore[assignment]
    MultiPolygon = None  # type: ignore[assignment]
    shapely_box = None  # type: ignore[assignment]
    SHAPELY_AVAILABLE = False
    logger.warning("shapely not installed")


# Constants

MIN_DOOR_WIDTH: float = 0.3  # metres — minimum door opening width
MIN_POLYGON_AREA: float = 0.01  # m² — skip tiny polygons

WALL_COLOR: list = [230, 230, 230, 255]        # light grey #e6e6e6
DEFAULT_FLOOR_COLOR: list = [245, 240, 232, 255]  # beige #f5f0e8

# Diplom3D cyber-brutalism palette
WALL_SIDE_COLOR: list = [158, 158, 158, 255]   # grey       #9E9E9E — wall sides
WALL_CAP_COLOR: list  = [255, 69, 0, 255]      # orange     #FF4500 — wall tops
FLOOR_COLOR: list     = [184, 181, 173, 255]   # warm grey  #B8B5AD — floor

ROOM_COLORS: dict = {
    "classroom":  [245, 197, 66,  255],   # yellow  #f5c542
    "corridor":   [66,  135, 245, 255],   # blue    #4287f5
    "staircase":  [245, 66,  66,  255],   # red     #f54242
    "toilet":     [66,  245, 200, 255],   # teal    #42f5c8
    "other":      [200, 200, 200, 255],   # grey    #c8c8c8
    "room":       [200, 200, 200, 255],   # grey    #c8c8c8 (legacy default)
}


# Polygon helpers

def contour_to_polygon(
    contour: np.ndarray,
    scale: float = 1.0,
) -> "Optional[Polygon]":
    """
    Convert an OpenCV contour to a Shapely Polygon.

    Args:
        contour: OpenCV contour, shape (N, 1, 2) or (N, 2), dtype int/float.
        scale: Multiply all coordinates by this factor (pixels → metres).

    Returns:
        Valid Shapely Polygon, or None if conversion fails.
    """
    if not SHAPELY_AVAILABLE:
        raise RuntimeError("shapely not installed")

    pts = contour.copy()
    if pts.ndim == 3:
        pts = pts.reshape(-1, 2)

    pts = pts.astype(float) * scale

    if len(pts) < 3:
        return None

    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly if poly.is_valid and not poly.is_empty else None
    except Exception as exc:
        logger.debug("contour_to_polygon failed: %s", exc)
        return None


def contours_to_polygons(
    contours: List[np.ndarray],
    image_height: int,
    pixels_per_meter: float,
) -> "List[Polygon]":
    """
    Batch-convert OpenCV contours to Shapely polygons (pixels → metres).

    Args:
        contours: List of OpenCV contours (N, 1, 2) int32, pixel coordinates.
        image_height: Image height in pixels (used for Y-axis flip: OpenCV Y-down → 3D Y-up).
        pixels_per_meter: Scale factor (pixels → metres).

    Returns:
        List of valid Shapely Polygon objects in metres.
    """
    if not SHAPELY_AVAILABLE:
        raise RuntimeError("shapely not installed")

    scale = 1.0 / pixels_per_meter
    h_m = image_height * scale  # image height in metres
    result: List[Polygon] = []

    for contour in contours:
        geom = contour_to_polygon(contour, scale=scale)
        if geom is None:
            continue

        geoms = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]

        for poly in geoms:
            try:
                if not poly.is_valid or poly.is_empty:
                    continue
                # Flip Y: OpenCV uses Y-down, 3D scene uses Y-up
                coords = list(poly.exterior.coords)
                flipped = [(x, h_m - y) for x, y in coords]

                holes = []
                for hole in poly.interiors:
                    hole_coords = list(hole.coords)
                    flipped_hole = [(x, h_m - y) for x, y in hole_coords]
                    holes.append(flipped_hole)

                new_poly = Polygon(flipped, holes) if holes else Polygon(flipped)
                if not new_poly.is_valid:
                    new_poly = new_poly.buffer(0)
                if new_poly.is_valid and not new_poly.is_empty:
                    result.append(new_poly)
            except Exception as exc:
                logger.debug("contours_to_polygons: skipping polygon: %s", exc)

    return result


# Mesh builders

def extrude_wall(
    polygon: "Polygon",
    height: float,
) -> "Optional[trimesh.Trimesh]":
    """
    Extrude a 2D polygon into a 3D wall mesh.

    Args:
        polygon: Shapely Polygon (footprint of the wall).
        height: Extrusion height in metres.

    Returns:
        trimesh.Trimesh or None on failure.
    """
    if not TRIMESH_AVAILABLE:
        raise RuntimeError("trimesh not installed")

    try:
        mesh = trimesh_creation.extrude_polygon(polygon, height=height)
        return mesh
    except Exception as exc:
        logger.debug("extrude_wall failed: %s", exc)
        return None


def build_floor_mesh(
    polygon: "Polygon",
    z_offset: float = 0.0,
) -> "Optional[trimesh.Trimesh]":
    """
    Build a thin floor slab from a room polygon.

    Args:
        polygon: Shapely Polygon (room footprint, in metres).
        z_offset: Vertical offset (0.0 = ground level).

    Returns:
        trimesh.Trimesh (0.05 m thick slab) or None on failure.
    """
    if not TRIMESH_AVAILABLE:
        raise RuntimeError("trimesh not installed")

    try:
        mesh = trimesh_creation.extrude_polygon(polygon, height=0.05)
        if z_offset != 0.0:
            mesh.apply_translation([0.0, 0.0, z_offset])
        return mesh
    except Exception as exc:
        logger.debug("build_floor_mesh failed: %s", exc)
        return None


def build_floor_mesh_rect(
    width: float,
    depth: float,
    z_offset: float = 0.0,
) -> "trimesh.Trimesh":
    """
    Build a rectangular floor slab (fallback when no room polygons).

    Args:
        width: Floor width in metres (X axis).
        depth: Floor depth in metres (Y axis).
        z_offset: Vertical offset.

    Returns:
        trimesh.Trimesh box centred at [width/2, depth/2, z_offset].
    """
    if not TRIMESH_AVAILABLE:
        raise RuntimeError("trimesh not installed")

    mesh = trimesh_creation.box(extents=[width, depth, 0.05])
    mesh.apply_translation([width / 2.0, depth / 2.0, z_offset + 0.025])
    return mesh


def build_ceiling_mesh(
    width: float,
    depth: float,
    z_offset: float,
) -> "trimesh.Trimesh":
    """
    Build a rectangular ceiling slab.

    Args:
        width: Ceiling width in metres.
        depth: Ceiling depth in metres.
        z_offset: Height of the ceiling (= floor_height).

    Returns:
        trimesh.Trimesh box centred at [width/2, depth/2, z_offset].
    """
    if not TRIMESH_AVAILABLE:
        raise RuntimeError("trimesh not installed")

    mesh = trimesh_creation.box(extents=[width, depth, 0.05])
    mesh.apply_translation([width / 2.0, depth / 2.0, z_offset])
    return mesh


def cut_door_opening(
    position: "tuple[float, float]",
    width_m: float,
    wall_thickness: float = 0.4,
    pixels_per_meter: float = 50.0,  # noqa: ARG001 — kept for API consistency
) -> "Optional[Polygon]":
    """
    Return a Shapely box representing a door opening footprint (top-down view).

    Args:
        position: (x, y) centre of the door in metres.
        width_m: Door width in metres.
        wall_thickness: Depth of the opening (= wall thickness), default 0.4 m.
        pixels_per_meter: Unused; kept for API consistency.

    Returns:
        Shapely box or None if width_m < MIN_DOOR_WIDTH.
    """
    if not SHAPELY_AVAILABLE:
        raise RuntimeError("shapely not installed")

    if width_m < MIN_DOOR_WIDTH:
        return None

    cx, cy = position
    half_w = width_m / 2.0
    half_d = wall_thickness / 2.0
    return shapely_box(cx - half_w, cy - half_d, cx + half_w, cy + half_d)


# Colour assignment

def assign_room_colors(
    mesh: "trimesh.Trimesh",
    rooms: list,
    pixels_per_meter: float,
    image_width: int = 0,
    image_height: int = 0,
) -> "trimesh.Trimesh":
    """
    Assign vertex colours to a combined mesh by room type.

    Walls receive WALL_COLOR; room floors receive their type colour from ROOM_COLORS.

    Args:
        mesh: Combined trimesh.Trimesh (walls + floors + ceiling).
        rooms: List of Room domain objects (may be empty).
        pixels_per_meter: Scale factor used to convert room centres to metres.
        image_width: Image width in pixels (for denormalizing room centres).
        image_height: Image height in pixels (for denormalizing room centres).

    Returns:
        The same mesh with vertex_colors set (modified in-place copy).
    """
    if not TRIMESH_AVAILABLE:
        raise RuntimeError("trimesh not installed")

    result = mesh.copy()

    if not rooms:
        colors = np.tile(WALL_COLOR, (len(result.vertices), 1))
        result.visual.vertex_colors = colors.astype(np.uint8)
        return result

    # Default: wall colour for all vertices
    colors = np.tile(WALL_COLOR, (len(result.vertices), 1)).astype(np.uint8)

    for room in rooms:
        room_type = getattr(room, "room_type", "other")
        color = ROOM_COLORS.get(room_type, ROOM_COLORS["other"])

        center = getattr(room, "center", None)
        if center is None:
            continue

        cx_norm = getattr(center, "x", 0.0)
        cy_norm = getattr(center, "y", 0.0)

        # Denormalize [0,1] → metres
        cx = (cx_norm * image_width) / pixels_per_meter if image_width else cx_norm
        cy = (cy_norm * image_height) / pixels_per_meter if image_height else cy_norm

        # Vertices whose XY distance to room centre (before rotation) is within radius
        verts = result.vertices
        dist = np.sqrt((verts[:, 0] - cx) ** 2 + (verts[:, 1] - cy) ** 2)
        area_norm = getattr(room, "area_normalized", 0.0)
        if area_norm > 0 and image_width and image_height:
            area_m2 = area_norm * (image_width / pixels_per_meter) * (image_height / pixels_per_meter)
            radius = max(0.5, (area_m2 ** 0.5) / 2.0)
        else:
            radius = 2.0
        mask = dist < radius
        colors[mask] = color

    result.visual.vertex_colors = colors
    return result
