"""FloorNavService — assembled-floor nav graph build + routing.

Orchestrates the floor nav graph: rebuilds the assembled floor mask (the SAME
``assemble_floor_mask`` call as ``build_floor_mesh``), transforms section rooms
and doors into floor-canvas space, builds the nav graph and persists it as
``uploads/nav/floor_{id}_nav.json``; then answers route + rooms-3d queries.

Layer rules (``prompts/architecture.md``):
- This is a SERVICE: it owns ALL IO (DB via repositories, masks/schema images via
  ``FileStorage`` + ``cv2.imread``) and calls the PURE ``processing`` functions
  with plain numpy arrays.
- INDEPENDENCE: it does NOT call ``FloorAssemblyService``. It
  recomputes ``k`` / canvas / assembled-mask with the IDENTICAL deterministic
  formula, so the nav graph geometry matches the confirmed GLB exactly. A
  consistency cross-check test guards against drift.
- The "no shifts" guarantee: each room is de-normalised by the LOADED
  section mask's OWN pixel dims (``mask.shape``), never ``image_size_cropped``.
- ``vectorization_data`` is read-only here. Loaded masks are never mutated.
"""

import json
import logging
import math
import os
from typing import Optional

import cv2
import networkx as nx
import numpy as np
from networkx.readwrite import json_graph

from app.core.exceptions import (
    FileStorageError,
    FloorAssemblyConflictError,
    FloorNavGraphNotFoundError,
    FloorNotFoundError,
    FloorSchemaError,
    ImageProcessingError,
)
from app.core.floor_stitching_constants import (
    CANVAS_TRUST_RESIDUAL_M,
    DEFAULT_CONNECTOR_THICKNESS_M,
    FLOOR_HEIGHT,
    MAX_FLOOR_CANVAS_PX,
)
from app.db.repositories.floor_connector_repo import FloorConnectorRepository
from app.db.repositories.floor_repo import FloorRepository
from app.db.repositories.section_repo import SectionRepository
from app.processing.floor_assembly import (
    ConnectorRaster,
    CutoutRaster,
    SectionWarpInput,
    assemble_floor_mask,
    compute_canvas_factor,
)
from app.processing.nav_graph import (
    deserialize_nav_graph,
    find_route,
    los_prune,
    serialize_nav_graph,
    transform_2d_to_3d,
)
from app.processing.nav_graph_floor import (
    SectionDoorInput,
    SectionRoomInput,
    build_floor_graph_from_mask,
    transform_doors_to_floor_canvas,
    transform_rooms_to_floor_canvas,
)
from app.services.file_storage import FileStorage

logger = logging.getLogger(__name__)


def _is_positive_finite(value: Optional[float]) -> bool:
    """True iff ``value`` is a real number that is finite and strictly positive."""
    return value is not None and math.isfinite(value) and value > 0


