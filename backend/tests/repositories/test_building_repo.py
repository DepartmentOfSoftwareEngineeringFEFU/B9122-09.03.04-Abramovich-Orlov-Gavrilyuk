"""
Unit tests for BuildingRepository.
"""

import pytest

from app.core.exceptions import BuildingDuplicateCodeError
from app.db.repositories.building_repo import BuildingRepository
from tests.repositories.conftest import building_factory


@pytest.mark.asyncio
async def test_building_repo_get_by_code_returns_entity(db_session):
    await building_factory(db_session, code="T1", name="Test 1")
    repo = BuildingRepository(db_session)
    result = await repo.get_by_code("T1")
    assert result is not None
    assert result.code == "T1"


@pytest.mark.asyncio
async def test_building_repo_get_by_code_missing_returns_none(db_session):
    repo = BuildingRepository(db_session)
    result = await repo.get_by_code("ZZNOTEXIST")
    assert result is None


@pytest.mark.asyncio
async def test_building_repo_get_by_code_lowercase_returns_entity(db_session):
    await building_factory(db_session, code="LC", name="Lower Case Test")
    repo = BuildingRepository(db_session)
    result = await repo.get_by_code("lc")
    assert result is not None
    assert result.code == "LC"


@pytest.mark.asyncio
async def test_building_repo_create_duplicate_code_raises_integrity_error(db_session):
    await building_factory(db_session, code="DUP", name="First")
    repo = BuildingRepository(db_session)
    with pytest.raises(BuildingDuplicateCodeError):
        await repo.create(code="DUP", name="Second duplicate")
