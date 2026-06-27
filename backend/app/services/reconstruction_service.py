import json
import logging
from typing import List, Optional

from app.db.models.reconstruction import Reconstruction
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.models.domain import (
    Point2D,
    TextBlock,
    VectorizationResult as DomainVectorizationResult,
    Wall,
    Room,
    Door,
)
from app.models.reconstruction_vectors import VectorizationResult as ReconstructionVectorizationResult
from app.models.floor_assembly import ControlPoint, ControlPointsResponse
from app.processing.contours import extract_elements
from app.processing.pipeline import (
    assign_room_numbers,
    classify_rooms,
    compute_scale_factor,
    compute_wall_thickness,
    door_detect,
    normalize_coords,
    room_detect,
)
from app.core.config import settings
from app.processing.mesh_builder import build_mesh_from_mask
from app.services.file_storage import FileStorage

logger = logging.getLogger(__name__)

# Single source of truth for status display
STATUS_DISPLAY: dict[int, str] = {
    1: "Создано",
    2: "Построение 3D модели...",
    3: "Готово",
    4: "Ошибка",
}


class ReconstructionService:
    def __init__(
        self,
        repo: ReconstructionRepository,
        storage: FileStorage,
        transition_repo: "app.db.repositories.floor_transition_repo.FloorTransitionRepository" = None,
    ) -> None:
        self._repo = repo
        self._storage = storage
        self._transition_repo = transition_repo

    async def build_mesh(
        self,
        plan_file_id: str,
        mask_file_id: str,
        user_id: int,
        text_blocks: Optional[List[TextBlock]] = None,
        image_size_original: Optional[tuple] = None,
        crop_rect: Optional[dict] = None,
        crop_applied: bool = False,
        rotation_angle: int = 0,
        manual_rooms: Optional[List[dict]] = None,
        manual_doors: Optional[List[dict]] = None,
    ) -> Reconstruction:
        """
        Execute full 3D reconstruction pipeline.

        Orchestrates the complete workflow: creates DB record, loads mask
        image, extracts walls and rooms, builds 3D mesh, exports files,
        and updates DB.

        Args:
            plan_file_id: Original plan image file ID
            mask_file_id: Binary mask file ID
            user_id: User ID who initiated the reconstruction
            text_blocks: Optional pre-extracted text blocks from the plan
            image_size_original: Original image size before cropping
                (width, height)
            crop_rect: Crop rectangle coordinates if cropping was applied
            crop_applied: Whether cropping was applied
            rotation_angle: Rotation angle applied to the image

        Returns:
            Reconstruction ORM model with status=3 (ready) or status=4
            (error)

        Raises:
            ValueError: if a manual elevator room has an invalid floor range
                (surfaced as HTTP 400 by the caller). Validated up front so no
                status=4 record is created for bad input.
        """
        # 0. Validate elevator floor fields BEFORE creating any DB record, so
        #    invalid input is rejected (400) instead of silently swallowed by
        #    the build try/except below (which would produce a status=4 row).
        if manual_rooms is not None:
            self._validate_manual_room_floor_fields(manual_rooms)

        # 1. Create reconstruction record with status=2 (processing)
        reconstruction = await self._repo.create_reconstruction(
            plan_file_id, mask_file_id, user_id, status=2
        )
        logger.info(
            "Created reconstruction record: id=%d, plan=%s, mask=%s",
            reconstruction.id,
            plan_file_id,
            mask_file_id,
        )

        try:
            # 2. Load mask from storage
            mask_array = await self._storage.load_mask(mask_file_id)
            h, w = mask_array.shape
            image_size = (w, h)

            # 3. Extract walls via extract_elements pure function
            elements = extract_elements(mask_array)
            wall_elements = [
                e for e in elements if e.element_type not in ("noise",)
            ]

            walls: List[Wall] = []
            for i, elem in enumerate(wall_elements):
                points = [
                    Point2D(
                        x=max(0.0, min(1.0, float(pt[0][0]) / w)),
                        y=max(0.0, min(1.0, float(pt[0][1]) / h)),
                    )
                    for pt in elem.contour
                ]
                if len(points) >= 3:
                    walls.append(
                        Wall(id=f"wall_{i}", points=points, thickness=0.2)
                    )

            # 4. Compute wall thickness
            wall_thickness_px = compute_wall_thickness(mask_array)

            # 5. Detect rooms
            if manual_rooms is not None:
                rooms = []
                for idx, r_dict in enumerate(manual_rooms):
                    rx = float(r_dict.get("x", 0))
                    ry = float(r_dict.get("y", 0))
                    rw = float(r_dict.get("width", 0))
                    rh = float(r_dict.get("height", 0))
                    poly = [
                        Point2D(x=rx, y=ry),
                        Point2D(x=rx + rw, y=ry),
                        Point2D(x=rx + rw, y=ry + rh),
                        Point2D(x=rx, y=ry + rh),
                    ]
                    c_dict = r_dict.get("center", {})
                    if isinstance(c_dict, dict) and "x" in c_dict and "y" in c_dict:
                        cx = float(c_dict["x"])
                        cy = float(c_dict["y"])
                    else:
                        cx = rx + rw / 2
                        cy = ry + rh / 2
                    
                    rooms.append(
                        Room(
                            id=r_dict.get("id", f"manual_room_{idx}"),
                            name=r_dict.get("name", ""),
                            polygon=poly,
                            center=Point2D(x=cx, y=cy),
                            room_type=r_dict.get("room_type", "room"),
                            area_normalized=rw * rh,
                            floor_from=r_dict.get("floor_from"),
                            floor_to=r_dict.get("floor_to"),
                            floors_excluded=r_dict.get("floors_excluded", []),
                            connects_up=r_dict.get("connects_up", True),
                            connects_down=r_dict.get("connects_down", True),
                        )
                    )
            else:
                rooms = room_detect(mask_array)
                rooms = classify_rooms(rooms)

            # 6. Detect doors
            if manual_doors is not None:
                doors = []
                for idx, d_dict in enumerate(manual_doors):
                    dx = float(d_dict.get("x1", 0))
                    dy = float(d_dict.get("y1", 0))
                    conns = []
                    if d_dict.get("room_id"):
                        conns.append(str(d_dict["room_id"]))
                    doors.append(
                        Door(
                            id=d_dict.get("id", f"manual_door_{idx}"),
                            position=Point2D(x=dx, y=dy),
                            width=0.05,
                            connects=conns
                        )
                    )
            else:
                doors = door_detect(mask_array, rooms)

            # 7. Load text blocks from storage if not provided
            if not text_blocks:
                text_blocks = await self._storage.load_text_blocks(
                    mask_file_id
                )

            # 8. Assign room numbers
            if text_blocks:
                rooms = assign_room_numbers(rooms, text_blocks)

            # 9. Normalize coordinates
            walls, rooms, doors = normalize_coords(
                walls, rooms, doors, image_size
            )

            # 10. Compute scale factor
            pixels_per_meter = compute_scale_factor(wall_thickness_px)

            # 11. Assemble VectorizationResult
            orig_size = image_size_original or image_size
            vectorization_result = DomainVectorizationResult(
                walls=walls,
                rooms=rooms,
                doors=doors,
                text_blocks=text_blocks or [],
                image_size_original=orig_size,
                image_size_cropped=image_size,
                crop_rect=crop_rect,
                crop_applied=crop_applied,
                rotation_angle=rotation_angle,
                wall_thickness_px=wall_thickness_px,
                estimated_pixels_per_meter=pixels_per_meter,
                rooms_with_names=sum(1 for r in rooms if r.name),
                corridors_count=sum(
                    1 for r in rooms if r.room_type == "corridor"
                ),
                doors_count=len(doors),
            )

            # 12. Save VectorizationResult to DB
            await self._repo.update_vectorization_data(
                reconstruction.id,
                json.dumps(
                    vectorization_result.model_dump(), ensure_ascii=False
                ),
            )

            # 12.5 Fetch transitions (optional cosmetic markers for inter-floor
            # connectors). This is NOT essential to the floor mesh, so a failure
            # here must never sink the core 3D build — otherwise schema drift in
            # an auxiliary table (e.g. a missing column) would take down the whole
            # pipeline. Degrade gracefully to "no markers" and keep building.
            transition_geoms = []
            if self._transition_repo:
                rid = reconstruction.id
                try:
                    transitions = await self._transition_repo.get_by_reconstruction(rid)
                    for t in transitions:
                        if t.from_reconstruction_id == rid and t.from_geometry:
                            transition_geoms.append(t.from_geometry)
                        if t.to_reconstruction_id == rid and t.to_geometry:
                            transition_geoms.append(t.to_geometry)
                except Exception as exc:
                    logger.warning(
                        "Skipping transition markers for reconstruction %d: %s",
                        rid,
                        exc,
                    )

            # 13. Build 3D mesh from binary mask
            mesh = build_mesh_from_mask(
                mask_array,
                floor_height=settings.DEFAULT_FLOOR_HEIGHT,
                pixels_per_meter=pixels_per_meter,
                vr=vectorization_result,
                transitions=transition_geoms if transition_geoms else None,
            )

            # 14. Export mesh
            obj_path, glb_path = await self._storage.save_mesh_files(
                reconstruction.id, mesh
            )
            logger.info("Mesh exported: obj=%s, glb=%s", obj_path, glb_path)

            # 15. Update DB with mesh paths
            reconstruction = await self._repo.update_mesh(
                reconstruction.id, obj_path, glb_path, status=3
            )

        except Exception as e:
            logger.error(
                "Error building mesh for reconstruction %d: %s",
                reconstruction.id,
                e,
                exc_info=True,
            )
            # Surface the real cause (type + message) so failures are diagnosable
            # instead of a generic string. Truncated to stay bounded.
            safe_msg = f"Ошибка построения модели: {type(e).__name__}: {str(e)[:300]}"
            reconstruction = await self._repo.update_mesh(
                reconstruction.id, None, None, status=4, error_message=safe_msg
            )

        return reconstruction

    async def get_vectorization_data(
        self, reconstruction_id: int
    ) -> Optional[ReconstructionVectorizationResult]:
        """
        Retrieve vectorization data from database.

        Args:
            reconstruction_id: Reconstruction ID

        Returns:
            VectorizationResult object or None if not found or invalid
        """
        reconstruction = await self._repo.get_by_id(reconstruction_id)
        if not reconstruction or not reconstruction.vectorization_data:
            return None
        try:
            data = json.loads(reconstruction.vectorization_data)
            return ReconstructionVectorizationResult(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                "Failed to parse vectorization data for %d: %s",
                reconstruction_id,
                e,
                exc_info=True,
            )
            return None

    async def update_vectorization_data(
        self, reconstruction_id: int, data: ReconstructionVectorizationResult
    ) -> bool:
        """
        Update vectorization data in database.

        Args:
            reconstruction_id: Reconstruction ID
            data: VectorizationResult object to save

        Returns:
            True if successful, False if reconstruction not found
        """
        existing = await self.get_vectorization_data(reconstruction_id)
        if existing is not None:
            merged = existing.model_copy(
                update={
                    "rooms": data.rooms,
                    "doors": data.doors,
                    "rotation_angle": data.rotation_angle,
                    "crop_rect": data.crop_rect,
                }
            )
            payload = merged.model_dump()
        else:
            payload = data.model_dump()

        json_str = json.dumps(payload, ensure_ascii=False)
        result = await self._repo.update_vectorization_data(
            reconstruction_id, json_str
        )
        return result is not None

    async def get_reconstruction(
        self, reconstruction_id: int
    ) -> Optional[Reconstruction]:
        """
        Get reconstruction by ID.

        Args:
            reconstruction_id: Reconstruction ID

        Returns:
            Reconstruction ORM model or None if not found
        """
        return await self._repo.get_by_id(reconstruction_id)

    async def get_saved_reconstructions(self) -> list[Reconstruction]:
        """
        List all saved reconstructions.

        Returns:
            List of Reconstruction ORM models where name is not NULL
        """
        return await self._repo.get_saved()

    async def save_reconstruction(
        self, reconstruction_id: int, name: str, building_id: Optional[str] = None, floor_number: Optional[int] = None
    ) -> Optional[Reconstruction]:
        """
        Save reconstruction with a name, building_id, and floor_number.

        Args:
            reconstruction_id: Reconstruction ID
            name: Name to assign to the reconstruction
            building_id: Building identifier (e.g., "A", "B", "C")
            floor_number: Floor number

        Returns:
            Updated Reconstruction ORM model or None if not found
        """
        return await self._repo.update_reconstruction(reconstruction_id, name, building_id, floor_number)

    async def delete_reconstruction(self, reconstruction_id: int) -> bool:
        """
        Delete reconstruction by ID.

        Args:
            reconstruction_id: Reconstruction ID

        Returns:
            True if deleted, False if not found
        """
        return await self._repo.delete(reconstruction_id)

    @staticmethod
    def get_status_display(status: int) -> str:
        """
        Get human-readable status text.

        Args:
            status: Status code (1=created, 2=processing, 3=ready, 4=error)

        Returns:
            Human-readable status string in Russian
        """
        return STATUS_DISPLAY.get(status, "Неизвестно")

    @staticmethod
    def get_room_labels(vr: Optional[DomainVectorizationResult]) -> list[dict]:
        """
        Format room labels for API response.

        Args:
            vr: VectorizationResult containing room data

        Returns:
            List of room label dictionaries with id, name, type, center,
            and color
        """
        if not vr or not vr.rooms:
            return []
        colors = {
            "classroom": "#f5c542", "corridor": "#4287f5",
            "staircase": "#2E7D32", "elevator": "#6A1B9A",
            "toilet": "#42f5c8", "other": "#c8c8c8", "room": "#c8c8c8",
        }
        return [
            {
                "id": room.id,
                "name": room.name,
                "room_type": room.room_type,
                "center_x": room.center.x,
                "center_y": room.center.y,
                "color": colors.get(room.room_type, "#c8c8c8"),
            }
            for room in vr.rooms
        ]

    @staticmethod
    def _validate_manual_room_floor_fields(manual_rooms: List[dict]) -> None:
        """Validate elevator floor-link fields on manual rooms (raises 400).

        Reuses the ``Room`` model validator: builds a minimal Room per entry
        that carries floor fields, so an invalid range raises ``ValueError``
        before any DB record is created. Non-elevator rooms (no floor fields)
        pass through untouched.

        Args:
            manual_rooms: Raw room dicts from the request.

        Raises:
            ValueError: if any elevator floor range is invalid.
        """
        for r_dict in manual_rooms:
            ff = r_dict.get("floor_from")
            ft = r_dict.get("floor_to")
            fx = r_dict.get("floors_excluded", [])
            if ff is None and ft is None:
                continue
            # Constructing Room fires the @model_validator floor-range check.
            Room(
                id="_validate",
                polygon=[Point2D(x=0.0, y=0.0)],
                center=Point2D(x=0.0, y=0.0),
                room_type=r_dict.get("room_type", "elevator"),
                floor_from=ff,
                floor_to=ft,
                floors_excluded=fx,
            )

    def build_mesh_url(self, reconstruction: Reconstruction) -> Optional[str]:
        """
        Build URL for GLB mesh file.

        Args:
            reconstruction: Reconstruction ORM model

        Returns:
            URL string or None if mesh file doesn't exist
        """
        if reconstruction.mesh_file_id_glb:
            model_id = reconstruction.id
            return f"/api/v1/uploads/models/reconstruction_{model_id}.glb"
        return None

    # extensions

    async def patch_floor(
        self, reconstruction_id: int, floor_id: int
    ) -> Optional[Reconstruction]:
        """PATCH: early binding of a reconstruction to a floor.

        Used on wizard StepUpload when admin picks building+floor.
        Validates floor exists (404 if not via caller).

        Args:
            reconstruction_id: Reconstruction to update.
            floor_id: Floor to bind to.

        Returns:
            Updated Reconstruction with relations, or None if not found.
        """
        logger.info(
            "patch_floor: reconstruction_id=%d, floor_id=%d",
            reconstruction_id,
            floor_id,
        )
        result = await self._repo.update_floor_id(reconstruction_id, floor_id)
        if result is None:
            return None
        return await self._repo.get_with_relations(reconstruction_id)

    async def save(
        self, reconstruction_id: int, name: str, floor_id: int
    ) -> Optional[Reconstruction]:
        """Save reconstruction with name + floor_id (replaces old building_id+floor_number).

        Validates floor exists; caller raises 404 if floor absent.

        Args:
            reconstruction_id: Reconstruction to update.
            name: Human-readable name for the reconstruction.
            floor_id: Floor FK.

        Returns:
            Updated Reconstruction with full relations, or None if not found.
        """
        logger.info(
            "save: reconstruction_id=%d, name=%s, floor_id=%d",
            reconstruction_id,
            name,
            floor_id,
        )
        result = await self._repo.update_reconstruction(
            reconstruction_id, name=name, floor_id=floor_id
        )
        if result is None:
            return None
        return await self._repo.get_with_relations(reconstruction_id)

    async def list(
        self,
        floor_id: Optional[int] = None,
        status: Optional[int] = None,
        unbound: bool = False,
        search: Optional[str] = None,
    ) -> list[Reconstruction]:
        """List saved reconstructions with optional filters.

        Args:
            floor_id: Filter by floor (for floor editor).
            status: Filter by status (e.g. 3=Done for gallery).
            unbound: If True, only reconstructions not linked to any section.
            search: Substring match on name.

        Returns:
            List of Reconstruction ORM models.
        """
        logger.debug(
            "list: floor_id=%s, status=%s, unbound=%s, search=%s",
            floor_id,
            status,
            unbound,
            search,
        )
        return await self._repo.get_saved(
            floor_id=floor_id,
            status=status,
            unbound=unbound,
            search=search,
        )

    async def get_by_id(self, reconstruction_id: int) -> Optional[Reconstruction]:
        """Get reconstruction by ID with full relations (floor→building + section).

        Args:
            reconstruction_id: Reconstruction ID.

        Returns:
            Reconstruction with relations or None if not found.
        """
        logger.debug("get_by_id (with relations): reconstruction_id=%d", reconstruction_id)
        return await self._repo.get_with_relations(reconstruction_id)

    #section-local control points

    async def get_control_points(
        self, reconstruction_id: int
    ) -> Optional[ControlPointsResponse]:
        """Read section-local control points for a reconstruction.

        Echoes ``image_size_cropped`` from ``vectorization_data`` (read-only;
        never writes it) so the editor can map normalised points to pixels.

        Args:
            reconstruction_id: Reconstruction ID.

        Returns:
            ControlPointsResponse, or None if the reconstruction is not found.
        """
        logger.debug("get_control_points: reconstruction_id=%d", reconstruction_id)
        reconstruction = await self._repo.get_by_id(reconstruction_id)
        if reconstruction is None:
            return None
        return self._build_control_points_response(reconstruction)

    async def save_control_points(
        self, reconstruction_id: int, points: List[ControlPoint]
    ) -> Optional[ControlPointsResponse]:
        """Replace section-local control points for a reconstruction.

        Coord range, list cap and id uniqueness are enforced by
        ``SaveControlPointsRequest`` at the request boundary, so this
        method only persists the points and echoes the GET shape.

        Args:
            reconstruction_id: Reconstruction ID.
            points: Validated control points to store (may be empty).

        Returns:
            ControlPointsResponse, or None if the reconstruction is not found.
        """
        logger.debug(
            "save_control_points: reconstruction_id=%d, count=%d",
            reconstruction_id,
            len(points),
        )
        reconstruction = await self._repo.update_control_points(
            reconstruction_id, [p.model_dump() for p in points]
        )
        if reconstruction is None:
            return None
        return self._build_control_points_response(reconstruction)

    @staticmethod
    def _build_control_points_response(
        reconstruction: Reconstruction,
    ) -> ControlPointsResponse:
        """Assemble a ControlPointsResponse from a Reconstruction row.

        Parses ``vectorization_data`` read-only to echo ``image_size_cropped``
        (None if absent or unparseable).
        """
        image_size_cropped = None
        if reconstruction.vectorization_data:
            try:
                data = json.loads(reconstruction.vectorization_data)
                image_size_cropped = data.get("image_size_cropped")
            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse vectorization_data for %d: %s",
                    reconstruction.id,
                    e,
                )
        return ControlPointsResponse(
            reconstruction_id=reconstruction.id,
            image_size_cropped=image_size_cropped,
            points=reconstruction.control_points or [],
        )
