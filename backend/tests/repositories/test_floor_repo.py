"""
Unit tests for FloorRepository.
"""

import pytest

from app.db.repositories.floor_repo import FloorRepository
from tests.repositories.conftest import building_factory, floor_factory


@pytest.mark.asyncio
async def test_floor_repo_get_by_building_and_number_returns_entity(db_session):
    building = await building_factory(db_session, code="F1", name="Floor Test 1")
    await floor_factory(db_session, building_id=building.id, number=3)
    repo = FloorRepository(db_session)
    result = await repo.get_by_building_and_number(building.id, 3)
    assert result is not None
    assert result.number == 3
    assert result.building_id == building.id


@pytest.mark.asyncio
async def test_floor_repo_get_by_building_and_number_missing_returns_none(db_session):
    building = await building_factory(db_session, code="F2", name="Floor Test 2")
    repo = FloorRepository(db_session)
    result = await repo.get_by_building_and_number(building.id, 99)
    assert result is None


@pytest.mark.asyncio
async def test_floor_repo_list_by_building_returns_sorted_by_number(db_session):
    building = await building_factory(db_session, code="F3", name="Floor Test 3")
    # Create floors in reverse order to test sorting
    await floor_factory(db_session, building_id=building.id, number=5)
    await floor_factory(db_session, building_id=building.id, number=2)
    await floor_factory(db_session, building_id=building.id, number=8)
    repo = FloorRepository(db_session)
    floors = await repo.list_by_building(building.id)
    numbers = [f.number for f in floors]
    assert numbers == sorted(numbers)
    assert 2 in numbers
    assert 5 in numbers
    assert 8 in numbers