class FloorNavService:
    """Assembled-floor nav graph build + routing (independent of FloorAssembly)."""

    def __init__(
        self,
        floor_repo: FloorRepository,
        section_repo: SectionRepository,
        connector_repo: FloorConnectorRepository,
        storage: FileStorage,
        upload_dir: str,
    ) -> None:
        self._floor_repo = floor_repo
        self._section_repo = section_repo
        self._connector_repo = connector_repo
        self._storage = storage
        self._nav_dir = os.path.join(upload_dir, "nav")

    # Build

    async def build_floor_nav_graph(self, floor_id: int) -> dict:
        """Rebuild the assembled floor mask + build & persist the nav graph.

        Recomputes ``k`` / canvas / assembled-mask with the IDENTICAL formula as
        ``FloorAssemblyService.build_floor_mesh``transforms section rooms
        into floor-canvas space by their LOADED mask dims, builds the nav
        graph and writes ``uploads/nav/floor_{id}_nav.json`` (idempotent overwrite).

        Args:
            floor_id: floor to build the nav graph for.

        Returns:
            Metadata dict: ``floor_id``, ``nodes_count``, ``edges_count``,
            ``rooms_count``, ``corridor_nodes_count``, ``canvas_size_px``,
            ``scale_factor``.

        Raises:
            FloorNotFoundError: floor absent (404).
            FloorSchemaError: no metric scale / no section masks / empty mask (422).
            FloorAssemblyConflictError: no section has a transform (409).
            ImageProcessingError / FileStorageError: unexpected IO failure.
        """
        logger.info("build_floor_nav_graph: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        ppm = floor.pixels_per_meter
        if not _is_positive_finite(ppm):
            raise FloorSchemaError(
                "Нет метрического масштаба — запустите расчёт преобразований"
            )

        sections = await self._section_repo.list_by_floor(floor_id)
        ok_sections = [s for s in sections if s.transform]
        if not ok_sections:
            raise FloorAssemblyConflictError(
                "Нет секций с рассчитанными преобразованиями"
            )

        master_w, master_h = await self._master_pixel_dims(floor)

        # k — IDENTICAL to floor_assembly_service.build_floor_mesh: the SAME
        # shared helper with the SAME args, so a mis-registered section
        # (high residual) is excluded from the min-scale estimate in BOTH builds.
        long_side = max(master_w, master_h)
        k = compute_canvas_factor(
            [
                (
                    float(s.transform["scale"]),
                    float(s.transform.get("residual_rms_px", 0.0)),
                )
                for s in ok_sections
                if s.transform
                and _is_positive_finite(float(s.transform["scale"]))
            ],
            long_side_px=long_side,
            ppm=ppm,
            max_canvas_px=MAX_FLOOR_CANVAS_PX,
            trust_residual_m=CANVAS_TRUST_RESIDUAL_M,
        )
        canvas_w = round(master_w * k)
        canvas_h = round(master_h * k)
        eff_ppm = ppm * k
        scale_factor = 1.0 / eff_ppm

        # Build warp inputs + collect room/door inputs in ONE pass (load each mask
        # once). The per-section rotation is threaded IDENTICALLY into the wall warp
        # AND the room/door inputs, so they all land on the same assembled walls and
        # the build_floor_mesh cross-check holds.
        warp_inputs: list[SectionWarpInput] = []
        room_inputs: list[SectionRoomInput] = []
        door_inputs: list[SectionDoorInput] = []
        for section in ok_sections:
            mask = self._load_section_mask(section)
            if mask is None:
                continue  # non-fatal (mask_missing), like build_floor_mesh
            mask_bin = np.where(mask.copy() > 127, 255, 0).astype(np.uint8)
            mask_h_px, mask_w_px = mask_bin.shape[:2]
            transform = section.transform
            scale_k = float(transform["scale"]) * k
            # Legacy-safe (no key → 0.0); NOT k-scaled (rotation is k-invariant).
            rot = float(transform.get("rotation_rad", 0.0))
            tx_k = float(transform["tx"]) * k
            ty_k = float(transform["ty"]) * k
            warp_inputs.append(
                SectionWarpInput(
                    section_id=section.id,
                    mask=mask_bin,
                    scale=scale_k,
                    rotation_rad=rot,  # walls rotate too (must match rooms/doors)
                    tx=tx_k,
                    ty=ty_k,
                )
            )
            # Rooms from the eager-loaded reconstruction (no extra query).
            # VectorRoom carries a polygon (NO x/y/width/height) — warp its vertices.
            for room in self._read_rooms(section.reconstruction):
                poly = [
                    (float(p["x"]), float(p["y"]))
                    for p in (room.get("polygon") or [])
                    if isinstance(p, dict) and "x" in p and "y" in p
                ]
                if len(poly) < 3:
                    continue
                room_inputs.append(
                    SectionRoomInput(
                        room_id=str(room.get("id", "")),
                        name=str(room.get("name", "")),
                        room_type=str(room.get("room_type", "room")),
                        polygon=poly,
                        mask_w=mask_w_px,  # ← LOADED MASK dims (no shift)
                        mask_h=mask_h_px,
                        scale_k=scale_k,
                        rotation_rad=rot,
                        tx_k=tx_k,
                        ty_k=ty_k,
                        # Transition metadata (D) — carry stair gates + elevator
                        # range from vectorization_data onto the nav node.
                        floor_from=room.get("floor_from"),
                        floor_to=room.get("floor_to"),
                        floors_excluded=room.get("floors_excluded") or [],
                        connects_up=bool(room.get("connects_up", True)),
                        connects_down=bool(room.get("connects_down", True)),
                    )
                )
            # Doors from the same reconstruction (VectorDoor: position + connects).
            for door in self._read_doors(section.reconstruction):
                pos = door.get("position") or {}
                connects = door.get("connects") or []
                door_inputs.append(
                    SectionDoorInput(
                        door_id=str(door.get("id", "")),
                        position=(
                            float(pos.get("x", 0.0)),
                            float(pos.get("y", 0.0)),
                        ),
                        room_id=str(connects[0]) if connects else None,
                        mask_w=mask_w_px,
                        mask_h=mask_h_px,
                        scale_k=scale_k,
                        rotation_rad=rot,
                        tx_k=tx_k,
                        ty_k=ty_k,
                    )
                )

        if not warp_inputs:
            raise FloorSchemaError("Нет масок секций для сборки")

        # Connectors → raster (same as build_floor_mesh).
        connector_rows = await self._connector_repo.list_by_floor(floor_id)
        default_thickness_px = max(
            1, round(DEFAULT_CONNECTOR_THICKNESS_M * ppm * k)
        )
        connectors_raster: list[ConnectorRaster] = []
        for row in connector_rows:
            pts = row.points or []
            if len(pts) < 2:
                continue
            points_px = np.array(
                [[round(px * canvas_w), round(py * canvas_h)] for px, py in pts],
                dtype=np.int32,
            )
            thickness_m = row.thickness_m or DEFAULT_CONNECTOR_THICKNESS_M
            thickness_px = max(1, round(thickness_m * ppm * k))
            connectors_raster.append(
                ConnectorRaster(points_px=points_px, thickness_px=thickness_px)
            )

        # Cutouts → CutoutRaster. SAME k-scaled canvas_w/canvas_h as build_floor_mesh
        # → a cutout erases identical pixels in the nav mask and the 3D mesh.
        cutouts_raster: list[CutoutRaster] = []
        for raw in (floor.nav_cutouts or []):
            pts = raw.get("points", [])
            if len(pts) < 3:
                continue
            points_px = np.array(
                [[round(px * canvas_w), round(py * canvas_h)] for px, py in pts],
                dtype=np.int32,
            )
            cutouts_raster.append(CutoutRaster(points_px=points_px))

        assembled = assemble_floor_mask(
            warp_inputs,
            (canvas_w, canvas_h),
            connectors_raster,
            default_wall_thickness_px=default_thickness_px,
            cutouts=cutouts_raster,
        )

        floor_rooms = transform_rooms_to_floor_canvas(
            room_inputs, canvas_w, canvas_h
        )
        floor_doors = transform_doors_to_floor_canvas(
            door_inputs, canvas_w, canvas_h
        )
        graph = build_floor_graph_from_mask(
            assembled, floor_rooms, floor_doors, canvas_w, canvas_h
        )

        nav_data = serialize_nav_graph(graph, canvas_w, canvas_h, scale_factor)
        with open(self._nav_path(floor_id), "w") as f:
            json.dump(nav_data, f)

        # Persist the assembled wall mask next to the JSON so find_floor_route can
        # LOS-straighten the path later (same array as the 3D mesh —).
        # Wrapped so a write failure never breaks the build.
        try:
            if not cv2.imwrite(self._floor_mask_path(floor_id), assembled):
                logger.warning(
                    "floor mask persist returned False: floor_id=%d", floor_id
                )
        except Exception:
            logger.warning(
                "floor mask persist failed: floor_id=%d", floor_id, exc_info=True
            )

        rooms_count = len(
            [n for n, d in graph.nodes(data=True) if d.get("type") == "room"]
        )
        corridor_nodes_count = len(
            [
                n
                for n, d in graph.nodes(data=True)
                if d.get("type") == "corridor_node"
            ]
        )
        # Connectivity guard (design AC-6): how many rooms actually reach the
        # corridor. A shortfall flags door-less rooms that couldn't attach OR a
        # severed section (floor-2 wings: a data/assembly gap, not a routing bug —
        # design). Additive only — never raises, never blocks the build.
        corridor_comp_nodes: set[str] = set()
        for comp in nx.connected_components(graph):
            if any(graph.nodes[n].get("type") == "corridor_node" for n in comp):
                corridor_comp_nodes |= comp
        rooms_on_corridor = sum(
            1
            for n, d in graph.nodes(data=True)
            if d.get("type") == "room" and n in corridor_comp_nodes
        )
        if rooms_on_corridor < rooms_count:
            logger.warning(
                "build_floor_nav_graph: floor_id=%d only %d/%d rooms reach a corridor",
                floor_id,
                rooms_on_corridor,
                rooms_count,
            )
        logger.info(
            "build_floor_nav_graph: floor_id=%d nodes=%d edges=%d rooms=%d",
            floor_id,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            rooms_count,
        )
        return {
            "floor_id": floor_id,
            "nodes_count": graph.number_of_nodes(),
            "edges_count": graph.number_of_edges(),
            "rooms_count": rooms_count,
            "corridor_nodes_count": corridor_nodes_count,
            "rooms_on_corridor": rooms_on_corridor,
            "canvas_size_px": [canvas_w, canvas_h],
            "scale_factor": round(scale_factor, 6),
        }

    # Route

    async def find_floor_route(
        self, floor_id: int, from_room: str, to_room: str
    ) -> dict:
        """Find the shortest path between two rooms on the assembled floor.

        Args:
            floor_id: floor whose nav graph to query.
            from_room: source room id (bare or ``room_``-prefixed).
            to_room: target room id (bare or ``room_``-prefixed).

        Returns:
            Dict with ``status`` (``found`` / ``no_path``), ``path_3d`` (list of
            ``[x, y, z]``), ``total_distance_m`` and the echoed room ids.

        Raises:
            FloorNavGraphNotFoundError: nav JSON missing (404).
            ValueError: ``from_room`` or ``to_room`` not in the graph (422).
        """
        logger.info(
            "find_floor_route: floor_id=%d, from=%s, to=%s",
            floor_id,
            from_room,
            to_room,
        )
        path = self._nav_path(floor_id)
        if not os.path.exists(path):
            raise FloorNavGraphNotFoundError(floor_id)
        with open(path) as f:
            nav_data = json.load(f)
        graph, metadata = deserialize_nav_graph(nav_data)

        from_node = (
            from_room if from_room.startswith("room_") else f"room_{from_room}"
        )
        to_node = to_room if to_room.startswith("room_") else f"room_{to_room}"
        for node, raw in ((from_node, from_room), (to_node, to_room)):
            if node not in graph.nodes:
                raise ValueError(f"Комната '{raw}' не найдена в графе")

        route = find_route(graph, from_node, to_node)
        if route is None:
            return {
                "floor_id": floor_id,
                "status": "no_path",
                "path_3d": [],
                "total_distance_m": None,
                "from_room_id": from_room,
                "to_room_id": to_room,
            }

        scale_factor = metadata["scale_factor"]
        mask_h = metadata["mask_height"]
        mask_w = metadata["mask_width"]

        # LOS-straighten like the single-plan nav_service. The shape== guard is
        # wall-safety: _line_of_sight treats out-of-bounds pixels as "not wall",
        # so a stale/smaller mask could let los_prune cut THROUGH a wall
        #. On mismatch/missing mask → skip, keeping the
        # simplify_path result.
        try:
            wall_mask = cv2.imread(
                self._floor_mask_path(floor_id), cv2.IMREAD_GRAYSCALE
            )
            if wall_mask is not None and wall_mask.shape == (mask_h, mask_w):
                route["path_coords_2d"] = los_prune(
                    route["path_coords_2d"], wall_mask
                )
        except Exception:
            pass  # LOS optional — fallback on simplify_path

        path_3d = transform_2d_to_3d(
            route["path_coords_2d"], mask_w, mask_h, scale_factor, y_offset=0.1
        )
        dist_m = route["total_distance_px"] * scale_factor
        return {
            "floor_id": floor_id,
            "status": "found",
            "path_3d": path_3d,
            "total_distance_m": round(dist_m, 2),
            "from_room_id": from_room,
            "to_room_id": to_room,
        }

    # Nav graph 2D

    async def get_floor_nav_graph_2d(self, floor_id: int) -> dict:
        """Return the floor nav graph's 2D node/edge data for visualization.

        Mirrors the single-plan (reconstruction) nav-graph response so the same
        frontend renderer (``StepNavGraph.tsx``) works unchanged: ``metadata``
        (``nodes_count``, ``edges_count``, ``room_nodes``, ``door_nodes``,
        ``mask_width``, ``mask_height``) plus ``graph`` as networkx node-link data
        with the ``edges`` key (NOT ``links``), each node carrying ``id`` / ``type``
        / ``pos`` ``[x, y]`` / ``room_name`` / ``room_id`` and each edge ``source`` /
        ``target`` / ``type`` / ``pts``. Pure read + transform — no graph logic.

        Args:
            floor_id: floor whose persisted nav graph to read.

        Returns:
            Dict ``{"metadata": {...}, "graph": {"nodes": [...], "edges": [...]}}``.

        Raises:
            FloorNavGraphNotFoundError: nav JSON missing (404).
        """
        logger.debug("get_floor_nav_graph_2d: floor_id=%d", floor_id)
        path = self._nav_path(floor_id)
        if not os.path.exists(path):
            raise FloorNavGraphNotFoundError(floor_id)
        with open(path) as f:
            nav_data = json.load(f)
        graph, metadata = deserialize_nav_graph(nav_data)

        # Re-emit node-link data with an explicit ``edges`` key so the wire shape
        # is stable regardless of the networkx default. ``pos`` / ``pts`` serialize
        # to JSON arrays either way.
        graph_data = json_graph.node_link_data(graph, edges="edges")
        return {
            "metadata": {
                "nodes_count": metadata.get(
                    "nodes_count", graph.number_of_nodes()
                ),
                "edges_count": metadata.get(
                    "edges_count", graph.number_of_edges()
                ),
                "room_nodes": metadata.get("room_nodes", []),
                "door_nodes": metadata.get("door_nodes", []),
                "mask_width": metadata.get("mask_width"),
                "mask_height": metadata.get("mask_height"),
            },
            "graph": {
                "nodes": graph_data.get("nodes", []),
                "edges": graph_data.get("edges", []),
            },
        }

    # Rooms 3D

    async def get_floor_rooms_3d(self, floor_id: int) -> list[dict]:
        """Return 3D bounding boxes for all room nodes in the floor nav graph.

        Coordinates are in the SAME space as the confirmed floor GLB. Returns an
        empty list (NOT 404) when the graph has not been built yet.

        Args:
            floor_id: floor whose nav graph to read.

        Returns:
            List of dicts matching the ``Room3DApi`` shape: ``id``, ``name``,
            ``room_type``, ``position`` ``[x, y, z]``, ``size`` ``[w, h, d]``,
            ``rotation`` (Y-axis radians; 0 when the section was not rotated).
        """
        logger.debug("get_floor_rooms_3d: floor_id=%d", floor_id)
        path = self._nav_path(floor_id)
        if not os.path.exists(path):
            return []  # graph not built → empty (not 404)
        with open(path) as f:
            nav_data = json.load(f)
        graph, metadata = deserialize_nav_graph(nav_data)

        scale_factor = metadata["scale_factor"]
        mask_h = metadata["mask_height"]
        rooms_3d: list[dict] = []
        for node_id, data in graph.nodes(data=True):
            if data.get("type") != "room":
                continue
            # Prefer the oriented box (true dims + rotation); fall back to the
            # axis-aligned bbox (single-plan / legacy graphs) with no rotation.
            obox = data.get("obox")
            if obox is not None:
                cx, cy, bw, bh, angle = obox
                # Canvas (x, y-down) warp by +φ → three.js Y-rotation of -φ
                # (canvas-y maps to world-z with the same sign; a +Y rotation
                # sends local +x toward -z).
                rot_y = -float(angle)
            elif "bbox" in data:
                rx, ry, bw, bh = data["bbox"]
                cx = rx + bw / 2.0
                cy = ry + bh / 2.0
                rot_y = 0.0
            else:
                continue
            rooms_3d.append(
                {
                    "id": data.get("room_id", str(node_id)),
                    "name": data.get("room_name", ""),
                    "room_type": data.get("room_type", "room"),
                    "position": [
                        round(cx * scale_factor, 4),
                        round(FLOOR_HEIGHT / 2, 4),
                        round((cy - mask_h) * scale_factor, 4),
                    ],
                    "size": [
                        round(bw * scale_factor, 4),
                        round(FLOOR_HEIGHT, 4),
                        round(bh * scale_factor, 4),
                    ],
                    "rotation": round(rot_y, 6),
                }
            )
        return rooms_3d

    # Private helpers (IO / parsing)

    def _nav_path(self, floor_id: int) -> str:
        """Return the nav JSON path for a floor, creating the nav dir if needed."""
        os.makedirs(self._nav_dir, exist_ok=True)
        return os.path.join(self._nav_dir, f"floor_{floor_id}_nav.json")

    def _floor_mask_path(self, floor_id: int) -> str:
        """Return the persisted assembled-mask PNG path, creating the nav dir.

        Mirror of ``_nav_path`` — the mask lives next to the nav JSON so route
        queries can LOS-straighten the path.
        """
        os.makedirs(self._nav_dir, exist_ok=True)
        return os.path.join(self._nav_dir, f"floor_{floor_id}_mask.png")

    @staticmethod
    def _read_rooms(reconstruction) -> list[dict]:  # type: ignore[no-untyped-def]
        """Read the ``rooms`` list from ``vectorization_data`` (read-only).

        ``vectorization_data`` is a nullable JSON string. Returns the rooms list, or
        ``[]`` if the column is empty / unparseable / the key is absent or not a
        list. Never writes ``vectorization_data``.
        """
        raw = reconstruction.vectorization_data if reconstruction else None
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "floor_nav: vectorization_data unparseable for recon %s",
                getattr(reconstruction, "id", "?"),
            )
            return []
        rooms = data.get("rooms", [])
        return rooms if isinstance(rooms, list) else []

    @staticmethod
    def _read_doors(reconstruction) -> list[dict]:  # type: ignore[no-untyped-def]
        """Read the ``doors`` list from ``vectorization_data`` (read-only).

        ``vectorization_data`` is a nullable JSON string. Returns the doors list
        (each ``VectorDoor``: ``id`` / ``position`` ``{x, y}`` / ``width`` /
        ``connects``), or ``[]`` if the column is empty / unparseable / the key is
        absent or not a list. Never writes ``vectorization_data``.
        """
        raw = reconstruction.vectorization_data if reconstruction else None
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "floor_nav: vectorization_data unparseable for recon %s",
                getattr(reconstruction, "id", "?"),
            )
            return []
        doors = data.get("doors", [])
        return doors if isinstance(doors, list) else []

    async def _master_pixel_dims(self, floor) -> tuple[int, int]:  # type: ignore
        """Compute master-pixel canvas dims ``(Wm, Hm)`` from the schema.

        Mirrors ``FloorAssemblyService._master_pixel_dims`` verbatim so the nav
        canvas matches the GLB build: the master canvas IS the cropped master schema
        raster. Rotation by 90/270 swaps W and H; crop multiplies the (rotated) dims.

        Args:
            floor: the Floor ORM row (carries ``schema_image_id`` /
                ``schema_crop_bbox``).

        Returns:
            ``(Wm, Hm)`` master-pixel width and height (ints, >= 1).

        Raises:
            FloorSchemaError: schema image not set or file missing.
            ImageProcessingError: the image file cannot be decoded.
        """
        if not floor.schema_image_id:
            raise FloorSchemaError("Floor has no master schema image")

        image_path = self._find_schema_image(floor.schema_image_id)
        if image_path is None:
            raise FloorSchemaError(
                f"Schema image '{floor.schema_image_id}' not found in storage"
            )
        image = cv2.imread(image_path)
        if image is None:
            raise ImageProcessingError(
                "master_pixel_dims", f"Failed to read schema image: {image_path}"
            )

        h, w = image.shape[:2]

        crop = floor.schema_crop_bbox
        rotation = int(crop.get("rotation", 0)) % 360 if crop else 0

        # 1. Rotation swaps the axes for 90 / 270 (mirrors preprocess_image).
        if rotation in (90, 270):
            w, h = h, w

        # 2. Crop multiplies the (rotated) dims; clamp to >= 1 like preprocess_image.
        if crop:
            crop_w = int(float(crop["width"]) * w)
            crop_h = int(float(crop["height"]) * h)
            w = max(1, min(crop_w, w))
            h = max(1, min(crop_h, h))

        return w, h

    def _find_schema_image(self, image_id: str) -> Optional[str]:
        """Resolve a schema image path across the candidate upload subfolders.

        Mirrors ``FloorAssemblyService._find_schema_image``: try each candidate
        subfolder via ``FileStorage.find_file`` and return the first match, or
        ``None``.
        """
        for subfolder in ("schemas", "plans", "masks", ""):
            try:
                return self._storage.find_file(image_id, subfolder)
            except FileStorageError:
                continue
        return None

    def _load_section_mask(self, section) -> Optional[np.ndarray]:  # type: ignore
        """Load a section's wall mask, or ``None`` if absent (non-fatal).

        Mirrors ``FloorAssemblyService._load_section_mask_for_build``: a missing
        ``mask_file_id`` or missing file is EXPECTED (the section is skipped). An
        undecodable file is an UNEXPECTED ``ImageProcessingError``. Never mutates
        the returned array.

        Raises:
            ImageProcessingError: the mask file exists but cannot be decoded.
        """
        reconstruction = section.reconstruction
        mask_file_id = reconstruction.mask_file_id if reconstruction else None
        if not mask_file_id:
            return None
        try:
            mask_path = self._storage.find_file(mask_file_id, "masks")
        except FileStorageError:
            return None
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise ImageProcessingError(
                "build_floor_nav_graph", f"Failed to load mask: {mask_path}"
            )
        return mask
