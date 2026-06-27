"""
Tests for FloorTransitionService — mocks FloorTransitionRepository and ReconstructionRepository.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.floor_transition import FloorTransitionRequest
from app.services.floor_transition_service import FloorTransitionService
from app.core.exceptions import FloorTransitionNotFoundError, FloorTransitionError


def _make_recon(id: int, building_id: str = "A"):
    r = MagicMock()
    r.id = id
    r.building_id = building_id
    r.name = f"Floor {id}"
    r.floor_number = id
    r.mask_file_id = f"mask_{id}"
    return r


def _make_transition_mock(id: int = 1):
    t = MagicMock()
    t.id = id
    t.name = "Лестница А"
    t.building_id = "A"
    t.from_reconstruction_id = 1
    t.from_x = 0.25
    t.from_y = 0.60
    t.to_reconstruction_id = 2
    t.to_x = 0.30
    t.to_y = 0.65
    return t


def _make_request(from_id: int = 1, to_id: int = 2) -> FloorTransitionRequest:
    return FloorTransitionRequest(
        name="Лестница А",
        from_reconstruction_id=from_id,
        from_x=0.25,
        from_y=0.60,
        to_reconstruction_id=to_id,
        to_x=0.30,
        to_y=0.65,
    )


@pytest.mark.asyncio
async def test_create_transition_valid_data_returns_entity():
    # Arrange
    repo = AsyncMock()
    recon_repo = AsyncMock()
    recon_repo.get_by_id.side_effect = lambda id: _make_recon(id)
    expected = _make_transition_mock()
    repo.create.return_value = expected
    service = FloorTransitionService(repo, recon_repo)

    # Act
    result = await service.create(_make_request())

    # Assert
    assert result is expected
    repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_transition_same_reconstruction_raises_error():
    # Pydantic model_validator fires before service is called
    with pytest.raises(Exception):
        FloorTransitionRequest(
            name="X",
            from_reconstruction_id=1,
            from_x=0.1,
            from_y=0.1,
            to_reconstruction_id=1,
            to_x=0.2,
            to_y=0.2,
        )


@pytest.mark.asyncio
async def test_create_transition_normalized_coords_stored():
    # Arrange
    repo = AsyncMock()
    recon_repo = AsyncMock()
    recon_repo.get_by_id.side_effect = lambda id: _make_recon(id)
    repo.create.return_value = _make_transition_mock()
    service = FloorTransitionService(repo, recon_repo)
    request = _make_request()

    # Act
    await service.create(request)

    # Assert — coords passed as-is (already normalized by Pydantic)
    call_kwargs = repo.create.call_args.kwargs
    assert call_kwargs["from_x"] == 0.25
    assert call_kwargs["from_y"] == 0.60
    assert call_kwargs["to_x"] == 0.30
    assert call_kwargs["to_y"] == 0.65


@pytest.mark.asyncio
async def test_get_by_building_returns_transitions():
    # Arrange
    repo = AsyncMock()
    recon_repo = AsyncMock()
    transitions = [_make_transition_mock(1), _make_transition_mock(2)]
    repo.get_by_building.return_value = transitions
    service = FloorTransitionService(repo, recon_repo)

    # Act
    result = await service.get_by_building("A")

    # Assert
    assert result == transitions
    repo.get_by_building.assert_called_once_with("A")


@pytest.mark.asyncio
async def test_get_by_building_empty_returns_empty_list():
    # Arrange
    repo = AsyncMock()
    recon_repo = AsyncMock()
    repo.get_by_building.return_value = []
    service = FloorTransitionService(repo, recon_repo)

    # Act
    result = await service.get_by_building("Z")

    # Assert
    assert result == []


@pytest.mark.asyncio
async def test_delete_existing_transition_returns_true():
    # Arrange
    repo = AsyncMock()
    recon_repo = AsyncMock()
    repo.delete.return_value = True
    service = FloorTransitionService(repo, recon_repo)

    # Act — should not raise
    await service.delete(1)

    # Assert
    repo.delete.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_delete_nonexistent_raises_not_found():
    # Arrange
    repo = AsyncMock()
    recon_repo = AsyncMock()
    repo.delete.return_value = False
    service = FloorTransitionService(repo, recon_repo)

    # Act / Assert
    with pytest.raises(FloorTransitionNotFoundError):
        await service.delete(999)
