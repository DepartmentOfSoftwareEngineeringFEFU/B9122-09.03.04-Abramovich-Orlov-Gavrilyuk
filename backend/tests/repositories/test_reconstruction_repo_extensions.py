"""
Unit tests for new ReconstructionRepository methods (extensions).
"""

import pytest

from app.db.repositories.reconstruction_repo import ReconstructionRepository
from tests.repositories.conftest import (
    building_factory,
    floor_factory,
    reconstruction_factory,
    section_factory,
)


@pytest.mark.asyncio
async def test_reconstruction_repo_list_unbound_returns_only_unbound(db_session):
    """list_unbound_for_floor returns only Done reconstructions not linked to a section."""
    building = await building_factory(db_session, code="R1", name="Rec Test 1")
    floor = await floor_factory(db_session, building_id=building.id, number=1)

    unbound_rec = await reconstruction_factory(
        db_session,
        plan_file_id="plan-unbound-r1",
        status=3,
        floor_id=floor.id,
        name="Unbound",
    )
    bound_rec = await reconstruction_factory(
        db_session,
        plan_file_id="plan-bound-r1",
        status=3,
        floor_id=floor.id,
        name="Bound",
    )
    # Link bound_rec to a section
    await section_factory(
        db_session, floor_id=floor.id, number=1, reconstruction_id=bound_rec.id
    )

    repo = ReconstructionRepository(db_session)
    unbound = await repo.list_unbound_for_floor(floor.id)
    unbound_ids = {r.id for r in unbound}

    assert unbound_rec.id in unbound_ids
    assert bound_rec.id not in unbound_ids


@pytest.mark.asyncio
async def test_reconstruction_repo_list_unbound_returns_empty(db_session):
    """list_unbound_for_floor returns [] when all Done reconstructions are bound."""
    building = await building_factory(db_session, code="R2", name="Rec Test 2")
    floor = await floor_factory(db_session, building_id=building.id, number=1)

    rec = await reconstruction_factory(
        db_session,
        plan_file_id="plan-bound-r2",
        status=3,
        floor_id=floor.id,
        name="All Bound",
    )
    await section_factory(
        db_session, floor_id=floor.id, number=1, reconstruction_id=rec.id
    )

    repo = ReconstructionRepository(db_session)
    unbound = await repo.list_unbound_for_floor(floor.id)
    assert unbound == []
