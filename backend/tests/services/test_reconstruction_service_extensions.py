"""
Tests for extensions to ReconstructionService.

Specifically tests the new `list` method with `unbound=True` filter.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.reconstruction_service import ReconstructionService


def _make_svc() -> ReconstructionService:
    repo = AsyncMock()
    storage = AsyncMock()
    return ReconstructionService(repo=repo, storage=storage)


def _make_reconstruction(id: int, status: int, has_section: bool = False) -> MagicMock:
    r = MagicMock()
    r.id = id
    r.status = status
    r.section = MagicMock() if has_section else None
    r.name = f"recon-{id}"
    return r


@pytest.mark.asyncio
async def test_list_unbound_excludes_non_done_reconstructions():
    """list(unbound=True) must only include status=Done without a section.

    The repository's get_saved() already implements this via a LEFT OUTER JOIN.
    We verify the service passes unbound=True correctly to the repo.
    """
    svc = _make_svc()
    done_unbound = _make_reconstruction(id=1, status=3, has_section=False)
    svc._repo.get_saved.return_value = [done_unbound]

    result = await svc.list(unbound=True)

    svc._repo.get_saved.assert_awaited_once_with(
        floor_id=None,
        status=None,
        unbound=True,
        search=None,
    )
    assert len(result) == 1
    assert result[0].status == 3
    assert result[0].section is None


@pytest.mark.asyncio
async def test_list_with_status_filter_passes_to_repo():
    """list(status=3) passes status filter to repository."""
    svc = _make_svc()
    svc._repo.get_saved.return_value = []

    await svc.list(status=3)

    svc._repo.get_saved.assert_awaited_once_with(
        floor_id=None,
        status=3,
        unbound=False,
        search=None,
    )


@pytest.mark.asyncio
async def test_list_with_floor_id_filter_passes_to_repo():
    """list(floor_id=101) passes floor_id filter to repository."""
    svc = _make_svc()
    svc._repo.get_saved.return_value = []

    await svc.list(floor_id=101)

    svc._repo.get_saved.assert_awaited_once_with(
        floor_id=101,
        status=None,
        unbound=False,
        search=None,
    )
