"""Tests for StitchingService."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.stitching_service import StitchingService
from app.models.stitching import (
    StitchingRequest,
    SourcePlanInput,
    TransformInput,
    ClipPolygonInput,
    RectCropInput,
)
from app.models.domain import (
    VectorizationResult,
    Wall,
    Room,
    Point2D,
)
from app.db.models.reconstruction import Reconstruction


def create_mock_reconstruction(
    reconstruction_id: int,
    rooms: list = None,
    walls: list = None,
) -> Reconstruction:
    """Create a mock Reconstruction object with vectorization data."""
    if rooms is None:
        rooms = []
    if walls is None:
        walls = [
            Wall(
                id=f"wall_{i}",
                points=[
                    Point2D(x=0.1 + i * 0.1, y=0.1),
                    Point2D(x=0.1 + i * 0.1, y=0.9),
                ],
                thickness=0.2,
            )
            for i in range(2)
        ]

    room_objects = [
        Room(
            id=f"room_{i}",
            name=room_name,
            polygon=[
                Point2D(x=0.1 + i * 0.2, y=0.1),
                Point2D(x=0.3 + i * 0.2, y=0.1),
                Point2D(x=0.3 + i * 0.2, y=0.3),
                Point2D(x=0.1 + i * 0.2, y=0.3),
            ],
            center=Point2D(x=0.2 + i * 0.2, y=0.2),
            room_type="room",
            area_normalized=0.04,
        )
        for i, room_name in enumerate(rooms)
    ]

    vectorization_result = VectorizationResult(
        walls=walls,
        rooms=room_objects,
        doors=[],
        text_blocks=[],
        image_size_original=(1000, 800),
        image_size_cropped=(1000, 800),
    )

    mock_reconstruction = MagicMock(spec=Reconstruction)
    mock_reconstruction.id = reconstruction_id
    mock_reconstruction.plan_file_id = f"plan_{reconstruction_id}"
    mock_reconstruction.mask_file_id = f"mask_{reconstruction_id}"
    mock_reconstruction.vectorization_data = vectorization_result.model_dump_json()
    mock_reconstruction.status = 3

    return mock_reconstruction


@pytest.mark.asyncio
async def test_stitch_plans_two_plans_no_clip_succeeds():
    """Test stitching two plans without clipping."""
    # Arrange
    mock_repo = MagicMock()
    recon1 = create_mock_reconstruction(1, rooms=["A301"])
    recon2 = create_mock_reconstruction(2, rooms=["A302"])
    mock_repo.get_by_id = AsyncMock(
        side_effect=[
            recon1,
            recon2,
            recon1,  # Third call to get first reconstruction's file IDs
        ]
    )

    new_reconstruction = create_mock_reconstruction(3, rooms=["A301", "A302"])
    new_reconstruction.name = "Merged Floor"
    mock_repo.create_reconstruction = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_name = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_vectorization_data = AsyncMock(return_value=new_reconstruction)

    service = StitchingService(mock_repo)

    request = StitchingRequest(
        name="Merged Floor",
        building_id="building-uuid-123",
        floor_number=3,
        source_plans=[
            SourcePlanInput(
                reconstruction_id="1",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=0,
            ),
            SourcePlanInput(
                reconstruction_id="2",
                transform=TransformInput(
                    translate_x=500,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=1,
            ),
        ],
    )

    # Act
    response = await service.stitch_plans(request, user_id=1)

    # Assert
    assert response.name == "Merged Floor"
    assert response.rooms_count == 2
    assert len(response.source_reconstruction_ids) == 2
    assert response.source_reconstruction_ids == [1, 2]
    assert response.building_id == "building-uuid-123"
    assert response.floor_number == 3
    assert response.status == 3
    assert response.walls_count >= 2


@pytest.mark.asyncio
async def test_stitch_plans_with_clip_polygons_succeeds():
    """Test stitching with clip polygons applied."""
    # Arrange
    mock_repo = MagicMock()
    recon1 = create_mock_reconstruction(1, rooms=["A301"])
    recon2 = create_mock_reconstruction(2, rooms=["A302"])
    mock_repo.get_by_id = AsyncMock(
        side_effect=[
            recon1,
            recon2,
            recon1,
        ]
    )

    new_reconstruction = create_mock_reconstruction(3)
    mock_repo.create_reconstruction = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_name = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_vectorization_data = AsyncMock(return_value=new_reconstruction)

    service = StitchingService(mock_repo)

    request = StitchingRequest(
        name="Clipped Merge",
        building_id="building-uuid",
        floor_number=1,
        source_plans=[
            SourcePlanInput(
                reconstruction_id="1",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[
                    ClipPolygonInput(
                        type="subtract",
                        points=[(100.0, 100.0), (200.0, 100.0), (200.0, 200.0)],
                    )
                ],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=0,
            ),
            SourcePlanInput(
                reconstruction_id="2",
                transform=TransformInput(
                    translate_x=300,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=1,
            ),
        ],
    )

    # Act
    response = await service.stitch_plans(request, user_id=1)

    # Assert
    assert response.name == "Clipped Merge"
    assert response.status == 3
    assert len(response.source_reconstruction_ids) == 2


@pytest.mark.asyncio
async def test_stitch_plans_with_rect_crop_succeeds():
    """Test stitching with rectangular crop applied."""
    # Arrange
    mock_repo = MagicMock()
    recon1 = create_mock_reconstruction(1, rooms=["A301"])
    recon2 = create_mock_reconstruction(2, rooms=["A302"])
    mock_repo.get_by_id = AsyncMock(
        side_effect=[
            recon1,
            recon2,
            recon1,
        ]
    )

    new_reconstruction = create_mock_reconstruction(3)
    mock_repo.create_reconstruction = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_name = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_vectorization_data = AsyncMock(return_value=new_reconstruction)

    service = StitchingService(mock_repo)

    request = StitchingRequest(
        name="Cropped Merge",
        building_id="building-uuid",
        floor_number=2,
        source_plans=[
            SourcePlanInput(
                reconstruction_id="1",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=RectCropInput(x=100, y=100, width=500, height=400),
                image_width_px=1000,
                image_height_px=800,
                z_index=0,
            ),
            SourcePlanInput(
                reconstruction_id="2",
                transform=TransformInput(
                    translate_x=400,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=1,
            ),
        ],
    )

    # Act
    response = await service.stitch_plans(request, user_id=1)

    # Assert
    assert response.name == "Cropped Merge"
    assert response.status == 3


@pytest.mark.asyncio
async def test_stitch_plans_source_not_found_raises_404():
    """Test that missing source reconstruction raises ValueError."""
    # Arrange
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=None)

    service = StitchingService(mock_repo)

    request = StitchingRequest(
        name="Test",
        building_id="building-uuid",
        floor_number=1,
        source_plans=[
            SourcePlanInput(
                reconstruction_id="999",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=0,
            ),
            SourcePlanInput(
                reconstruction_id="1000",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=1,
            ),
        ],
    )

    # Act & Assert
    with pytest.raises(ValueError, match="Reconstruction 999 not found"):
        await service.stitch_plans(request, user_id=1)


@pytest.mark.asyncio
async def test_stitch_plans_duplicate_rooms_returns_warnings():
    """Test that duplicate rooms generate warnings."""
    # Arrange
    # Create two plans with same room name at close positions
    mock_repo = MagicMock()
    recon1 = create_mock_reconstruction(1, rooms=["A301"])
    recon2 = create_mock_reconstruction(2, rooms=["A301"])  # Same name
    mock_repo.get_by_id = AsyncMock(
        side_effect=[
            recon1,
            recon2,
            recon1,
        ]
    )

    new_reconstruction = create_mock_reconstruction(3)
    mock_repo.create_reconstruction = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_name = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_vectorization_data = AsyncMock(return_value=new_reconstruction)

    service = StitchingService(mock_repo)

    request = StitchingRequest(
        name="Duplicate Test",
        building_id="building-uuid",
        floor_number=1,
        source_plans=[
            SourcePlanInput(
                reconstruction_id="1",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=0,
            ),
            SourcePlanInput(
                reconstruction_id="2",
                transform=TransformInput(
                    translate_x=10,  # Very close to first plan
                    translate_y=10,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=1,
            ),
        ],
    )

    # Act
    response = await service.stitch_plans(request, user_id=1)

    # Assert
    assert response.warnings is not None
    assert len(response.warnings) > 0
    assert "A301" in response.warnings[0]


@pytest.mark.asyncio
async def test_stitch_plans_all_clipped_raises_400():
    """Test that clipping all walls raises ValueError."""
    # Arrange
    # Create a plan with walls that will be completely clipped
    walls = [
        Wall(
            id="wall_1",
            points=[
                Point2D(x=0.1, y=0.1),
                Point2D(x=0.2, y=0.1),
            ],
            thickness=0.2,
        )
    ]
    mock_reconstruction = create_mock_reconstruction(1, rooms=[], walls=walls)

    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=mock_reconstruction)

    service = StitchingService(mock_repo)

    # Clip polygon that covers entire plan
    request = StitchingRequest(
        name="Over-clipped",
        building_id="building-uuid",
        floor_number=1,
        source_plans=[
            SourcePlanInput(
                reconstruction_id="1",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[
                    ClipPolygonInput(
                        type="subtract",
                        points=[
                            (0.0, 0.0),
                            (1000.0, 0.0),
                            (1000.0, 800.0),
                            (0.0, 800.0),
                        ],
                    )
                ],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=0,
            ),
            SourcePlanInput(
                reconstruction_id="1",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[
                    ClipPolygonInput(
                        type="subtract",
                        points=[
                            (0.0, 0.0),
                            (1000.0, 0.0),
                            (1000.0, 800.0),
                            (0.0, 800.0),
                        ],
                    )
                ],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=1,
            ),
        ],
    )

    # Act & Assert
    with pytest.raises(ValueError, match="No walls remaining"):
        await service.stitch_plans(request, user_id=1)


@pytest.mark.asyncio
async def test_stitch_plans_saves_reconstruction_correctly():
    """Test that stitched reconstruction is saved with correct data."""
    # Arrange
    mock_repo = MagicMock()
    recon1 = create_mock_reconstruction(1, rooms=["A301"])
    recon2 = create_mock_reconstruction(2, rooms=["A302"])
    mock_repo.get_by_id = AsyncMock(
        side_effect=[
            recon1,
            recon2,
            recon1,
        ]
    )

    new_reconstruction = create_mock_reconstruction(3)
    new_reconstruction.name = "Saved Merge"
    mock_repo.create_reconstruction = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_name = AsyncMock(return_value=new_reconstruction)
    mock_repo.update_vectorization_data = AsyncMock(return_value=new_reconstruction)

    service = StitchingService(mock_repo)

    request = StitchingRequest(
        name="Saved Merge",
        building_id="building-uuid",
        floor_number=5,
        source_plans=[
            SourcePlanInput(
                reconstruction_id="1",
                transform=TransformInput(
                    translate_x=0,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=0,
            ),
            SourcePlanInput(
                reconstruction_id="2",
                transform=TransformInput(
                    translate_x=500,
                    translate_y=0,
                    scale_x=1.0,
                    scale_y=1.0,
                    rotation_deg=0,
                ),
                clip_polygons=[],
                rect_crop=None,
                image_width_px=1000,
                image_height_px=800,
                z_index=1,
            ),
        ],
    )

    # Act
    response = await service.stitch_plans(request, user_id=42)

    # Assert
    # Verify create_reconstruction was called with correct params
    mock_repo.create_reconstruction.assert_called_once()
    call_kwargs = mock_repo.create_reconstruction.call_args[1]
    assert call_kwargs["user_id"] == 42
    assert call_kwargs["status"] == 3

    # Verify update_name was called
    mock_repo.update_name.assert_called_once_with(
        new_reconstruction.id, "Saved Merge"
    )

    # Verify update_vectorization_data was called
    mock_repo.update_vectorization_data.assert_called_once()
    vectorization_json = mock_repo.update_vectorization_data.call_args[0][1]
    vectorization_data = json.loads(vectorization_json)
    assert "walls" in vectorization_data
    assert "rooms" in vectorization_data

    # Verify response
    assert response.id == new_reconstruction.id
    assert response.name == "Saved Merge"
    assert response.floor_number == 5
