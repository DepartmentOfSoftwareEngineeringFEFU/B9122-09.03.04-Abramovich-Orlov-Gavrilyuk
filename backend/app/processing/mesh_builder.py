import logging
import math
from typing import List, TYPE_CHECKING

import cv2
import numpy as np

from app.core.exceptions import ImageProcessingError
from app.models.domain import VectorizationResult

if TYPE_CHECKING:
    import trimesh
    from shapely.geometry import Polygon as ShapelyPolygon

logger = logging.getLogger(__name__)

# Floor-slab vertex colour baked into the GLB. A LIGHT warm beige — distinctly
# lighter than the wall colour (mesh_generator.WALL_SIDE_COLOR = 158 grey) and warm
# vs the neutral-grey walls, so the floor reads as its own surface (not merged) in
# the stacked building viewer while staying visible against the white background.
FLOOR_SLAB_COLOR = [208, 202, 188, 255]  # light warm beige


def _create_floor(
    width_m: float,
    height_m: float,
    color: list,
) -> "trimesh.Trimesh | None":
    """Плоский прямоугольный пол в плоскости XZ (Z-up), Y=0."""
    if width_m <= 0 or height_m <= 0:
        return None
    try:
        import trimesh
    except ImportError:
        return None
    vertices = np.array([
        [0.0,     0.0, 0.0],
        [width_m, 0.0, 0.0],
        [width_m, 0.0, height_m],
        [0.0,     0.0, height_m],
    ], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    colors = np.tile(color, (len(vertices), 1)).astype(np.uint8)
    mesh.visual.vertex_colors = colors
    return mesh


def _create_wall_cap(
    polygon: "ShapelyPolygon",
    height: float,
    color: list,
) -> "trimesh.Trimesh | None":
    """Плоская крышка полигона стены на заданной высоте (Z-up пространство).

    Сдвигается вдоль Z на height. После rotation_matrix(-pi/2, [1,0,0])
    ось Z становится Y, поэтому крышка окажется на Y=height в Three.js.
    """
    try:
        from trimesh import creation as trimesh_creation
    except ImportError:
        return None
    try:
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            return None
        cap = trimesh_creation.extrude_polygon(polygon, height=0.001)
        if cap is None or len(cap.vertices) == 0:
            return None
        # Translate along Z (Z-up space, before -90° X rotation)
        cap.apply_translation([0, 0, height + 0.001])
        colors = np.tile(color, (len(cap.vertices), 1)).astype(np.uint8)
        cap.visual.vertex_colors = colors
        return cap
    except Exception as exc:
        logger.debug("_create_wall_cap failed: %s", exc)
        return None


def build_mesh_from_mask(
    mask: np.ndarray,
    floor_height: float = 3.0,
    pixels_per_meter: float = 50.0,
    vr: "VectorizationResult | None" = None,
    transitions: list[list[list[float]]] | None = None,
) -> "trimesh.Trimesh":
    """
    Строит 3D-меш этажа из бинарной маски стен.

    Использует cv2.findContours для извлечения контуров стен из маски,
    экструдирует их на floor_height. Без пола и потолка — чистые стены
    для обзора сверху (как карта здания).

    Args:
        mask: Бинарная маска (uint8), белый (255) = стены.
        floor_height: Высота этажа в метрах (default: 3.0).
        pixels_per_meter: Масштаб пикселей на метр.
        vr: Опциональный VectorizationResult для цветов комнат.

    Returns:
        trimesh.Trimesh — объединённый меш. НЕ сохранён на диск.
    """
    try:
        import trimesh
    except ImportError:
        raise ImageProcessingError("build_mesh_from_mask", "trimesh not installed")

    from app.processing.mesh_generator import (
        extrude_wall,
        WALL_SIDE_COLOR,
    )
    from shapely.geometry import Polygon as ShapelyPolygon

    h, w = mask.shape[:2]

    # Sanity check: white should be walls (10-40%), not free space (>50%)
    white_ratio = float(np.sum(mask > 127)) / (h * w)
    logger.info("build_mesh_from_mask: white_ratio=%.1f%%", white_ratio * 100)
    if white_ratio > 0.5:
        logger.warning(
            "build_mesh_from_mask: white_ratio=%.1f%% — mask may be inverted! "
            "Expected white=walls (10-40%%)",
            white_ratio * 100,
        )

    # Step 1: Extract wall contours from mask using RETR_CCOMP hierarchy.
    # For each top-level contour (parent == -1), collect its direct children
    # as holes. This correctly handles the closed outer building boundary:
    # outer ring (57% area) + inner hole (52% area) = wall ring (5% area).
    contours_raw, hierarchy = cv2.findContours(
        mask.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE,
    )

    min_area = 50
    if hierarchy is not None:
        hier = hierarchy[0]
        # Build map: parent_idx → list of child contours
        children: dict = {}
        for i, c in enumerate(contours_raw):
            parent = hier[i][3]
            if parent != -1:
                children.setdefault(parent, []).append(c)

        # Keep top-level contours; attach their holes
        # contours list becomes list of (exterior, [holes])
        contour_pairs = []
        for i, c in enumerate(contours_raw):
            if hier[i][3] == -1 and cv2.contourArea(c) > min_area:
                holes = children.get(i, [])
                contour_pairs.append((c, holes))
        contours = contour_pairs
    else:
        contours = [(c, []) for c in contours_raw if cv2.contourArea(c) > min_area]

    logger.info(
        "build_mesh_from_mask: image=%dx%d, raw=%d, filtered=%d, ppm=%.2f",
        w, h, len(contours_raw), len(contours), pixels_per_meter,
    )

    if not contours:
        raise ImageProcessingError(
            "build_mesh_from_mask", "No wall contours found in mask",
        )

    # Step 2: Contours → polygons (pixels → metres, Y-flip)
    scale = 1.0 / pixels_per_meter
    h_m = h * scale
    polygons = []
    skipped_area = 0
    failed_poly = 0
    for exterior_c, hole_cs in contours:
        ext_pts = exterior_c.reshape(-1, 2).astype(float) * scale
        ext_flipped = [(x, h_m - y) for x, y in ext_pts]
        hole_list = []
        for hole_c in hole_cs:
            hole_pts = hole_c.reshape(-1, 2).astype(float) * scale
            hole_flipped = [(x, h_m - y) for x, y in hole_pts]
            hole_list.append(hole_flipped)
        try:
            poly = ShapelyPolygon(ext_flipped, hole_list)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_valid and not poly.is_empty and poly.area > 0:
                # buffer(0) can return MultiPolygon — unpack it
                if poly.geom_type == "MultiPolygon":
                    for sub_poly in poly.geoms:
                        if sub_poly.is_valid and not sub_poly.is_empty and sub_poly.area > 0:
                            polygons.append(sub_poly)
                else:
                    polygons.append(poly)
            else:
                skipped_area += 1
        except Exception as exc:
            failed_poly += 1
            logger.debug("polygon build failed: %s", exc)
    logger.info(
        "Polygons: %d (skipped_invalid=%d, failed=%d)",
        len(polygons), skipped_area, failed_poly,
    )

    if not polygons:
        raise ImageProcessingError(
            "build_mesh_from_mask", "No valid polygons from contours",
        )

    # Step 3: Extrude walls (sides)
    meshes: list = []
    extrude_failed = 0
    for poly in polygons:
        wall_mesh = extrude_wall(poly, height=floor_height)
        if wall_mesh is not None:
            colors = np.tile(WALL_SIDE_COLOR, (len(wall_mesh.vertices), 1)).astype(np.uint8)
            wall_mesh.visual.vertex_colors = colors
            meshes.append(wall_mesh)
        else:
            extrude_failed += 1
            logger.warning(
                "extrude_wall failed for polygon area=%.4f, points=%d, holes=%d",
                poly.area, len(poly.exterior.coords), len(list(poly.interiors)),
            )

    logger.info("Wall meshes: %d", len(meshes))

    if not meshes:
        raise ImageProcessingError(
            "build_mesh_from_mask", "No wall meshes created",
        )

    # Step 3.4: Floor slab — fill the building footprint so the floor reads as a
    # solid surface under the walls (not floating walls). Union the EXTERIORS of
    # the wall polygons (drop interior holes) → the solid footprint, then extrude a
    # thin slab and drop it a few cm BELOW z=0 (walls rise from z=0) so the slab top
    # never sits coplanar with the wall bottoms — that coplanarity is what causes
    # z-fighting. Best-effort: a slab failure must never block the walls.
    try:
        from shapely.ops import unary_union
        from trimesh import creation as trimesh_creation

        solids = [
            ShapelyPolygon(p.exterior) for p in polygons if p.exterior is not None
        ]
        footprint = unary_union(solids) if solids else None
        if footprint is not None and not footprint.is_empty:
            slab_geoms = (
                list(footprint.geoms)
                if footprint.geom_type == "MultiPolygon"
                else [footprint]
            )
            slab_count = 0
            for sp in slab_geoms:
                if not sp.is_valid:
                    sp = sp.buffer(0)
                if sp.is_empty or sp.area <= 0:
                    continue
                slab = trimesh_creation.extrude_polygon(sp, height=0.1)
                # z in [-0.13, -0.03] → top 3 cm below the walls (no z-fighting).
                slab.apply_translation([0.0, 0.0, -0.13])
                colors = np.tile(
                    FLOOR_SLAB_COLOR, (len(slab.vertices), 1)
                ).astype(np.uint8)
                slab.visual.vertex_colors = colors
                meshes.append(slab)
                slab_count += 1
            logger.info("Floor slab pieces: %d", slab_count)
    except Exception as exc:  # noqa: BLE001 — slab is cosmetic, never fatal
        logger.warning("floor slab build failed (walls kept): %s", exc)

    # Step 3.5: Extrude transitions
    if transitions:
        for t_geom in transitions:
            try:
                ext_pts = [(pt[0] * w * scale, h_m - pt[1] * h * scale) for pt in t_geom]
                poly = ShapelyPolygon(ext_pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_valid and not poly.is_empty and poly.area > 0:
                    t_mesh = extrude_wall(poly, height=0.05)
                    if t_mesh is not None:
                        t_mesh.apply_translation([0, 0, 0.01])  # slightly above floor
                        # Green color for transitions
                        colors = np.tile(
                            [34, 197, 94, 200], (len(t_mesh.vertices), 1)
                        ).astype(np.uint8)
                        t_mesh.visual.vertex_colors = colors
                        meshes.append(t_mesh)
            except Exception as exc:
                logger.debug("Failed to extrude transition: %s", exc)

    # Step 4: Combine
    if not meshes:
        return trimesh.Trimesh()

    combined = trimesh.util.concatenate(meshes)

    # Step 5: Z-up → Y-up (Three.js convention)
    matrix = trimesh.transformations.rotation_matrix(
        -math.pi / 2, [1, 0, 0],
    )
    combined.apply_transform(matrix)

    return combined


# Legacy wrapper
def build_mesh(
    contours: List[np.ndarray],
    image_width: int,
    image_height: int,
    floor_height: float = 3.0,
    pixels_per_meter: float = 50.0,
) -> "trimesh.Trimesh":
    """Legacy: строит меш из готовых контуров."""
    if not contours:
        raise ImageProcessingError("build_mesh", "No contours provided")

    try:
        import trimesh as _trimesh
    except ImportError:
        raise ImageProcessingError("build_mesh", "trimesh not installed")

    from app.processing.mesh_generator import (
        contours_to_polygons,
        extrude_wall,
        WALL_COLOR,
    )

    polygons = contours_to_polygons(contours, image_height, pixels_per_meter)
    meshes = []
    for poly in polygons:
        m = extrude_wall(poly, height=floor_height)
        if m is not None:
            colors = np.tile(WALL_COLOR, (len(m.vertices), 1)).astype(np.uint8)
            m.visual.vertex_colors = colors
            meshes.append(m)

    combined = _trimesh.util.concatenate(meshes)
    matrix = _trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])
    combined.apply_transform(matrix)
    return combined
