"""
Service layer for stitching multiple floor plans into one.

Orchestrates the stitching pipeline: load models from DB → transform → clip
→ merge → normalize → save.
"""

import json
import logging
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.models.domain import VectorizationResult, Wall, Room, Door, Point2D
from app.models.stitching import StitchingRequest, StitchingResponse
from app.processing.stitching import (
    build_affine_matrix,
    apply_affine_to_polygon,
)

logger = logging.getLogger(__name__)


class Point2DPixel(BaseModel):
    """Point in pixel coordinates (no [0,1] constraint)."""
    x: float
    y: float


class WallPixel(BaseModel):
    """Wall in pixel coordinates."""
    id: str
    points: List[Point2DPixel]
    thickness: float = 0.2


class RoomPixel(BaseModel):
    """Room in pixel coordinates."""
    id: str
    name: str = ""
    polygon: List[Point2DPixel]
    center: Point2DPixel
    room_type: str = "room"
    area_normalized: float = 0.0


class DoorPixel(BaseModel):
    """Door in pixel coordinates."""
    id: str
    position: Point2DPixel
    width: float = 0.0
    connects: List[str] = Field(default_factory=list)


class VectorizationResultPixel(BaseModel):
    """VectorizationResult in pixel coordinates (for intermediate processing)."""
    walls: List[WallPixel] = Field(default_factory=list)
    rooms: List[RoomPixel] = Field(default_factory=list)
    doors: List[DoorPixel] = Field(default_factory=list)
    image_size_original: Tuple[int, int]
    image_size_cropped: Tuple[int, int]
    crop_rect: Optional[dict] = None
    crop_applied: bool = False
    rotation_angle: int = 0
    wall_thickness_px: float = 0.0
    estimated_pixels_per_meter: float = 50.0
    rooms_with_names: int = 0
    corridors_count: int = 0
    doors_count: int = 0


