"""Model merging and coordinate normalization for stitching pipeline."""

from typing import List, Dict
from app.models.domain import (
    VectorizationResult,
    Wall,
    Room,
    Door,
    Point2D,
    TextBlock,
)


def merge_models(
    models: List[VectorizationResult],
) -> VectorizationResult:
    """
    Merge multiple vectorization models into one.

    Concatenates walls, rooms, doors. Does NOT normalize coordinates.

    Args:
        models: List of VectorizationResult objects

    Returns:
        Single VectorizationResult with all elements combined
    """
    if not models:
        return VectorizationResult(
            walls=[],
            rooms=[],
            doors=[],
            text_blocks=[],
            image_size_original=(0, 0),
            image_size_cropped=(0, 0),
        )

    # Concatenate all elements
    all_walls: List[Wall] = []
    all_rooms: List[Room] = []
    all_doors: List[Door] = []
    all_text_blocks = []

    for model in models:
        all_walls.extend(model.walls)
        all_rooms.extend(model.rooms)
        all_doors.extend(model.doors)
        all_text_blocks.extend(model.text_blocks)

    # Use first model's metadata as base
    first = models[0]

    return VectorizationResult(
        walls=all_walls,
        rooms=all_rooms,
        doors=all_doors,
        text_blocks=all_text_blocks,
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


def normalize_to_bounding_box(
    model: VectorizationResult,
) -> VectorizationResult:
    """
    Normalize all coordinates to [0,1] relative to bounding box.

    Bounding box computed from all wall points.

    Args:
        model: VectorizationResult with coordinates in any space

    Returns:
        VectorizationResult with coordinates in [0,1]
    """
    if not model.walls:
        return model

    # Find bounding box from all wall points
    all_x = []
    all_y = []
    for wall in model.walls:
        for point in wall.points:
            all_x.append(point.x)
            all_y.append(point.y)

    if not all_x:
        return model

    min_x = min(all_x)
    max_x = max(all_x)
    min_y = min(all_y)
    max_y = max(all_y)

    width = max_x - min_x
    height = max_y - min_y

    # Avoid division by zero
    if width == 0 or height == 0:
        return model

    def normalize_point(point: Point2D) -> Point2D:
        """Normalize a single point to [0,1]."""
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

    # Normalize text blocks
    normalized_text_blocks = []
    for text_block in model.text_blocks:
        normalized_text_blocks.append(
            TextBlock(
                text=text_block.text,
                center=normalize_point(text_block.center),
                confidence=text_block.confidence,
                is_room_number=text_block.is_room_number,
            )
        )

    return VectorizationResult(
        walls=normalized_walls,
        rooms=normalized_rooms,
        doors=normalized_doors,
        text_blocks=normalized_text_blocks,
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


def check_duplicate_rooms(
    rooms: List[Room],
    distance_threshold: float = 30.0,
) -> List[str]:
    """
    Detect rooms with same name located close together.

    Args:
        rooms: List of Room objects
        distance_threshold: Max distance (pixels) to consider duplicate

    Returns:
        List of warning messages (empty if no duplicates)
    """
    warnings = []

    # Group rooms by name
    rooms_by_name: Dict[str, List[Room]] = {}
    for room in rooms:
        if room.name:  # Only check named rooms
            if room.name not in rooms_by_name:
                rooms_by_name[room.name] = []
            rooms_by_name[room.name].append(room)

    # Check each group for duplicates
    for name, room_group in rooms_by_name.items():
        if len(room_group) <= 1:
            continue

        # Check pairwise distances
        for i in range(len(room_group)):
            for j in range(i + 1, len(room_group)):
                room_a = room_group[i]
                room_b = room_group[j]

                # Calculate Euclidean distance between centers
                dx = room_a.center.x - room_b.center.x
                dy = room_a.center.y - room_b.center.y
                distance = (dx * dx + dy * dy) ** 0.5

                if distance < distance_threshold:
                    warnings.append(
                        f"Duplicate room '{name}' detected: "
                        f"{room_a.id} and {room_b.id} are {distance:.1f}px apart"
                    )

    return warnings
