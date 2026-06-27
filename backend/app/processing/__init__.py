"""
Processing module - pure functions for image processing.

All functions are PURE — no DB, no HTTP, no file I/O, no state.
"""

# Binarization functions
from app.processing.binarization import (
    to_grayscale,
    binarize_otsu,
    apply_adaptive_threshold,
    apply_morphology,
    invert_if_needed,
    binarize_image,
)

# Contour extraction and classification
from app.processing.contours import (
    StructuralElement,
    find_contours,
    approximate_contour,
    get_contour_properties,
    classify_element,
    extract_elements,
    draw_contours,
    get_wall_contours,
)

# Vectorization
from app.processing.vectorizer import (
    find_contours as vectorizer_find_contours,
)

# Preprocessing
from app.processing.preprocessor import preprocess_image

# Mesh building
from app.processing.mesh_builder import build_mesh_from_mask, build_mesh

# Navigation (class + pure function)
from app.processing.navigation import (
    NavigationGraphService,
    GraphNode,
    GraphEdge,
    a_star,
)

__all__ = [
    # Binarization
    "to_grayscale",
    "binarize_otsu",
    "apply_adaptive_threshold",
    "apply_morphology",
    "invert_if_needed",
    "binarize_image",
    # Contours
    "StructuralElement",
    "find_contours",
    "approximate_contour",
    "get_contour_properties",
    "classify_element",
    "extract_elements",
    "draw_contours",
    "get_wall_contours",
    # Vectorization
    "vectorizer_find_contours",
    # Preprocessing
    "preprocess_image",
    # Mesh building
    "build_mesh_from_mask",
    "build_mesh",
    # Navigation
    "NavigationGraphService",
    "GraphNode",
    "GraphEdge",
    "a_star",
]
