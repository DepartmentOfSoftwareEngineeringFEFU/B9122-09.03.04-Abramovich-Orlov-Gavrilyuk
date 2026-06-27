"""Floor-level nav-graph helpers — PURE processing layer.

Bridges section room/door coordinates into the assembled floor-canvas space and
orchestrates the existing ``nav_graph.py`` pipeline on the assembled floor mask.

NOTE: ``processing/`` is the PURE layer. This module imports ONLY ``math`` /
``numpy`` / ``networkx`` / ``dataclasses`` / ``typing`` / stdlib +
``app.core.exceptions`` at module level. The heavier ``app.processing.nav_graph``
/ ``app.processing.pipeline`` imports are done lazily inside
``build_floor_graph_from_mask`` (pure → pure imports, deferred to keep import
time light — mirrors ``nav_service.py``). No DB, no HTTP, no file IO, no service
imports.

CRITICAL — the "no shifts" guarantee:
The solved similarity ``(scale, rotation_rad, tx, ty)`` is applied by
``cv2.warpAffine`` directly to the section wall-mask ARRAY (mask-pixel →
master-pixel). Therefore a room/door MUST be de-normalised by the EXACT pixel
dimensions of the loaded mask array that is warped — ``mask.shape[1]`` (W) /
``mask.shape[0]`` (H) — NOT the stored ``vectorization_data.image_size_cropped``
(only asserted ≈ mask aspect). Using ``image_size_cropped`` would introduce
exactly the room "shift" the feature must avoid. Rooms/doors warp through the SAME
``scale·R(rotation_rad)`` + translation as the walls, so they stay aligned by
construction.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import numpy as np

from app.core.exceptions import ImageProcessingError

logger = logging.getLogger(__name__)

# Door→corridor snap bounds (R5, [B2]). The distance cap is
# deliberately LOOSE — its only job is to reject absurd cross-canvas snaps; the
# seeded line-of-sight does the real cross-section rejection. Derived from wall
# thickness so the bounds scale with the plan's pixel resolution.
SNAP_RATIO: float = 12.0
MIN_SNAP_PX: float = 12.0
MAX_SNAP_PX_CAP: float = 80.0

# Bridge-distance bounds. Skeletonisation can break a
# single corridor into disconnected fragments (1-px medial-axis gaps) → A* finds no
# route across them. ``bridge_graph_components`` stitches fragments with short wall-clear
# edges up to this many px apart. The ceiling was RAISED 32→60 (Stage A) so the
# main corridor absorbs more skeleton-break fragments before rooms attach; still
# LOS-gated — the distance cap, not the gate, is what changed, so it still refuses to
# bridge across a wall. Only MIN is empirically validated (room-2 gap = 10px on live
# floor 1); RATIO/MAX are extrapolation, easily tuned.
BRIDGE_RATIO: float = 10.0
MIN_BRIDGE_PX: float = 12.0
MAX_BRIDGE_PX: float = 60.0

# Room→corridor attach cap. For rooms with
# NO door (every stair/elevator) and any door-snap failure: snap the room to the nearest
# LOS-clear corridor node from its bbox edge. Wall-thickness-scaled like SNAP_RATIO; the
# seeded LOS — not this cap — is the wall guard. Edge-distance ~60px validated on live
# floor 1; RATIO/MIN/MAX are EXTRAPOLATION, tune if a live floor needs it.
ATTACH_RATIO: float = 12.0
MIN_ATTACH_PX: float = 24.0
MAX_ATTACH_PX: float = 64.0


@dataclass(frozen=True)
class SectionRoomInput:
    """One room from ``Reconstruction.vectorization_data`` plus the section's
    k-scaled transform and the LOADED MASK pixel dims.

    Attributes:
        room_id: room identifier from ``vectorization_data.rooms[*].id``.
        name: human room name (e.g. "Аудитория 301").
        room_type: room category (``room`` / ``staircase`` / ``elevator`` / ...).
        polygon: room outline as ``[(x, y), ...]`` normalised [0,1] over the
            SECTION cropped wall mask (``VectorRoom.polygon``). The floor bbox is
            the AABB of these vertices AFTER the similarity warp — under rotation
            the section-space bbox is NOT the floor-space bbox, so the vertices are
            warped first, then the floor-space AABB is taken.
        mask_w: pixel width of the SECTION WALL-MASK ARRAY that is warped into the
            floor (``mask.shape[1]``) — NOT ``image_size_cropped``. This is what
            makes rooms track walls with zero shift.
        mask_h: pixel height of the SECTION WALL-MASK ARRAY (``mask.shape[0]``).
        scale_k: ``section.transform["scale"] * k`` (pre-multiplied by the canvas
            memory-guard factor ``k``).
        rotation_rad: ``section.transform["rotation_rad"]`` — NOT k-scaled (a
            rotation is invariant to the uniform memory-guard factor ``k``).
        tx_k: ``section.transform["tx"] * k``.
        ty_k: ``section.transform["ty"] * k``.
        floor_from: elevator lowest served floor (``None`` for non-elevators).
        floor_to: elevator highest served floor (``None`` for non-elevators).
        floors_excluded: elevator floors the cabin skips (empty for non-elevators).
        connects_up: stair gate — links to the floor ABOVE (default ``True``).
        connects_down: stair gate — links to the floor BELOW (default ``True``).
    """

    room_id: str
    name: str
    room_type: str
    polygon: list[tuple[float, float]]
    mask_w: int
    mask_h: int
    scale_k: float
    rotation_rad: float
    tx_k: float
    ty_k: float
    # Transition metadata (multifloor-routing, D) — threaded onto the persisted
    # nav node so route-time matching never re-reads ``vectorization_data``.
    floor_from: Optional[int] = None
    floor_to: Optional[int] = None
    floors_excluded: list[int] = field(default_factory=list)
    connects_up: bool = True
    connects_down: bool = True


def transform_rooms_to_floor_canvas(
    rooms: list[SectionRoomInput],
    canvas_w: int,
    canvas_h: int,
) -> list[dict]:
    """Transform section-norm room polygons to floor-canvas-norm bbox dicts.

    Each room polygon vertex is de-normalised by the room's OWN loaded-mask pixel
    dims (``mask_w`` / ``mask_h``), warped through the SAME k-scaled similarity
    ``scale_k · R(rotation_rad)`` + ``(tx_k, ty_k)`` that ``assemble_floor_mask``
    applies to the section wall pixels, and the axis-aligned bounding box of the
    warped vertices is taken, clipped to the canvas, then re-normalised to [0,1]
    over the floor canvas. Warping the vertices then taking the floor-space AABB is
    correct under rotation — the section-space AABB is NOT the floor-space AABB.
    This guarantees rooms land on the assembled walls with zero shift.

    Args:
        rooms: section rooms with their k-scaled transforms + LOADED mask dims.
        canvas_w: assembled canvas width in pixels.
        canvas_h: assembled canvas height in pixels.

    Returns:
        List of dicts with keys ``id``, ``name``, ``room_type``, ``x``, ``y``,
        ``width``, ``height`` (axis-aligned bbox) plus the oriented box
        ``obb_cx``/``obb_cy``/``obb_w``/``obb_h`` and ``rotation_rad`` (Q2 fix —
        true dims + angle so the 3D room box renders rotated); all lengths
        normalised [0,1] over ``(canvas_w, canvas_h)``. The dict shape matches
        what ``nav_graph.integrate_semantics`` consumes. Rooms are clipped to the
        canvas; zero-area rooms (after clipping) are dropped.
    """
    result: list[dict] = []
    for room in rooms:
        # scale·R(rotation_rad): the SAME similarity the wall pixels get.
        cos = room.scale_k * math.cos(room.rotation_rad)
        sin = room.scale_k * math.sin(room.rotation_rad)
        floor_xs: list[float] = []
        floor_ys: list[float] = []
        sec_xs: list[float] = []
        sec_ys: list[float] = []
        for norm_x, norm_y in room.polygon:
            # De-normalise by the LOADED MASK dims (the warped array) —.
            sec_px_x = norm_x * room.mask_w
            sec_px_y = norm_y * room.mask_h
            sec_xs.append(sec_px_x)
            sec_ys.append(sec_px_y)
            floor_xs.append(cos * sec_px_x - sin * sec_px_y + room.tx_k)
            floor_ys.append(sin * sec_px_x + cos * sec_px_y + room.ty_k)
        if not floor_xs:
            continue

        # Axis-aligned bbox of the warped vertices, clipped to the canvas.
        x0 = max(0.0, min(min(floor_xs), canvas_w - 1.0))
        y0 = max(0.0, min(min(floor_ys), canvas_h - 1.0))
        floor_px_w = min(max(floor_xs) - min(floor_xs), canvas_w - x0)
        floor_px_h = min(max(floor_ys) - min(floor_ys), canvas_h - y0)

        if floor_px_w <= 0 or floor_px_h <= 0:
            continue

        # Oriented box (Q2-поворот fix): the room is axis-aligned in its OWN
        # section, so the section-space AABB gives the TRUE (un-inflated) dims.
        # Warp the section-bbox CENTER through the SAME similarity and carry
        # rotation_rad, so the 3D room box can render rotated to match the warped
        # walls — the floor-space AABB above is inflated + axis-aligned and so
        # cannot represent the rotation.
        sec_cx = (min(sec_xs) + max(sec_xs)) / 2.0
        sec_cy = (min(sec_ys) + max(sec_ys)) / 2.0
        obb_cx = cos * sec_cx - sin * sec_cy + room.tx_k
        obb_cy = sin * sec_cx + cos * sec_cy + room.ty_k
        obb_w = (max(sec_xs) - min(sec_xs)) * room.scale_k
        obb_h = (max(sec_ys) - min(sec_ys)) * room.scale_k

        result.append(
            {
                "id": room.room_id,
                "name": room.name,
                "room_type": room.room_type,
                "x": x0 / canvas_w,
                "y": y0 / canvas_h,
                "width": floor_px_w / canvas_w,
                "height": floor_px_h / canvas_h,
                "obb_cx": obb_cx / canvas_w,
                "obb_cy": obb_cy / canvas_h,
                "obb_w": obb_w / canvas_w,
                "obb_h": obb_h / canvas_h,
                "rotation_rad": room.rotation_rad,
                # Transition metadata pass-through (D) — pure carry, no maths.
                "floor_from": room.floor_from,
                "floor_to": room.floor_to,
                "floors_excluded": list(room.floors_excluded),
                "connects_up": room.connects_up,
                "connects_down": room.connects_down,
            }
        )
    return result


@dataclass(frozen=True)
class SectionDoorInput:
    """One door from ``Reconstruction.vectorization_data`` plus the section's
    k-scaled transform and the LOADED MASK pixel dims.

    Attributes:
        door_id: door identifier from ``vectorization_data.doors[*].id``.
        position: door centre ``(x, y)`` normalised [0,1] over the SECTION cropped
            wall mask (``VectorDoor.position``).
        room_id: the room this door connects to (``connects[0]``), or ``None``.
        mask_w: pixel width of the SECTION WALL-MASK ARRAY (``mask.shape[1]``) —
            NOT ``image_size_cropped``.
        mask_h: pixel height of the SECTION WALL-MASK ARRAY (``mask.shape[0]``).
        scale_k: ``section.transform["scale"] * k``.
        rotation_rad: ``section.transform["rotation_rad"]`` — NOT k-scaled.
        tx_k: ``section.transform["tx"] * k``.
        ty_k: ``section.transform["ty"] * k``.
    """

    door_id: str
    position: tuple[float, float]
    room_id: Optional[str]
    mask_w: int
    mask_h: int
    scale_k: float
    rotation_rad: float
    tx_k: float
    ty_k: float


def transform_doors_to_floor_canvas(
    doors: list[SectionDoorInput],
    canvas_w: int,
    canvas_h: int,
) -> list[dict]:
    """Transform section-norm door points to floor-canvas-norm point dicts.

    Each door position is de-normalised by the door's OWN loaded-mask pixel dims,
    warped through the SAME ``scale_k · R(rotation_rad)`` + ``(tx_k, ty_k)``
    similarity as the walls/rooms, clipped to the canvas and re-normalised to
    [0,1]. The emitted shape is a degenerate "point" segment (``x1 == x2``,
    ``y1 == y2``) — exactly what ``nav_graph.integrate_semantics`` consumes for a
    door.

    Args:
        doors: section doors with their k-scaled transforms + LOADED mask dims.
        canvas_w: assembled canvas width in pixels.
        canvas_h: assembled canvas height in pixels.

    Returns:
        List of dicts with keys ``id``, ``x1``, ``y1``, ``x2``, ``y2``,
        ``room_id`` (``x1 == x2``, ``y1 == y2``), normalised [0,1] over the canvas.
    """
    result: list[dict] = []
    for door in doors:
        cos = door.scale_k * math.cos(door.rotation_rad)
        sin = door.scale_k * math.sin(door.rotation_rad)
        sec_px_x = door.position[0] * door.mask_w
        sec_px_y = door.position[1] * door.mask_h
        floor_px_x = cos * sec_px_x - sin * sec_px_y + door.tx_k
        floor_px_y = sin * sec_px_x + cos * sec_px_y + door.ty_k

        # Clip to canvas bounds.
        floor_px_x = max(0.0, min(floor_px_x, canvas_w - 1.0))
        floor_px_y = max(0.0, min(floor_px_y, canvas_h - 1.0))

        norm_x = floor_px_x / canvas_w
        norm_y = floor_px_y / canvas_h
        result.append(
            {
                "id": door.door_id,
                "x1": norm_x,
                "y1": norm_y,
                "x2": norm_x,
                "y2": norm_y,
                "room_id": door.room_id,
            }
        )
    return result


def build_floor_graph_from_mask(
    assembled_mask: np.ndarray,
    floor_rooms: list[dict],
    floor_doors: list[dict],
    canvas_w: int,
    canvas_h: int,
) -> nx.Graph:
    """Build a nav topology graph from an assembled floor mask.

    Delegates entirely to the existing pure helpers in ``nav_graph.py`` — no new
    topology logic. Computes the corridor mask, skeletonises it, builds the
    topology graph, prunes dendrites and integrates room + door semantics.

    Args:
        assembled_mask: ``(H, W)`` uint8 ``{0,255}`` — white = walls. Not
            None/empty; dtype must be ``uint8``.
        floor_rooms: room dicts normalised [0,1] over the canvas (output of
            ``transform_rooms_to_floor_canvas``).
        floor_doors: door dicts normalised [0,1] over the canvas (output of
            ``transform_doors_to_floor_canvas``); ``[]`` when the floor has none.
        canvas_w: canvas width (``== assembled_mask.shape[1]``).
        canvas_h: canvas height (``== assembled_mask.shape[0]``).

    Returns:
        ``nx.Graph`` with ``corridor_node`` / ``room`` / ``door`` /
        ``corridor_entry`` node types.

    Raises:
        ImageProcessingError: if ``assembled_mask`` is None, empty, or wrong dtype.
    """
    from app.processing.nav_graph import (
        attach_unlinked_rooms,
        bridge_graph_components,
        build_skeleton,
        build_topology_graph,
        extract_corridor_mask,
        integrate_semantics,
        prune_dendrites,
    )
    # NOTE: compute_wall_thickness lives in pipeline, NOT nav_graph.
    from app.processing.pipeline import compute_wall_thickness

    if assembled_mask is None or assembled_mask.size == 0:
        raise ImageProcessingError("build_floor_graph_from_mask", "Empty mask")
    if assembled_mask.dtype != np.uint8:
        raise ImageProcessingError(
            "build_floor_graph_from_mask",
            f"Expected uint8, got {assembled_mask.dtype}",
        )

    wall_thickness_px = compute_wall_thickness(assembled_mask)
    if wall_thickness_px <= 0:
        wall_thickness_px = 3.0  # fallback

    # R5 snap bounds derived locally from wall thickness — no ppm
    # threading. The seeded LOS (skip_px past the door's own wall) is the real
    # cross-section gate; max_snap_dist_px only rejects absurd cross-canvas snaps.
    max_snap_dist_px = min(
        MAX_SNAP_PX_CAP, max(MIN_SNAP_PX, SNAP_RATIO * wall_thickness_px)
    )
    skip_px = wall_thickness_px + 1.0

    corridor_mask = extract_corridor_mask(
        assembled_mask, floor_rooms, canvas_w, canvas_h, wall_thickness_px
    )
    skeleton = build_skeleton(corridor_mask)
    graph = build_topology_graph(skeleton)
    graph = prune_dendrites(graph, min_branch_length=20.0)

    # Reconnect corridor fragments split by skeletonisation BEFORE door snapping,
    # so an isolated room's stub rejoins the network and its door can snap to it
    #. LOS-gated → never bridges across a wall.
    max_bridge_dist_px = min(
        MAX_BRIDGE_PX, max(MIN_BRIDGE_PX, BRIDGE_RATIO * wall_thickness_px)
    )
    graph = bridge_graph_components(graph, assembled_mask, max_bridge_dist_px)

    graph = integrate_semantics(
        graph, floor_rooms, floor_doors, canvas_w, canvas_h,
        assembled_mask, max_snap_dist_px, skip_px,
    )

    # Stage B (in the Pipeline): runs LAST so it sees the
    # bridged corridor fragments + the door-linked rooms, and only attaches rooms
    # still OFF the corridor (every door-less stair/elevator + any door-snap failure)
    # to the nearest LOS-clear corridor node. Reuses the already-computed
    # wall_thickness_px / skip_px — the seeded LOS, not this cap, is the wall guard.
    max_attach_px = min(
        MAX_ATTACH_PX, max(MIN_ATTACH_PX, ATTACH_RATIO * wall_thickness_px)
    )
    graph = attach_unlinked_rooms(graph, assembled_mask, max_attach_px, skip_px)
    return graph
