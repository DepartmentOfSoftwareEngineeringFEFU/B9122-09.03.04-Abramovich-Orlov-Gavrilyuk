import pytest
import numpy as np
import cv2

from app.models.domain import (
    Door, Point2D, Room, VectorizationResult, Wall,
)


@pytest.fixture
def simple_wall_contour() -> np.ndarray:
    return np.array([[[10, 10]], [[50, 10]], [[50, 50]], [[10, 50]]], dtype=np.int32)


@pytest.fixture
def sample_vectorization_result() -> VectorizationResult:
    return VectorizationResult(
        walls=[
            Wall(
                id="w0",
                points=[
                    Point2D(x=0.1, y=0.1),
                    Point2D(x=0.5, y=0.1),
                    Point2D(x=0.5, y=0.5),
                    Point2D(x=0.1, y=0.5),
                ],
                thickness=0.2,
            )
        ],
        rooms=[
            Room(
                id="r0",
                name="Аудитория 101",
                polygon=[
                    Point2D(x=0.1, y=0.1),
                    Point2D(x=0.5, y=0.1),
                    Point2D(x=0.5, y=0.5),
                    Point2D(x=0.1, y=0.5),
                ],
                center=Point2D(x=0.3, y=0.3),
                room_type="classroom",
            )
        ],
        doors=[],
        image_size_original=(500, 500),
        image_size_cropped=(500, 500),
        estimated_pixels_per_meter=50.0,
    )


@pytest.fixture
def blank_white_image() -> np.ndarray:
    return np.ones((200, 200, 3), dtype=np.uint8) * 255


@pytest.fixture
def simple_room_image() -> np.ndarray:
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (20, 20), (180, 180), (0, 0, 0), thickness=5)
    return img


@pytest.fixture
def binary_rectangle_mask() -> np.ndarray:
    mask = np.zeros((200, 200), dtype=np.uint8)
    cv2.rectangle(mask, (20, 20), (180, 180), 255, thickness=5)
    return mask


@pytest.fixture
def empty_mask() -> np.ndarray:
    return np.zeros((200, 200), dtype=np.uint8)
