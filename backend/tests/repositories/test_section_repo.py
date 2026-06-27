"""
Unit tests for SectionRepository.
"""

import pytest

from app.db.repositories.section_repo import SectionRepository
from tests.repositories.conftest import (
    building_factory,
    floor_factory,
    reconstruction_factory,
    section_factory,
)


@pytest.mark.asyncio
async def test_section_repo_list_by_floor_includes_reconstructions(db_session):
    building = await building_factory(db_session, code="S1", name="Section Test 1")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    rec = await reconstruction_factory(
        db_session,
        plan_file_id="plan-s1",
        status=3,
        floor_id=floor.id,
        name="Sec Rec 1",
    )
    await section_factory(
        db_session, floor_id=floor.id, number=1, reconstruction_id=rec.id
    )
    repo = SectionRepository(db_session)
    sections = await repo.list_by_floor(floor.id)
    assert len(sections) >= 1
    sec = next(s for s in sections if s.number == 1)
    assert sec.reconstruction is not None
    assert sec.reconstruction.id == rec.id


@pytest.mark.asyncio
async def test_section_repo_delete_all_for_floor_keeps_other_floors(db_session):
    building = await building_factory(db_session, code="S2", name="Section Test 2")
    floor_a = await floor_factory(db_session, building_id=building.id, number=1)
    floor_b = await floor_factory(db_session, building_id=building.id, number=2)
    await section_factory(db_session, floor_id=floor_a.id, number=1)
    await section_factory(db_session, floor_id=floor_b.id, number=1)
    repo = SectionRepository(db_session)
    await repo.delete_all_for_floor(floor_a.id)
    await db_session.commit()
    sections_a = await repo.list_by_floor(floor_a.id)
    sections_b = await repo.list_by_floor(floor_b.id)
    assert len(sections_a) == 0
    assert len(sections_b) >= 1


@pytest.mark.asyncio
async def test_section_repo_bulk_create_inserts_all(db_session):
    building = await building_factory(db_session, code="S3", name="Section Test 3")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    items = [
        {
            "floor_id": floor.id,
            "number": i,
            "geometry": {"points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]},
            "section_type": 1,
            "reconstruction_id": None,
        }
        for i in range(1, 4)
    ]
    repo = SectionRepository(db_session)
    created = await repo.bulk_create(items)
    await db_session.commit()
    assert len(created) == 3
    numbers = {s.number for s in created}
    assert numbers == {1, 2, 3}
