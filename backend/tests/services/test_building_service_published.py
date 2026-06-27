"""
Tests for BuildingService.list_published — the data source for the public
GET /api/v1/buildings?published=true endpoint.

Verifies hierarchical filtering and that the public response
omits private fields like `address` and `created_at`.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.buildings import BuildingPublicResponse, FloorPublic, SectionPublic
from app.services.building_service import BuildingService


# Helpers


def _make_building(
    id: int = 1,
    code: str = "D",
    name: str = "Корпус D",
    address: str | None = "ул. Тестовая, 1",
) -> MagicMock:
    b = MagicMock()
    b.id = id
    b.code = code
    b.name = name
    b.address = address
    b.created_at = datetime(2026, 1, 1)
    return b


def _make_floor(id: int = 100, number: int = 7) -> MagicMock:
    f = MagicMock()
    f.id = id
    f.number = number
    return f


def _make_section(
    id: int = 1,
    reconstruction_id: int | None = None,
    reconstruction_status: int | None = None,
    mesh_file_id_glb: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.number = id
    s.reconstruction_id = reconstruction_id
    s.section_type = 1
    s.geometry = {"points": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]]}
    if reconstruction_status is not None:
        s.reconstruction = MagicMock()
        s.reconstruction.id = reconstruction_id
        s.reconstruction.status = reconstruction_status
        s.reconstruction.mesh_file_id_glb = mesh_file_id_glb
    else:
        s.reconstruction = None
    return s


def _make_svc(
    buildings: list | None = None,
    floors_by_building: dict[int, list] | None = None,
    sections_by_floor: dict[int, list] | None = None,
) -> BuildingService:
    building_repo = AsyncMock()
    floor_repo = AsyncMock()
    section_repo = AsyncMock()
    reconstruction_repo = AsyncMock()

    building_repo.list_all.return_value = buildings or []

    fbb = floors_by_building or {}
    sbf = sections_by_floor or {}

    async def _list_floors(b_id: int):
        return fbb.get(b_id, [])

    async def _list_sections(f_id: int):
        return sbf.get(f_id, [])

    floor_repo.list_by_building.side_effect = _list_floors
    section_repo.list_by_floor.side_effect = _list_sections

    return BuildingService(
        building_repo=building_repo,
        floor_repo=floor_repo,
        section_repo=section_repo,
        reconstruction_repo=reconstruction_repo,
    )


# Tests


@pytest.mark.asyncio
async def test_list_published_excludes_building_without_done_reconstruction():
    """Building whose only section has reconstruction.status != Done must be filtered out."""
    # Arrange
    building = _make_building(id=1, code="A", name="Корпус A")
    floor = _make_floor(id=10, number=1)
    pending_section = _make_section(
        id=1, reconstruction_id=42, reconstruction_status=2  # Processing, not Done
    )
    svc = _make_svc(
        buildings=[building],
        floors_by_building={1: [floor]},
        sections_by_floor={10: [pending_section]},
    )

    # Act
    result = await svc.list_published()

    # Assert
    assert result == []


@pytest.mark.asyncio
async def test_list_published_returns_building_with_done_section():
    """Building with at least one section whose reconstruction.status == Done is published."""
    # Arrange
    building = _make_building(id=1, code="D", name="Корпус D")
    floor = _make_floor(id=10, number=7)
    done_section = _make_section(
        id=1,
        reconstruction_id=42,
        reconstruction_status=3,  # Done
        mesh_file_id_glb="mesh-42.glb",
    )
    svc = _make_svc(
        buildings=[building],
        floors_by_building={1: [floor]},
        sections_by_floor={10: [done_section]},
    )

    # Act
    result = await svc.list_published()

    # Assert
    assert len(result) == 1
    assert isinstance(result[0], BuildingPublicResponse)
    assert result[0].id == 1
    assert result[0].code == "D"
    assert len(result[0].floors) == 1
    assert isinstance(result[0].floors[0], FloorPublic)
    assert len(result[0].floors[0].sections) == 1
    assert isinstance(result[0].floors[0].sections[0], SectionPublic)
    # URL is built from reconstruction_id, not from the raw mesh_file_id_glb value
    # (matches build_mesh_url() in reconstruction_service.py and the static mount in main.py)
    assert (
        result[0].floors[0].sections[0].mesh_url_glb
        == "/api/v1/uploads/models/reconstruction_42.glb"
    )


@pytest.mark.asyncio
async def test_list_published_response_omits_private_fields():
    """BuildingPublicResponse must not leak admin-only fields like address or created_at."""
    # Arrange
    building = _make_building(id=1, code="D", name="Корпус D", address="SECRET ADDRESS")
    floor = _make_floor(id=10, number=7)
    done_section = _make_section(
        id=1, reconstruction_id=42, reconstruction_status=3, mesh_file_id_glb="m.glb"
    )
    svc = _make_svc(
        buildings=[building],
        floors_by_building={1: [floor]},
        sections_by_floor={10: [done_section]},
    )

    # Act
    result = await svc.list_published()

    # Assert
    assert len(result) == 1
    serialised = result[0].model_dump()
    assert "address" not in serialised
    assert "created_at" not in serialised
    assert "SECRET ADDRESS" not in str(serialised)
