"""Polygon clipping operations for stitching floor plans."""
from typing import List
from shapely.geometry import Polygon, LineString, MultiLineString, Point
from app.models.domain import Wall, Room, Door, Point2D


def clip_walls(
    walls: List[Wall],
    clip_polygon: Polygon,
) -> List[Wall]:
    """
    Remove walls inside clip polygon.

    Walls fully inside → removed
    Walls fully outside → unchanged
    Walls intersecting → trimmed (may create multiple segments)

    Args:
        walls: List of Wall objects
        clip_polygon: Shapely Polygon to subtract

    Returns:
        List of Wall objects after clipping
    """
    result: List[Wall] = []

    for wall in walls:
        # Convert Wall points to Shapely LineString
        coords = [(p.x, p.y) for p in wall.points]
        line = LineString(coords)

        # Subtract clip polygon from line
        diff = line.difference(clip_polygon)

        # Handle result based on geometry type
        if diff.is_empty:
            # Wall fully inside clip polygon → skip
            continue
        elif isinstance(diff, LineString):
            # Single segment remains
            new_points = [Point2D(x=x, y=y) for x, y in diff.coords]
            result.append(Wall(
                id=wall.id,
                points=new_points,
                thickness=wall.thickness,
            ))
        elif isinstance(diff, MultiLineString):
            # Multiple segments created
            for i, segment in enumerate(diff.geoms):
                new_points = [Point2D(x=x, y=y) for x, y in segment.coords]
                result.append(Wall(
                    id=f"{wall.id}_seg{i}",
                    points=new_points,
                    thickness=wall.thickness,
                ))

    return result


def clip_rooms(
    rooms: List[Room],
    clip_polygon: Polygon,
) -> List[Room]:
    """
    Remove rooms whose center is inside clip polygon.

    If room polygon intersects clip boundary, trim polygon and recalculate center.

    Args:
        rooms: List of Room objects
        clip_polygon: Shapely Polygon to subtract

    Returns:
        List of Room objects after clipping
    """
    result: List[Room] = []

    for room in rooms:
        # Check if center is inside clip polygon
        center_point = Point(room.center.x, room.center.y)
        if clip_polygon.contains(center_point):
            # Center inside → remove room
            continue

        # Convert room polygon to Shapely
        coords = [(p.x, p.y) for p in room.polygon]
        room_poly = Polygon(coords)

        # Check if room intersects clip polygon
        if room_poly.intersects(clip_polygon):
            # Trim the room polygon
            diff = room_poly.difference(clip_polygon)

            if diff.is_empty:
                # Fully clipped → skip
                continue

            # Handle only Polygon result (ignore MultiPolygon for simplicity)
            if isinstance(diff, Polygon):
                # Update polygon and recalculate center
                new_polygon = [Point2D(x=x, y=y) for x, y in diff.exterior.coords[:-1]]
                centroid = diff.centroid
                new_center = Point2D(x=centroid.x, y=centroid.y)

                result.append(Room(
                    id=room.id,
                    name=room.name,
                    polygon=new_polygon,
                    center=new_center,
                    room_type=room.room_type,
                    area_normalized=diff.area,
                ))
            # Skip MultiPolygon cases
        else:
            # No intersection → keep unchanged
            result.append(room)

    return result


def clip_doors(
    doors: List[Door],
    clip_polygon: Polygon,
) -> List[Door]:
    """
    Remove doors inside clip polygon.

    Args:
        doors: List of Door objects
        clip_polygon: Shapely Polygon to subtract

    Returns:
        List of Door objects after clipping
    """
    result: List[Door] = []

    for door in doors:
        # Check if door position is inside clip polygon
        door_point = Point(door.position.x, door.position.y)
        if not clip_polygon.contains(door_point):
            # Outside clip polygon → keep
            result.append(door)

    return result
