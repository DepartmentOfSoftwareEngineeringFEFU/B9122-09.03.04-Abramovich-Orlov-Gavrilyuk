"""
Tests for SectionService.

All repositories are mocked via AsyncMock — no DB.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import FloorNotFoundError, SectionValidationError
from app.models.sections import ReplaceSectionsRequest, SectionPayloadItem, SectionGeometry
from app.services.section_service import SectionService


# Helpers

_GEOMETRY = SectionGeometry(points=[[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]])


def _make_floor(id: int = 101) -> MagicMock:
    f = MagicMock()
    f.id = id
    return f


def _make_reconstruction(id: int = 777, status: int = 3) -> MagicMock:
    r = MagicMock()
    r.id = id
    r.status = status
    return r


def _make_section_db(
    id: int = 1,
    floor_id: int = 101,
    number: int = 1,
    reconstruction=None,
) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.floor_id = floor_id
    s.number = number
    s.geometry = _GEOMETRY.model_dump()
    s.section_type = 1
    s.reconstruction = reconstruction
    s.reconstruction_id = reconstruction.id if reconstruction else None
    s.created_at = datetime(2026, 1, 1)
    s.updated_at = datetime(2026, 1, 1)
    return s


def _make_svc(
    floor: MagicMock | None = _make_floor(),
    sections: list | None = None,
    reconstruction: MagicMock | None = None,
) -> SectionService:
    floor_repo = AsyncMock()
    section_repo = AsyncMock()
    reconstruction_repo = AsyncMock()

    floor_repo.get_by_id.return_value = floor
    section_repo.list_by_floor.return_value = sections or []
    section_repo.delete_all_for_floor.return_value = None
    section_repo.bulk_create.return_value = []
    # Expose session mock for commit
    section_repo._session = AsyncMock()
    reconstruction_repo.get_by_id.return_value = reconstruction

    return SectionService(
        floor_repo=floor_repo,
        section_repo=section_repo,
        reconstruction_repo=reconstruction_repo,
    )


def _items(*numbers: int, recon_id: int | None = None) -> list[SectionPayloadItem]:
    return [
        SectionPayloadItem(
            number=n,
            geometry=_GEOMETRY,
            section_type=1,
            reconstruction_id=recon_id,
        )
        for n in numbers
    ]


# Tests


@pytest.mark.asyncio
async def test_replace_sections_valid_payload_writes_all():
    """replace_sections with valid payload calls delete_all + bulk_create."""
    recon = _make_reconstruction(id=10)
    svc = _make_svc(reconstruction=recon)
    req = ReplaceSectionsRequest(
        sections=[
            SectionPayloadItem(number=1, geometry=_GEOMETRY, reconstruction_id=10),
            SectionPayloadItem(number=2, geometry=_GEOMETRY, reconstruction_id=None),
        ]
    )
    # list_by_floor after replace returns empty (mocked)
    svc._section_repo.list_by_floor.return_value = []

    await svc.replace_sections(floor_id=101, req=req)

    svc._section_repo.delete_all_for_floor.assert_awaited_once_with(101)
    svc._section_repo.bulk_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_sections_duplicate_number_raises_validation():
    """Duplicate section numbers in payload → SectionValidationError."""
    svc = _make_svc()
    req = ReplaceSectionsRequest(
        sections=[
            SectionPayloadItem(number=1, geometry=_GEOMETRY),
            SectionPayloadItem(number=1, geometry=_GEOMETRY),  # duplicate
        ]
    )
    with pytest.raises(SectionValidationError, match="Duplicate section number"):
        await svc.replace_sections(floor_id=101, req=req)

    # DB should not have been touched
    svc._section_repo.delete_all_for_floor.assert_not_awaited()


@pytest.mark.asyncio
async def test_replace_sections_allows_cross_floor_reconstruction():
    """reconstruction from a different floor is allowed."""
    # Reconstruction exists but belongs to a different floor — should NOT raise
    recon = _make_reconstruction(id=999)
    svc = _make_svc(reconstruction=recon)
    svc._section_repo.list_by_floor.return_value = []

    req = ReplaceSectionsRequest(
        sections=[SectionPayloadItem(number=1, geometry=_GEOMETRY, reconstruction_id=999)]
    )
    # Should succeed without raising
    await svc.replace_sections(floor_id=101, req=req)

    svc._section_repo.delete_all_for_floor.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_sections_duplicate_reconstruction_raises_validation():
    """Same reconstruction_id used twice in payload → SectionValidationError."""
    recon = _make_reconstruction(id=5)
    svc = _make_svc(reconstruction=recon)
    req = ReplaceSectionsRequest(
        sections=[
            SectionPayloadItem(number=1, geometry=_GEOMETRY, reconstruction_id=5),
            SectionPayloadItem(number=2, geometry=_GEOMETRY, reconstruction_id=5),  # dup
        ]
    )
    with pytest.raises(SectionValidationError, match="already used"):
        await svc.replace_sections(floor_id=101, req=req)


@pytest.mark.asyncio
async def test_replace_sections_missing_floor_raises_not_found():
    """replace_sections raises FloorNotFoundError when floor does not exist."""
    svc = _make_svc(floor=None)  # floor_repo.get_by_id returns None
    req = ReplaceSectionsRequest(sections=[])

    with pytest.raises(FloorNotFoundError):
        await svc.replace_sections(floor_id=999, req=req)


@pytest.mark.asyncio
async def test_replace_sections_transactional_rollback_on_error():
    """If bulk_create raises, delete_all was already called — shows atomicity concern.

    The service calls delete_all then bulk_create within the same session.
    We verify that when bulk_create raises, the exception propagates up.
    (Session-level rollback is handled by the outer request lifecycle.)
    """
    svc = _make_svc()
    svc._section_repo.bulk_create.side_effect = RuntimeError("DB error")
    recon = _make_reconstruction(id=1)
    svc._reconstruction_repo.get_by_id.return_value = recon

    req = ReplaceSectionsRequest(
        sections=[SectionPayloadItem(number=1, geometry=_GEOMETRY, reconstruction_id=1)]
    )
    with pytest.raises(RuntimeError, match="DB error"):
        await svc.replace_sections(floor_id=101, req=req)

    # delete_all was called before the failure
    svc._section_repo.delete_all_for_floor.assert_awaited_once()


@pytest.mark.asyncio
async def test_replace_sections_empty_payload_clears_all():
    """replace_sections with empty list deletes all and inserts nothing."""
    svc = _make_svc()
    svc._section_repo.list_by_floor.return_value = []

    req = ReplaceSectionsRequest(sections=[])
    result = await svc.replace_sections(floor_id=101, req=req)

    svc._section_repo.delete_all_for_floor.assert_awaited_once_with(101)
    svc._section_repo.bulk_create.assert_not_awaited()
    assert result == []
