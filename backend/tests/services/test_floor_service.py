"""
Tests for FloorService.

All repositories are mocked via AsyncMock — no DB.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BuildingNotFoundError, FloorDuplicateNumberError
from app.models.floors import FloorCreateRequest
from app.services.floor_service import FloorService


# Helpers


def _make_building(id: int = 1, code: str = "D") -> MagicMock:
    b = MagicMock()
    b.id = id
    b.code = code
    b.name = f"Корпус {code}"
    b.address = None
    b.created_at = datetime(2026, 1, 1)
    return b


def _make_floor(id: int = 101, building_id: int = 1, number: int = 7) -> MagicMock:
    f = MagicMock()
    f.id = id
    f.building_id = building_id
    f.number = number
    f.created_at = datetime(2026, 1, 1)
    f.building = _make_building(id=building_id)
    f.schema_image_id = None
    f.schema_image = None
    f.schema_crop_bbox = None
    f.wall_polygons = None
    f.mask_file_id = None
    f.mask_file = None
    return f


def _make_svc(building=None, existing_floor=None) -> FloorService:
    building_repo = AsyncMock()
    floor_repo = AsyncMock()

    building_repo.get_by_id.return_value = building
    floor_repo.get_by_building_and_number.return_value = existing_floor
    floor_repo.create.return_value = _make_floor()
    floor_repo.count_sections.return_value = 0
    floor_repo.count_unbound_reconstructions.return_value = 0

    return FloorService(building_repo=building_repo, floor_repo=floor_repo)


# Tests


@pytest.mark.asyncio
async def test_create_floor_missing_building_raises_not_found():
    """create_floor raises BuildingNotFoundError when building does not exist."""
    svc = _make_svc(building=None)  # building_repo.get_by_id returns None

    req = FloorCreateRequest(number=7)
    with pytest.raises(BuildingNotFoundError):
        await svc.create_floor(building_id=999, req=req)

    svc._floor_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_floor_duplicate_number_raises_conflict():
    """create_floor raises FloorDuplicateNumberError when number already taken."""
    building = _make_building(id=1, code="D")
    existing = _make_floor(id=50, building_id=1, number=7)

    svc = _make_svc(building=building, existing_floor=existing)

    req = FloorCreateRequest(number=7)
    with pytest.raises(FloorDuplicateNumberError):
        await svc.create_floor(building_id=1, req=req)

    svc._floor_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_id_exposes_mask_file_url():
    """get_by_id surfaces mask_file_url from the linked mask_file relationship."""
    floor = _make_floor(id=101, building_id=1, number=7)
    floor.mask_file_id = "mask-uuid"
    floor.mask_file = MagicMock()
    floor.mask_file.url = "/api/v1/uploads/masks/mask-uuid.png"
    svc = _make_svc(building=_make_building(id=1))
    svc._floor_repo.get_by_id.return_value = floor

    resp = await svc.get_by_id(101)

    assert resp.mask_file_id == "mask-uuid"
    assert resp.mask_file_url == "/api/v1/uploads/masks/mask-uuid.png"
