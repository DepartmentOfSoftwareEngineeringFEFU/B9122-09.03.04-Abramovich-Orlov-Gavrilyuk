import pytest
from app.processing.vectorizer import find_contours
from app.processing.mesh_builder import build_mesh
from app.core.exceptions import ImageProcessingError


def test_build_mesh_valid_contours_returns_mesh(binary_rectangle_mask):
    contours = find_contours(binary_rectangle_mask)
    h, w = binary_rectangle_mask.shape
    mesh = build_mesh(contours, image_width=w, image_height=h)
    assert mesh is not None
    assert len(mesh.vertices) > 0, "Mesh must contain vertices"
    assert len(mesh.faces) > 0, "Mesh must contain faces"


def test_build_mesh_empty_contours_raises_error():
    with pytest.raises(ImageProcessingError):
        build_mesh([], image_width=200, image_height=200)
