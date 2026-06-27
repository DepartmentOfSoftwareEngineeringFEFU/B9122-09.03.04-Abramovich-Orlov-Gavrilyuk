"""Tests for _create_floor and _create_wall_cap in mesh_builder."""
import numpy as np
import pytest

pytest.importorskip("trimesh")
pytest.importorskip("shapely")

from shapely.geometry import Polygon as ShapelyPolygon
from app.processing.mesh_builder import _create_floor, _create_wall_cap
from app.processing.mesh_generator import FLOOR_COLOR, WALL_CAP_COLOR, WALL_SIDE_COLOR


# --- _create_floor ---

def test_create_floor_valid_dims_returns_quad():
    # Arrange / Act
    mesh = _create_floor(5.0, 3.0, FLOOR_COLOR)
    # Assert
    assert mesh is not None
    assert len(mesh.vertices) == 4
    assert len(mesh.faces) == 2


def test_create_floor_vertex_colors_match_floor_color():
    mesh = _create_floor(5.0, 3.0, FLOOR_COLOR)
    assert mesh is not None
    colors = np.array(mesh.visual.vertex_colors)
    assert colors.shape == (4, 4)
    assert np.all(colors[:, :3] == FLOOR_COLOR[:3])


def test_create_floor_zero_width_returns_none():
    assert _create_floor(0.0, 3.0, FLOOR_COLOR) is None


def test_create_floor_zero_height_returns_none():
    assert _create_floor(5.0, 0.0, FLOOR_COLOR) is None


# --- _create_wall_cap ---

def test_create_wall_cap_valid_polygon_returns_mesh_at_height():
    poly = ShapelyPolygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    mesh = _create_wall_cap(poly, height=3.0, color=WALL_CAP_COLOR)
    assert mesh is not None
    assert len(mesh.vertices) > 0
    # In Z-up space (before rotation), cap is translated along Z axis
    assert np.all(mesh.vertices[:, 2] >= 3.0)


def test_create_wall_cap_vertex_colors_match_cap_color():
    poly = ShapelyPolygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    mesh = _create_wall_cap(poly, height=3.0, color=WALL_CAP_COLOR)
    assert mesh is not None
    colors = np.array(mesh.visual.vertex_colors)
    assert np.all(colors[:, :3] == WALL_CAP_COLOR[:3])


def test_create_wall_cap_invalid_polygon_returns_none():
    # Empty polygon is invalid/empty
    poly = ShapelyPolygon()
    result = _create_wall_cap(poly, height=3.0, color=WALL_CAP_COLOR)
    assert result is None


# --- build_mesh_from_mask integration ---

def test_build_mesh_from_mask_contains_wall_colors():
    """Integration: result mesh has vertices with WALL_SIDE_COLOR."""
    import cv2
    from app.processing.mesh_builder import build_mesh_from_mask

    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(mask, (10, 10), (90, 90), 255, thickness=5)

    mesh = build_mesh_from_mask(mask, floor_height=3.0, pixels_per_meter=10.0)
    colors = np.array(mesh.visual.vertex_colors)[:, :3]

    wall_side = np.array(WALL_SIDE_COLOR[:3])
    assert any(np.all(row == wall_side) for row in colors), "WALL_SIDE_COLOR not found"