class StitchingService:
    """Service for stitching multiple floor plans into one."""

    def __init__(self, reconstruction_repo: ReconstructionRepository) -> None:
        """
        Initialize stitching service.

        Args:
            reconstruction_repo: Repository for reconstruction data access
        """
        self.reconstruction_repo = reconstruction_repo

    async def stitch_plans(
        self,
        request: StitchingRequest,
        user_id: int,
    ) -> StitchingResponse:
        """
        Stitch multiple floor plans into one.

        Steps:
        1. Load source reconstructions from DB
        2. For each source:
           a. Deserialize vectorization_data
           b. Apply rect_crop (if any)
           c. Denormalize coords to image pixels
           d. Apply affine transform
           e. Apply clip polygons
        3. Merge all models
        4. Check for duplicate rooms
        5. Normalize to bounding box [0,1]
        6. Save new reconstruction
        7. Return response

        Args:
            request: StitchingRequest with source plans and transforms
            user_id: ID of user creating stitched reconstruction

        Returns:
            StitchingResponse with new reconstruction details

        Raises:
            ValueError: If source reconstruction not found
            ValueError: If no walls after merge
        """
        logger.info(
            "Starting stitching: %d source plans, user_id=%d",
            len(request.source_plans),
            user_id,
        )

        # Step 1: Load and transform all source plans
        transformed_models: List[VectorizationResultPixel] = []

        for idx, source in enumerate(request.source_plans):
            logger.info(
                "Processing source plan %d/%d: reconstruction_id=%s",
                idx + 1,
                len(request.source_plans),
                source.reconstruction_id,
            )

            # Load reconstruction from DB
            reconstruction = await self.reconstruction_repo.get_by_id(
                int(source.reconstruction_id)
            )
            if not reconstruction:
                raise ValueError(
                    f"Reconstruction {source.reconstruction_id} not found"
                )

            if not reconstruction.vectorization_data:
                raise ValueError(
                    f"Reconstruction {source.reconstruction_id} has no vectorization data"
                )

            # Deserialize vectorization data
            vectorization_dict = json.loads(reconstruction.vectorization_data)
            model = VectorizationResult(**vectorization_dict)

            # Apply rect crop if specified
            if source.rect_crop:
                logger.debug("Applying rect crop: %s", source.rect_crop)
                model = self._apply_rect_crop(
                    model,
                    source.rect_crop.model_dump(),
                    source.image_width_px,
                    source.image_height_px,
                )

            # Denormalize coordinates to image pixels
            model_px = self._denormalize_coords(
                model,
                source.image_width_px,
                source.image_height_px,
            )

            # Build affine transformation matrix
            import numpy as np
            matrix = build_affine_matrix(
                translate_x=source.transform.translate_x,
                translate_y=source.transform.translate_y,
                scale_x=source.transform.scale_x,
                scale_y=source.transform.scale_y,
                rotation_deg=source.transform.rotation_deg,
            )
            # Ensure matrix is numpy array
            if not isinstance(matrix, np.ndarray):
                matrix = np.array(matrix, dtype=np.float64)

            # Apply affine transform to all elements
            model_px = self._apply_affine_transform(model_px, matrix)

            # Apply clip polygons if specified
            if source.clip_polygons:
                logger.debug("Applying %d clip polygons", len(source.clip_polygons))
                for clip_poly in source.clip_polygons:
                    clip_points = [(p[0], p[1]) for p in clip_poly.points]
                    model_px = self._apply_clip_polygon(model_px, clip_points)

            transformed_models.append(model_px)

        # Step 3: Merge all models
        logger.info("Merging %d transformed models", len(transformed_models))
        merged_model_px = self._merge_models_pixel(transformed_models)

        # Validate merge result
        if not merged_model_px.walls:
            raise ValueError("No walls remaining after merge and clipping")

        # Step 4: Check for duplicate rooms
        warnings = self._check_duplicate_rooms_pixel(merged_model_px.rooms)
        if warnings:
            logger.warning("Duplicate rooms detected: %s", warnings)

        # Step 5: Normalize to bounding box [0,1]
        logger.info("Normalizing coordinates to [0,1]")
        normalized_model = self._normalize_to_bounding_box_pixel(merged_model_px)

        # Step 6: Save new reconstruction
        logger.info("Saving stitched reconstruction to DB")

        # Create placeholder files (stitching doesn't have plan/mask files)
        # We'll use the first source's plan_file_id as reference
        first_reconstruction = await self.reconstruction_repo.get_by_id(
            int(request.source_plans[0].reconstruction_id)
        )

        new_reconstruction = await self.reconstruction_repo.create_reconstruction(
            plan_file_id=first_reconstruction.plan_file_id,
            mask_file_id=first_reconstruction.mask_file_id,
            user_id=user_id,
            status=3,  # Ready
        )

        # Update name and vectorization data
        await self.reconstruction_repo.update_name(
            new_reconstruction.id,
            request.name,
        )

        vectorization_json = normalized_model.model_dump_json()
        await self.reconstruction_repo.update_vectorization_data(
            new_reconstruction.id,
            vectorization_json,
        )

        # Step 7: Build response
        source_ids = [int(s.reconstruction_id) for s in request.source_plans]

        logger.info(
            "Stitching complete: new reconstruction_id=%d, walls=%d, rooms=%d",
            new_reconstruction.id,
            len(normalized_model.walls),
            len(normalized_model.rooms),
        )

        return StitchingResponse(
            id=new_reconstruction.id,
            name=request.name,
            status=3,
            source_reconstruction_ids=source_ids,
            building_id=request.building_id,
            floor_number=request.floor_number,
            rooms_count=len(normalized_model.rooms),
            walls_count=len(normalized_model.walls),
            warnings=warnings if warnings else None,
        )

    def _merge_models_pixel(
        self,
        models: List[VectorizationResultPixel],
    ) -> VectorizationResultPixel:
        """
        Merge multiple pixel-space models into one.

        Args:
            models: List of VectorizationResultPixel objects

        Returns:
            Single merged VectorizationResultPixel
        """
        if not models:
            return VectorizationResultPixel(
                walls=[],
                rooms=[],
                doors=[],
                image_size_original=(0, 0),
                image_size_cropped=(0, 0),
            )

        all_walls = []
        all_rooms = []
        all_doors = []

        for model in models:
            all_walls.extend(model.walls)
            all_rooms.extend(model.rooms)
            all_doors.extend(model.doors)

        first = models[0]
        return VectorizationResultPixel(
            walls=all_walls,
            rooms=all_rooms,
            doors=all_doors,
            image_size_original=first.image_size_original,
            image_size_cropped=first.image_size_cropped,
            crop_rect=first.crop_rect,
            crop_applied=first.crop_applied,
            rotation_angle=first.rotation_angle,
            wall_thickness_px=first.wall_thickness_px,
            estimated_pixels_per_meter=first.estimated_pixels_per_meter,
            rooms_with_names=sum(1 for r in all_rooms if r.name),
            corridors_count=sum(1 for r in all_rooms if r.room_type == "corridor"),
            doors_count=len(all_doors),
        )

    def _check_duplicate_rooms_pixel(
        self,
        rooms: List[RoomPixel],
        distance_threshold: float = 30.0,
    ) -> List[str]:
        """
        Detect rooms with same name located close together.

        Args:
            rooms: List of RoomPixel objects
            distance_threshold: Max distance (pixels) to consider duplicate

        Returns:
            List of warning messages
        """
        warnings = []
        rooms_by_name = {}

        for room in rooms:
            if room.name:
                if room.name not in rooms_by_name:
                    rooms_by_name[room.name] = []
                rooms_by_name[room.name].append(room)

        for name, room_group in rooms_by_name.items():
            if len(room_group) <= 1:
                continue

            for i in range(len(room_group)):
                for j in range(i + 1, len(room_group)):
                    room_a = room_group[i]
                    room_b = room_group[j]

                    dx = room_a.center.x - room_b.center.x
                    dy = room_a.center.y - room_b.center.y
                    distance = (dx * dx + dy * dy) ** 0.5

                    if distance < distance_threshold:
                        warnings.append(
                            f"Duplicate room '{name}' detected: "
                            f"{room_a.id} and {room_b.id} are {distance:.1f}px apart"
                        )

        return warnings

    def _normalize_to_bounding_box_pixel(
        self,
        model: VectorizationResultPixel,
    ) -> VectorizationResult:
        """
        Normalize pixel coordinates to [0,1] relative to bounding box.

        Args:
            model: VectorizationResultPixel with pixel coordinates

        Returns:
            VectorizationResult with normalized [0,1] coordinates
        """
        if not model.walls:
            return VectorizationResult(
                walls=[],
                rooms=[],
                doors=[],
                text_blocks=[],
                image_size_original=model.image_size_original,
                image_size_cropped=model.image_size_cropped,
            )

        # Find bounding box from walls AND rooms
        all_x = []
        all_y = []
        for wall in model.walls:
            for point in wall.points:
                all_x.append(point.x)
                all_y.append(point.y)

        for room in model.rooms:
            for point in room.polygon:
                all_x.append(point.x)
                all_y.append(point.y)

        if not all_x:
            return VectorizationResult(
                walls=[],
                rooms=[],
                doors=[],
                text_blocks=[],
                image_size_original=model.image_size_original,
                image_size_cropped=model.image_size_cropped,
            )

        min_x = min(all_x)
        max_x = max(all_x)
        min_y = min(all_y)
        max_y = max(all_y)

        width = max_x - min_x
        height = max_y - min_y

        if width == 0 or height == 0:
            return VectorizationResult(
                walls=[],
                rooms=[],
                doors=[],
                text_blocks=[],
                image_size_original=model.image_size_original,
                image_size_cropped=model.image_size_cropped,
            )

        def normalize_point(point: Point2DPixel) -> Point2D:
            """Normalize pixel point to [0,1]."""
            return Point2D(
                x=(point.x - min_x) / width,
                y=(point.y - min_y) / height,
            )

        # Normalize walls
        normalized_walls = []
        for wall in model.walls:
            normalized_walls.append(
                Wall(
                    id=wall.id,
                    points=[normalize_point(p) for p in wall.points],
                    thickness=wall.thickness,
                )
            )

        # Normalize rooms
        normalized_rooms = []
        for room in model.rooms:
            normalized_rooms.append(
                Room(
                    id=room.id,
                    name=room.name,
                    polygon=[normalize_point(p) for p in room.polygon],
                    center=normalize_point(room.center),
                    room_type=room.room_type,
                    area_normalized=room.area_normalized,
                )
            )

        # Normalize doors
        normalized_doors = []
        for door in model.doors:
            normalized_doors.append(
                Door(
                    id=door.id,
                    position=normalize_point(door.position),
                    width=door.width,
                    connects=door.connects,
                )
            )

        return VectorizationResult(
            walls=normalized_walls,
            rooms=normalized_rooms,
            doors=normalized_doors,
            text_blocks=[],
            image_size_original=model.image_size_original,
            image_size_cropped=model.image_size_cropped,
            crop_rect=model.crop_rect,
            crop_applied=model.crop_applied,
            rotation_angle=model.rotation_angle,
            wall_thickness_px=model.wall_thickness_px,
            estimated_pixels_per_meter=model.estimated_pixels_per_meter,
            rooms_with_names=model.rooms_with_names,
            corridors_count=model.corridors_count,
            doors_count=model.doors_count,
        )

    def _denormalize_coords(
        self,
        model: VectorizationResult,
        image_width: int,
        image_height: int,
    ) -> VectorizationResultPixel:
        """
        Convert normalized [0,1] coords to image pixels.

        Args:
            model: VectorizationResult with normalized coordinates
            image_width: Image width in pixels
            image_height: Image height in pixels

        Returns:
            VectorizationResultPixel with pixel coordinates
        """

        def denorm_point(point: Point2D) -> Point2DPixel:
            """Denormalize a single point."""
            return Point2DPixel(
                x=point.x * image_width,
                y=point.y * image_height,
            )

        # Denormalize walls
        denorm_walls = []
        for wall in model.walls:
            denorm_walls.append(
                WallPixel(
                    id=wall.id,
                    points=[denorm_point(p) for p in wall.points],
                    thickness=wall.thickness,
                )
            )

        # Denormalize rooms
        denorm_rooms = []
        for room in model.rooms:
            denorm_rooms.append(
                RoomPixel(
                    id=room.id,
                    name=room.name,
                    polygon=[denorm_point(p) for p in room.polygon],
                    center=denorm_point(room.center),
                    room_type=room.room_type,
                    area_normalized=room.area_normalized,
                )
            )

        # Denormalize doors
        denorm_doors = []
        for door in model.doors:
            denorm_doors.append(
                DoorPixel(
                    id=door.id,
                    position=denorm_point(door.position),
                    width=door.width,
                    connects=door.connects,
                )
            )

        return VectorizationResultPixel(
            walls=denorm_walls,
            rooms=denorm_rooms,
            doors=denorm_doors,
            image_size_original=model.image_size_original,
            image_size_cropped=model.image_size_cropped,
            crop_rect=model.crop_rect,
            crop_applied=model.crop_applied,
            rotation_angle=model.rotation_angle,
            wall_thickness_px=model.wall_thickness_px,
            estimated_pixels_per_meter=model.estimated_pixels_per_meter,
            rooms_with_names=model.rooms_with_names,
            corridors_count=model.corridors_count,
            doors_count=model.doors_count,
        )

    def _apply_rect_crop(
        self,
        model: VectorizationResult,
        crop: dict,
        image_width: int,
        image_height: int,
    ) -> VectorizationResult:
        """
        Apply rectangular crop in image space.

        Filters out elements outside crop rect and adjusts coordinates.

        Args:
            model: VectorizationResult with normalized coordinates
            crop: Crop rectangle {x, y, width, height} in pixels
            image_width: Original image width in pixels
            image_height: Original image height in pixels

        Returns:
            VectorizationResult with cropped elements
        """
        crop_x = crop["x"]
        crop_y = crop["y"]
        crop_w = crop["width"]
        crop_h = crop["height"]

        def is_point_in_crop(point: Point2D) -> bool:
            """Check if point (in normalized coords) is inside crop rect."""
            px = point.x * image_width
            py = point.y * image_height
            return (
                crop_x <= px <= crop_x + crop_w
                and crop_y <= py <= crop_y + crop_h
            )

        def adjust_point(point: Point2D) -> Point2D:
            """Adjust point coordinates relative to crop origin."""
            px = point.x * image_width
            py = point.y * image_height
            # Clamp to [0, 1] range after normalization
            norm_x = max(0.0, min(1.0, (px - crop_x) / crop_w))
            norm_y = max(0.0, min(1.0, (py - crop_y) / crop_h))
            return Point2D(x=norm_x, y=norm_y)

        # Filter and adjust walls
        cropped_walls = []
        for wall in model.walls:
            # Keep wall if any point is inside crop
            if any(is_point_in_crop(p) for p in wall.points):
                cropped_walls.append(
                    Wall(
                        id=wall.id,
                        points=[adjust_point(p) for p in wall.points],
                        thickness=wall.thickness,
                    )
                )

        # Filter and adjust rooms
        cropped_rooms = []
        for room in model.rooms:
            if is_point_in_crop(room.center):
                cropped_rooms.append(
                    Room(
                        id=room.id,
                        name=room.name,
                        polygon=[adjust_point(p) for p in room.polygon],
                        center=adjust_point(room.center),
                        room_type=room.room_type,
                        area_normalized=room.area_normalized,
                    )
                )

        # Filter and adjust doors
        cropped_doors = []
        for door in model.doors:
            if is_point_in_crop(door.position):
                cropped_doors.append(
                    Door(
                        id=door.id,
                        position=adjust_point(door.position),
                        width=door.width,
                        connects=door.connects,
                    )
                )

        return VectorizationResult(
            walls=cropped_walls,
            rooms=cropped_rooms,
            doors=cropped_doors,
            text_blocks=model.text_blocks,
            image_size_original=model.image_size_original,
            image_size_cropped=(int(crop_w), int(crop_h)),
            crop_rect=crop,
            crop_applied=True,
            rotation_angle=model.rotation_angle,
            wall_thickness_px=model.wall_thickness_px,
            estimated_pixels_per_meter=model.estimated_pixels_per_meter,
            rooms_with_names=model.rooms_with_names,
            corridors_count=model.corridors_count,
            doors_count=model.doors_count,
        )

    def _apply_affine_transform(
        self,
        model: VectorizationResultPixel,
        matrix: list,
    ) -> VectorizationResultPixel:
        """
        Apply affine transformation to all model elements.

        Args:
            model: VectorizationResultPixel with pixel coordinates
            matrix: 2x3 affine transformation matrix

        Returns:
            VectorizationResultPixel with transformed coordinates
        """
        # Transform walls
        transformed_walls = []
        for wall in model.walls:
            wall_points = [[p.x, p.y] for p in wall.points]
            transformed_points = apply_affine_to_polygon(matrix, wall_points)
            transformed_walls.append(
                WallPixel(
                    id=wall.id,
                    points=[Point2DPixel(x=p[0], y=p[1]) for p in transformed_points],
                    thickness=wall.thickness,
                )
            )

        # Transform rooms
        transformed_rooms = []
        for room in model.rooms:
            room_points = [[p.x, p.y] for p in room.polygon]
            transformed_polygon = apply_affine_to_polygon(matrix, room_points)
            center_transformed = apply_affine_to_polygon(
                matrix, [[room.center.x, room.center.y]]
            )[0]
            transformed_rooms.append(
                RoomPixel(
                    id=room.id,
                    name=room.name,
                    polygon=[Point2DPixel(x=p[0], y=p[1]) for p in transformed_polygon],
                    center=Point2DPixel(x=center_transformed[0], y=center_transformed[1]),
                    room_type=room.room_type,
                    area_normalized=room.area_normalized,
                )
            )

        # Transform doors
        transformed_doors = []
        for door in model.doors:
            door_pos = apply_affine_to_polygon(
                matrix, [[door.position.x, door.position.y]]
            )[0]
            transformed_doors.append(
                DoorPixel(
                    id=door.id,
                    position=Point2DPixel(x=door_pos[0], y=door_pos[1]),
                    width=door.width,
                    connects=door.connects,
                )
            )

        return VectorizationResultPixel(
            walls=transformed_walls,
            rooms=transformed_rooms,
            doors=transformed_doors,
            image_size_original=model.image_size_original,
            image_size_cropped=model.image_size_cropped,
            crop_rect=model.crop_rect,
            crop_applied=model.crop_applied,
            rotation_angle=model.rotation_angle,
            wall_thickness_px=model.wall_thickness_px,
            estimated_pixels_per_meter=model.estimated_pixels_per_meter,
            rooms_with_names=model.rooms_with_names,
            corridors_count=model.corridors_count,
            doors_count=model.doors_count,
        )

    def _apply_clip_polygon(
        self,
        model: VectorizationResultPixel,
        clip_polygon: List[Tuple[float, float]],
    ) -> VectorizationResultPixel:
        """
        Apply clip polygon (subtract operation) to model.

        Args:
            model: VectorizationResultPixel to clip
            clip_polygon: Polygon to subtract (list of (x, y) tuples)

        Returns:
            VectorizationResultPixel with clipped elements
        """
        from shapely.geometry import Polygon, LineString

        # Convert clip polygon to Shapely Polygon
        clip_poly = Polygon(clip_polygon)

        # Clip walls
        clipped_walls = []
        for wall in model.walls:
            wall_line = LineString([(p.x, p.y) for p in wall.points])

            # Subtract clip polygon from wall
            clipped_geom = wall_line.difference(clip_poly)

            # Handle different geometry types
            if clipped_geom.is_empty:
                continue
            elif clipped_geom.geom_type == 'LineString':
                coords = list(clipped_geom.coords)
                if len(coords) >= 2:
                    clipped_walls.append(
                        WallPixel(
                            id=wall.id,
                            points=[Point2DPixel(x=p[0], y=p[1]) for p in coords],
                            thickness=wall.thickness,
                        )
                    )
            elif clipped_geom.geom_type == 'MultiLineString':
                for idx, line in enumerate(clipped_geom.geoms):
                    coords = list(line.coords)
                    if len(coords) >= 2:
                        clipped_walls.append(
                            WallPixel(
                                id=f"{wall.id}_seg{idx}",
                                points=[Point2DPixel(x=p[0], y=p[1]) for p in coords],
                                thickness=wall.thickness,
                            )
                        )

        # Clip rooms
        clipped_rooms = []
        for room in model.rooms:
            room_poly = Polygon([(p.x, p.y) for p in room.polygon])

            # Subtract clip polygon from room
            clipped_geom = room_poly.difference(clip_poly)

            if clipped_geom.is_empty:
                continue
            elif clipped_geom.geom_type == 'Polygon':
                coords = list(clipped_geom.exterior.coords[:-1])  # Remove duplicate last point
                if len(coords) >= 3:
                    # Recompute center
                    center_x = sum(p[0] for p in coords) / len(coords)
                    center_y = sum(p[1] for p in coords) / len(coords)
                    clipped_rooms.append(
                        RoomPixel(
                            id=room.id,
                            name=room.name,
                            polygon=[Point2DPixel(x=p[0], y=p[1]) for p in coords],
                            center=Point2DPixel(x=center_x, y=center_y),
                            room_type=room.room_type,
                            area_normalized=room.area_normalized,
                        )
                    )

        # Clip doors (simple point-in-polygon test)
        clipped_doors = []
        for door in model.doors:
            from shapely.geometry import Point
            door_point = Point(door.position.x, door.position.y)

            # Keep door if it's NOT inside clip polygon
            if not clip_poly.contains(door_point):
                clipped_doors.append(door)

        return VectorizationResultPixel(
            walls=clipped_walls,
            rooms=clipped_rooms,
            doors=clipped_doors,
            image_size_original=model.image_size_original,
            image_size_cropped=model.image_size_cropped,
            crop_rect=model.crop_rect,
            crop_applied=model.crop_applied,
            rotation_angle=model.rotation_angle,
            wall_thickness_px=model.wall_thickness_px,
            estimated_pixels_per_meter=model.estimated_pixels_per_meter,
            rooms_with_names=len([r for r in clipped_rooms if r.name]),
            corridors_count=len([r for r in clipped_rooms if r.room_type == "corridor"]),
            doors_count=len(clipped_doors),
        )
