import glob
import json
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.repositories.floor_transition_repo import FloorTransitionRepository
    from app.db.repositories.reconstruction_repo import ReconstructionRepository
    from app.db.repositories.transition_repo import TransitionRepository

import cv2
import numpy as np

from app.processing.nav_graph import (
    build_skeleton,
    build_topology_graph,
    deserialize_nav_graph,
    extract_corridor_mask,
    find_route,
    integrate_semantics,
    los_prune,
    prune_dendrites,
    serialize_nav_graph,
    transform_2d_to_3d,
    merge_floor_graphs,
    find_multifloor_route_in_graph,
    FloorGraphData,
    FLOOR_HEIGHT_METERS,
)
from app.processing.pipeline import compute_scale_factor, compute_wall_thickness
from app.models.floor_transition import (
    MultifloorRouteResponse,
    PathSegment3D,
    TransitionUsed3D,
    Room3DInfo,
)
from app.models.transition import (
    MultiPlanRouteRequest,
    MultiPlanRouteResponse,
    RouteSegment,
)
from app.core.exceptions import NavGraphNotFoundError

logger = logging.getLogger(__name__)


class NavService:
    def __init__(self, upload_dir: str) -> None:
        self._upload_dir = upload_dir
        self._masks_dir = os.path.join(upload_dir, "masks")

    def _find_mask_file(self, mask_file_id: str) -> str:
        pattern = os.path.join(self._masks_dir, f"{mask_file_id}.*")
        files = [
            f for f in glob.glob(pattern)
            if os.path.basename(f).startswith(mask_file_id + '.')
        ]
        if not files:
            raise FileNotFoundError(f"Mask file not found: {mask_file_id}")
        return files[0]

    async def build_graph(
        self,
        mask_file_id: str,
        rooms: list[dict],
        doors: list[dict],
        scale_factor: float = 0.02,
    ) -> dict:
        """Полный пайплайн генерации навигационного графа."""
        mask_path = self._find_mask_file(mask_file_id)
        wall_mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if wall_mask is None:
            raise ValueError(f"Cannot read mask: {mask_path}")
        h, w = wall_mask.shape[:2]

        # Compute scale_factor from the mask itself so it matches mesh_builder.py
        wall_thickness_px = compute_wall_thickness(wall_mask)
        scale_factor = 1.0 / compute_scale_factor(wall_thickness_px)

        corridor_mask = extract_corridor_mask(wall_mask, rooms, w, h, wall_thickness_px)
        skeleton = build_skeleton(corridor_mask)
        G = build_topology_graph(skeleton)
        G = prune_dendrites(G, min_branch_length=20.0)
        G = integrate_semantics(G, rooms, doors, w, h)

        nav_data = serialize_nav_graph(G, w, h, scale_factor)

        nav_path = os.path.splitext(mask_path)[0] + '_nav.json'
        with open(nav_path, 'w') as f:
            json.dump(nav_data, f)

        # Debug images (6 шт) — для визуальной проверки
        debug_dir = os.path.dirname(mask_path)
        prefix = mask_file_id

        cv2.imwrite(f'{debug_dir}/{prefix}_1_free.png', cv2.bitwise_not(wall_mask))

        dilate_px = max(1, min(int(wall_thickness_px), 30))
        dilate_kernel = np.ones((dilate_px, dilate_px), np.uint8)
        dilated = cv2.dilate(wall_mask, dilate_kernel, iterations=1)
        cv2.imwrite(f'{debug_dir}/{prefix}_2_dilated_walls.png', dilated)
        cv2.imwrite(f'{debug_dir}/{prefix}_3_closed_free.png', cv2.bitwise_not(dilated))
        cv2.imwrite(f'{debug_dir}/{prefix}_4_corridor.png', corridor_mask)
        cv2.imwrite(f'{debug_dir}/{prefix}_5_skeleton.png', skeleton)

        overlay = cv2.cvtColor(wall_mask, cv2.COLOR_GRAY2BGR)
        overlay[corridor_mask > 0] = [180, 80, 0]
        overlay[skeleton > 0] = [0, 255, 255]
        for node_id, data in G.nodes(data=True):
            pos = data.get('pos', (0, 0))
            x, y = int(pos[0]), int(pos[1])
            if 0 <= x < w and 0 <= y < h:
                color = {
                    'room': (0, 0, 255),
                    'door': (0, 255, 0),
                    'corridor_entry': (255, 128, 0),
                    'corridor_node': (128, 128, 128),
                }.get(data.get('type', ''), (200, 200, 200))
                radius = 6 if data.get('type') in ('room', 'door') else 3
                cv2.circle(overlay, (x, y), radius, color, -1)
        cv2.imwrite(f'{debug_dir}/{prefix}_6_overlay.png', overlay)

        logger.info("NavService.build_graph: saved %s, debug images → %s", nav_path, debug_dir)
        return nav_data["metadata"]

    def load_graph(self, mask_file_id: str) -> dict:
        """Загружает сохранённый граф с диска."""
        nav_path = os.path.join(self._masks_dir, f"{mask_file_id}_nav.json")
        if not os.path.exists(nav_path):
            raise FileNotFoundError(f"Nav graph not found: {nav_path}")
        with open(nav_path, 'r') as f:
            return json.load(f)

    def get_rooms_3d(self, graph_id: str) -> list[dict]:
        """Возвращает 3D-позиции всех комнат графа в том же формате,
        что и `from_room_3d`/`to_room_3d` в find_route. Используется фронтом
        для overlay-боксов в MeshViewer — гарантирует точное совпадение
        с маркерами маршрута."""
        nav_data = self.load_graph(graph_id)
        G, metadata = deserialize_nav_graph(nav_data)
        scale_factor = metadata.get('scale_factor', 0.02)
        mask_height = metadata.get('mask_height', 500)

        rooms_3d: list[dict] = []
        for node_id, data in G.nodes(data=True):
            if data.get('type') != 'room' or 'bbox' not in data:
                continue
            rx, ry, rw, rh = data['bbox']
            width_3d = rw * scale_factor
            depth_3d = rh * scale_factor
            cx = rx + rw / 2.0
            cy = ry + rh / 2.0
            center_x_3d = cx * scale_factor
            center_z_3d = (cy - mask_height) * scale_factor
            rooms_3d.append({
                "id": data.get('room_id', node_id),
                "name": data.get('room_name', ''),
                "room_type": data.get('room_type', 'room'),
                "position": [round(center_x_3d, 4), 1.5, round(center_z_3d, 4)],
                "size": [round(width_3d, 4), 3.0, round(depth_3d, 4)],
            })
        return rooms_3d

    async def find_route(
        self,
        graph_id: str,
        from_room_id: str,
        to_room_id: str,
    ) -> dict:
        """Загружает граф, ищет маршрут A*, трансформирует координаты в 3D."""
        try:
            nav_data = self.load_graph(graph_id)
        except FileNotFoundError:
            return {"status": "error", "message": "Graph not found"}

        G, metadata = deserialize_nav_graph(nav_data)

        route = find_route(G, from_room_id, to_room_id)
        if not route:
            return {
                "status": "no_path",
                "message": f"No path from {from_room_id} to {to_room_id}",
            }

        scale_factor = metadata.get('scale_factor', 0.02)
        mask_width = metadata.get('mask_width', 1000)
        mask_height = metadata.get('mask_height', 500)

        # LOS pruning — remove zigzags where straight line is clear of walls
        try:
            mask_path = self._find_mask_file(graph_id)
            wall_mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
            if wall_mask is not None:
                route['path_coords_2d'] = los_prune(route['path_coords_2d'], wall_mask)
        except Exception:
            pass  # LOS is optional — fall back to simplified path

        coords_3d = transform_2d_to_3d(
            route['path_coords_2d'],
            mask_width, mask_height,
            scale_factor,
            y_offset=0.1,
        )

        distance_meters = route['total_distance_px'] * scale_factor
        estimated_time = distance_meters / 1.2

        from_node_key = from_room_id if from_room_id.startswith("room_") else f"room_{from_room_id}"
        to_node_key = to_room_id if to_room_id.startswith("room_") else f"room_{to_room_id}"
        from_name = G.nodes.get(from_node_key, {}).get('room_name', from_room_id)
        to_name = G.nodes.get(to_node_key, {}).get('room_name', to_room_id)

        # Extract room bounding boxes and convert to 3D sizes and positions
        from_room_3d = None
        to_room_3d = None

        def extract_room_3d(node_key):
            node_data = G.nodes.get(node_key, {})
            if 'bbox' in node_data:
                rx, ry, rw, rh = node_data['bbox']
                # 2D to 3D transformation logic (same as transform_2d_to_3d)
                # Box size in 3D: width = rw * scale, depth (z) = rh * scale
                width_3d = rw * scale_factor
                depth_3d = rh * scale_factor
                # Box center in 3D:
                cx = rx + rw / 2.0
                cy = ry + rh / 2.0

                # We need to map pixel coordinates exactly as transform_2d_to_3d does.
                center_x_3d = cx * scale_factor
                center_z_3d = (cy - mask_height) * scale_factor
                return {
                    "position": [round(center_x_3d, 4), 1.5, round(center_z_3d, 4)],
                    "size": [round(width_3d, 4), 3.0, round(depth_3d, 4)]
                }
            return None

        from_room_3d = extract_room_3d(from_node_key)
        to_room_3d = extract_room_3d(to_node_key)

        return {
            "status": "success",
            "from_room": from_name or from_room_id,
            "to_room": to_name or to_room_id,
            "total_distance_px": round(route['total_distance_px'], 1),
            "total_distance_meters": round(distance_meters, 1),
            "estimated_time_seconds": round(estimated_time),
            "coordinates": coords_3d,
            "path_nodes_count": len(route['path_nodes']),
            "from_room_3d": from_room_3d,
            "to_room_3d": to_room_3d,
        }

    async def find_multifloor_route(
        self,
        building_id: str,
        from_reconstruction_id: int,
        from_room_id: str,
        to_reconstruction_id: int,
        to_room_id: str,
        ft_repo: "FloorTransitionRepository",
        recon_repo: "ReconstructionRepository",
    ) -> MultifloorRouteResponse:
        """
        Find a route between rooms, possibly across multiple floors.

        Delegates to single-floor find_route() when from == to reconstruction.
        Raises NavGraphNotFoundError if a required nav graph file is missing.
        Returns MultifloorRouteResponse.
        """
        # Same floor — delegate to existing single-floor logic
        if from_reconstruction_id == to_reconstruction_id:
            recon = await recon_repo.get_by_id(from_reconstruction_id)
            if recon is None:
                return MultifloorRouteResponse(
                    status="no_path",
                    message=f"Reconstruction {from_reconstruction_id} not found",
                )
            logger.info(
                "find_multifloor_route same-floor: recon_id=%s, mask_file_id=%s, "
                "from_room=%s, to_room=%s",
                from_reconstruction_id, recon.mask_file_id, from_room_id, to_room_id,
            )
            result = await self.find_route(
                graph_id=recon.mask_file_id,
                from_room_id=from_room_id,
                to_room_id=to_room_id,
            )
            if result.get("status") != "success":
                return MultifloorRouteResponse(
                    status=result.get("status", "no_path"),
                    message=result.get("message"),
                )
            floor_number = recon.floor.number if recon.floor else 0
            y_offset = floor_number * FLOOR_HEIGHT_METERS + 0.1
            coords_3d = result.get("coordinates", [])
            segment = PathSegment3D(
                reconstruction_id=from_reconstruction_id,
                floor_number=floor_number,
                floor_name=recon.name or str(from_reconstruction_id),
                coordinates_3d=coords_3d,
            )
            from_room_3d = None
            to_room_3d = None
            if result.get("from_room_3d"):
                r = result["from_room_3d"]
                from_room_3d = Room3DInfo(position=r["position"], size=r["size"])
            if result.get("to_room_3d"):
                r = result["to_room_3d"]
                to_room_3d = Room3DInfo(position=r["position"], size=r["size"])
            return MultifloorRouteResponse(
                status="success",
                total_distance_meters=result.get("total_distance_meters"),
                estimated_time_seconds=result.get("estimated_time_seconds"),
                path_segments=[segment],
                transitions_used=[],
                from_room_3d=from_room_3d,
                to_room_3d=to_room_3d,
            )

        # Multi-floor path
        transitions = await ft_repo.get_by_building(building_id)
        transition_groups = []
        for t in transitions:
            # Centroid extraction for from_geometry
            if t.from_geometry and isinstance(t.from_geometry, list) and len(t.from_geometry) > 0:
                fx = sum(pt[0] for pt in t.from_geometry) / len(t.from_geometry)
                fy = sum(pt[1] for pt in t.from_geometry) / len(t.from_geometry)
            else:
                fx = t.from_x
                fy = t.from_y
                
            # Centroid extraction for to_geometry
            if t.to_geometry and isinstance(t.to_geometry, list) and len(t.to_geometry) > 0:
                tx = sum(pt[0] for pt in t.to_geometry) / len(t.to_geometry)
                ty = sum(pt[1] for pt in t.to_geometry) / len(t.to_geometry)
            else:
                tx = t.to_x
                ty = t.to_y
                
            transition_groups.append({
                "id": t.id,
                "name": t.name,
                "type": "floor_transition",
                "points": [
                    {
                        "id": f"from_{t.id}",
                        "reconstruction_id": t.from_reconstruction_id,
                        "x": fx,
                        "y": fy,
                    },
                    {
                        "id": f"to_{t.id}",
                        "reconstruction_id": t.to_reconstruction_id,
                        "x": tx,
                        "y": ty,
                    },
                ]
            })

        # Collect all unique reconstruction ids to load
        recon_ids: set[int] = {from_reconstruction_id, to_reconstruction_id}
        for t in transitions:
            recon_ids.add(t.from_reconstruction_id)
            recon_ids.add(t.to_reconstruction_id)

        floor_data_list: list[FloorGraphData] = []
        for recon_id in recon_ids:
            recon = await recon_repo.get_by_id(recon_id)
            if recon is None or not recon.mask_file_id:
                continue
            try:
                nav_data = self.load_graph(recon.mask_file_id)
            except FileNotFoundError:
                if recon_id in (from_reconstruction_id, to_reconstruction_id):
                    raise NavGraphNotFoundError(recon_id)
                continue
            G, metadata = deserialize_nav_graph(nav_data)
            floor_data_list.append(FloorGraphData(
                graph=G,
                metadata=metadata,
                reconstruction_id=recon_id,
                floor_number=recon.floor.number if recon.floor else 0,
                floor_name=recon.name or str(recon_id),
            ))

        merged_graph, floor_data_by_recon_id = merge_floor_graphs(
            floor_data_list, transition_groups
        )

        route = find_multifloor_route_in_graph(
            merged_graph,
            floor_data_by_recon_id,
            from_reconstruction_id,
            from_room_id,
            to_reconstruction_id,
            to_room_id,
        )

        if route is None:
            return MultifloorRouteResponse(
                status="no_path",
                message="No path found between rooms",
            )

        # Build 3D path segments
        path_segments_3d: list[PathSegment3D] = []
        for seg in route["path_segments"]:
            fd = floor_data_by_recon_id.get(seg["reconstruction_id"])
            if fd is None:
                continue
            y_offset = fd.floor_number * FLOOR_HEIGHT_METERS + 0.1
            coords_3d = transform_2d_to_3d(
                seg["coords_2d"],
                fd.metadata.get("mask_width", 1000),
                fd.metadata.get("mask_height", 500),
                fd.metadata.get("scale_factor", 0.02),
                y_offset=y_offset,
            )
            path_segments_3d.append(PathSegment3D(
                reconstruction_id=seg["reconstruction_id"],
                floor_number=seg["floor_number"],
                floor_name=seg["floor_name"],
                coordinates_3d=coords_3d,
            ))

        # Build 3D transitions
        transitions_used_3d: list[TransitionUsed3D] = []
        for tu in route["transitions_used"]:
            from_fd = floor_data_by_recon_id.get(tu.get("from_recon_id"))
            to_fd = floor_data_by_recon_id.get(tu.get("to_recon_id"))
            if from_fd is None or to_fd is None:
                continue
            from_y = from_fd.floor_number * FLOOR_HEIGHT_METERS + 0.1
            to_y = to_fd.floor_number * FLOOR_HEIGHT_METERS + 0.1
            from_px, from_py = tu["from_px"]
            to_px, to_py = tu["to_px"]
            from_3d = transform_2d_to_3d(
                [(from_px, from_py)],
                from_fd.metadata.get("mask_width", 1000),
                from_fd.metadata.get("mask_height", 500),
                from_fd.metadata.get("scale_factor", 0.02),
                y_offset=from_y,
            )[0]
            to_3d = transform_2d_to_3d(
                [(to_px, to_py)],
                to_fd.metadata.get("mask_width", 1000),
                to_fd.metadata.get("mask_height", 500),
                to_fd.metadata.get("scale_factor", 0.02),
                y_offset=to_y,
            )[0]
            transitions_used_3d.append(TransitionUsed3D(
                name=tu["name"],
                from_3d=from_3d,
                to_3d=to_3d,
            ))

        total_distance_px = route.get("total_distance_px", 0.0)
        # Use scale_factor from the from-floor for distance estimation
        from_fd = floor_data_by_recon_id.get(from_reconstruction_id)
        scale = from_fd.metadata.get("scale_factor", 0.02) if from_fd else 0.02
        distance_meters = round(total_distance_px * scale, 1)
        estimated_time = round(distance_meters / 1.2)

        return MultifloorRouteResponse(
            status="success",
            total_distance_meters=distance_meters,
            estimated_time_seconds=estimated_time,
            path_segments=path_segments_3d,
            transitions_used=transitions_used_3d,
        )

    async def find_multi_plan_route(
        self,
        request: MultiPlanRouteRequest,
        transition_repo: "TransitionRepository",
        recon_repo: "ReconstructionRepository",
    ) -> MultiPlanRouteResponse:
        from_recon = await recon_repo.get_by_id(request.from_reconstruction_id)
        if from_recon is None:
            return MultiPlanRouteResponse(status="error", message="From reconstruction not found")

        # Same floor — delegate to single-floor logic
        if request.from_reconstruction_id == request.to_reconstruction_id:
            result = await self.find_route(
                graph_id=from_recon.mask_file_id,
                from_room_id=request.from_room_id,
                to_room_id=request.to_room_id,
            )
            if result.get("status") != "success":
                return MultiPlanRouteResponse(status=result.get("status", "no_path"), message=result.get("message"))
            
            floor_name = from_recon.name or str(from_recon.id)
            segment = RouteSegment(
                reconstruction_id=from_recon.id,
                reconstruction_name=floor_name,
                floor_label=floor_name,
                coordinates=result.get("coordinates", []),
            )
            return MultiPlanRouteResponse(
                status="success",
                total_distance_meters=result.get("total_distance_meters"),
                segments=[segment]
            )

        # Multi-floor path using new Transition models
        building_id = from_recon.building_id
        if not building_id:
            return MultiPlanRouteResponse(status="error", message="From reconstruction has no building_id")

        groups = await transition_repo.list_groups_by_building(building_id)
        transition_groups = []
        for g in groups:
            points = []
            for p in g.points:
                # If geometry exists, calculate centroid. Otherwise use position_x, position_y
                if getattr(p, "geometry", None):
                    geom = p.geometry
                    xs = [pt[0] for pt in geom]
                    ys = [pt[1] for pt in geom]
                    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                else:
                    cx, cy = p.position_x, p.position_y
                points.append({
                    "id": p.id,
                    "reconstruction_id": p.reconstruction_id,
                    "x": cx,
                    "y": cy,
                })
            transition_groups.append({
                "id": g.id,
                "name": g.label or f"Transition {g.id}",
                "type": getattr(g, "type", "passage"),
                "points": points,
            })

        recon_ids: set[int] = {request.from_reconstruction_id, request.to_reconstruction_id}
        for tg in transition_groups:
            for p in tg["points"]:
                recon_ids.add(p["reconstruction_id"])

        floor_data_list: list[FloorGraphData] = []
        for recon_id in recon_ids:
            recon = await recon_repo.get_by_id(recon_id)
            if recon is None or not recon.mask_file_id:
                continue
            try:
                nav_data = self.load_graph(recon.mask_file_id)
            except FileNotFoundError:
                if recon_id in (request.from_reconstruction_id, request.to_reconstruction_id):
                    raise NavGraphNotFoundError(recon_id)
                continue
            G, metadata = deserialize_nav_graph(nav_data)
            floor_data_list.append(FloorGraphData(
                graph=G,
                metadata=metadata,
                reconstruction_id=recon_id,
                floor_number=recon.floor.number if recon.floor else 0,
                floor_name=recon.name or str(recon_id),
            ))

        merged_graph, floor_data_by_recon_id = merge_floor_graphs(
            floor_data_list, transition_groups
        )

        route = find_multifloor_route_in_graph(
            merged_graph,
            floor_data_by_recon_id,
            request.from_reconstruction_id,
            request.from_room_id,
            request.to_reconstruction_id,
            request.to_room_id,
        )

        if route is None:
            return MultiPlanRouteResponse(
                status="no_path",
                message="No path found between rooms",
            )

        # Build path segments (using the existing PathSegment3D and transforming it to RouteSegment)
        path_segments: list[RouteSegment] = []
        for seg in route["path_segments"]:
            fd = floor_data_by_recon_id.get(seg["reconstruction_id"])
            if fd is None:
                continue
            y_offset = fd.floor_number * FLOOR_HEIGHT_METERS + 0.1
            coords_3d = transform_2d_to_3d(
                seg["coords_2d"],
                fd.metadata.get("mask_width", 1000),
                fd.metadata.get("mask_height", 500),
                fd.metadata.get("scale_factor", 0.02),
                y_offset=y_offset,
            )
            path_segments.append(RouteSegment(
                reconstruction_id=seg["reconstruction_id"],
                reconstruction_name=seg["floor_name"],
                floor_label=seg["floor_name"],
                coordinates=coords_3d,
            ))

        total_distance_px = route.get("total_distance_px", 0.0)
        from_fd = floor_data_by_recon_id.get(request.from_reconstruction_id)
        scale = from_fd.metadata.get("scale_factor", 0.02) if from_fd else 0.02
        distance_meters = round(total_distance_px * scale, 1)

        return MultiPlanRouteResponse(
            status="success",
            total_distance_meters=distance_meters,
            segments=path_segments,
        )

    async def build_graph_endpoint(self, request) -> dict:
        """Endpoint wrapper for build_graph. Returns BuildNavGraphResponse."""
        metadata = await self.build_graph(
            mask_file_id=request.mask_file_id,
            rooms=request.rooms,
            doors=request.doors,
            scale_factor=request.scale_factor,
        )
        from app.models.reconstruction import BuildNavGraphResponse
        return BuildNavGraphResponse(
            graph_id=request.mask_file_id,
            **metadata,
        )
