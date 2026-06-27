"""
Tests for BuildingService.

All repositories are mocked via AsyncMock — no DB.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BuildingDuplicateCodeError
from app.models.buildings import BuildingCreateRequest
from app.services.building_service import BuildingService


# Helpers


def _make_building(
    id: int = 1,
    code: str = "D",
    name: str = "Корпус D",
    address: str | None = None,
) -> MagicMock:
    b = MagicMock()
    b.id = id
    b.code = code
    b.name = name
    b.address = address
    b.created_at = datetime(2026, 1, 1)
    b.floors = []
    return b


def _make_section(
    id: int = 1,
    reconstruction_id: int | None = None,
    reconstruction_status: int | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.reconstruction_id = reconstruction_id
    s.section_type = 1
    # geometry must be dict or None (SectionPublic accepts Optional[dict])
    s.geometry = {"points": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]]}
    if reconstruction_status is not None:
        s.reconstruction = MagicMock()
        s.reconstruction.id = reconstruction_id
        s.reconstruction.status = reconstruction_status
    else:
        s.reconstruction = None
    return s


def _make_svc(
    buildings: list | None = None,
    floors: list | None = None,
    sections: list | None = None,
) -> BuildingService:
    building_repo = AsyncMock()
    floor_repo = AsyncMock()
    section_repo = AsyncMock()
    reconstruction_repo = AsyncMock()

    building_repo.list_all.return_value = buildings or []
    building_repo.get_by_code.return_value = None  # default: no duplicate
    building_repo.create.return_value = _make_building()
    floor_repo.list_by_building.return_value = floors or []
    section_repo.list_by_floor.return_value = sections or []

    return BuildingService(
        building_repo=building_repo,
        floor_repo=floor_repo,
        section_repo=section_repo,
        reconstruction_repo=reconstruction_repo,
    )


# Tests


@pytest.mark.asyncio
async def test_create_building_valid_data_succeeds():
    """Happy path: create building returns BuildingResponse with id."""
    svc = _make_svc()
    req = BuildingCreateRequest(code="D", name="Корпус D")

    result = await svc.create_building(req)

    assert result.id == 1
    assert result.code == "D"
    svc._building_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_building_duplicate_code_raises_conflict():
    """If code already exists → BuildingDuplicateCodeError raised."""
    svc = _make_svc()
    svc._building_repo.get_by_code.return_value = _make_building(code="D")

    req = BuildingCreateRequest(code="D", name="Дубликат")
    with pytest.raises(BuildingDuplicateCodeError):
        await svc.create_building(req)

    # create should NOT have been called
    svc._building_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_building_lowercase_code_normalized_to_upper():
    """Pydantic validator normalises code to uppercase before reaching service."""
    svc = _make_svc()
    req = BuildingCreateRequest(code="d", name="Корпус d")

    # Pydantic @field_validator converts "d" → "D"
    assert req.code == "D"

    result = await svc.create_building(req)
    assert result.code == "D"


@pytest.mark.asyncio
async def test_list_published_includes_complete_building():
    """Building with a Done-status section appears in published list."""
    building = _make_building(id=42, code="D", name="Корпус D")
    done_section = _make_section(id=1, reconstruction_id=777, reconstruction_status=3)

    floor = MagicMock()
    floor.id = 101
    floor.number = 7

    building_repo = AsyncMock()
    floor_repo = AsyncMock()
    section_repo = AsyncMock()
    reconstruction_repo = AsyncMock()

    building_repo.list_all.return_value = [building]
    floor_repo.list_by_building.return_value = [floor]
    section_repo.list_by_floor.return_value = [done_section]

    # Need mesh info on reconstruction
    done_section.reconstruction.mesh_file_id_glb = "abc.glb"

    svc = BuildingService(building_repo, floor_repo, section_repo, reconstruction_repo)
    result = await svc.list_published()

    assert len(result) == 1
    assert result[0].id == 42
    assert result[0].code == "D"
    assert len(result[0].floors) == 1
    assert len(result[0].floors[0].sections) == 1


@pytest.mark.asyncio
async def test_list_published_excludes_empty_building():
    """Building with no floors at all must not appear in published list."""
    building = _make_building(id=1, code="A")

    building_repo = AsyncMock()
    floor_repo = AsyncMock()
    section_repo = AsyncMock()
    reconstruction_repo = AsyncMock()

    building_repo.list_all.return_value = [building]
    floor_repo.list_by_building.return_value = []  # no floors
    section_repo.list_by_floor.return_value = []

    svc = BuildingService(building_repo, floor_repo, section_repo, reconstruction_repo)
    result = await svc.list_published()

    assert result == []


@pytest.mark.asyncio
async def test_list_published_excludes_floor_without_sections():
    """Floor that exists but has no sections must not publish the building."""
    building = _make_building(id=2, code="B")
    floor = MagicMock()
    floor.id = 200
    floor.number = 3

    building_repo = AsyncMock()
    floor_repo = AsyncMock()
    section_repo = AsyncMock()
    reconstruction_repo = AsyncMock()

    building_repo.list_all.return_value = [building]
    floor_repo.list_by_building.return_value = [floor]
    section_repo.list_by_floor.return_value = []  # no sections

    svc = BuildingService(building_repo, floor_repo, section_repo, reconstruction_repo)
    result = await svc.list_published()

    assert result == []


@pytest.mark.asyncio
async def test_list_published_excludes_section_with_pending_reconstruction():
    """Section with reconstruction.status != Done must not publish the building."""
    building = _make_building(id=3, code="C")
    floor = MagicMock()
    floor.id = 300
    floor.number = 5

    pending_section = _make_section(
        id=10, reconstruction_id=555, reconstruction_status=2  # Processing, not Done
    )

    building_repo = AsyncMock()
    floor_repo = AsyncMock()
    section_repo = AsyncMock()
    reconstruction_repo = AsyncMock()

    building_repo.list_all.return_value = [building]
    floor_repo.list_by_building.return_value = [floor]
    section_repo.list_by_floor.return_value = [pending_section]

    svc = BuildingService(building_repo, floor_repo, section_repo, reconstruction_repo)
    result = await svc.list_published()

    assert result == []
