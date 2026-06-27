"""
Unit tests for FloorConnectorRepository plus round-trip checks for
the new JSON update methods on Section / Reconstruction repos.
"""

import pytest

from app.db.repositories.floor_connector_repo import FloorConnectorRepository
from app.db.repositories.floor_repo import FloorRepository
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.db.repositories.section_repo import SectionRepository
from tests.repositories.conftest import (
    building_factory,
    connector_factory,
    floor_factory,
    reconstruction_factory,
    section_factory,
)


@pytest.mark.asyncio
async def test_connector_repo_list_by_floor_returns_floor_connectors(db_session):
    building = await building_factory(db_session, code="C0", name="Conn Test 0")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    await connector_factory(db_session, floor_id=floor.id)
    await connector_factory(db_session, floor_id=floor.id)
    repo = FloorConnectorRepository(db_session)
    connectors = await repo.list_by_floor(floor.id)
    assert len(connectors) == 2
    assert all(c.floor_id == floor.id for c in connectors)


@pytest.mark.asyncio
async def test_connector_repo_replace_all_for_floor_replaces_old_rows(db_session):
    building = await building_factory(db_session, code="C1", name="Conn Test 1")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    old_points = [[0.99, 0.99], [0.88, 0.88]]
    await connector_factory(db_session, floor_id=floor.id, points=old_points)
    repo = FloorConnectorRepository(db_session)

    new_items = [
        {"points": [[0.1, 0.1], [0.5, 0.5]]},
        {"points": [[0.2, 0.2], [0.8, 0.8]]},
    ]
    created = await repo.replace_all_for_floor(floor.id, new_items)

    assert len(created) == 2
    remaining = await repo.list_by_floor(floor.id)
    # Old row content is gone; only the new items remain (SQLite may reuse PKs,
    # so compare by content, not by id).
    remaining_points = [c.points for c in remaining]
    assert old_points not in remaining_points
    assert remaining_points == [item["points"] for item in new_items]


@pytest.mark.asyncio
async def test_connector_repo_replace_all_for_floor_empty_clears(db_session):
    building = await building_factory(db_session, code="C2", name="Conn Test 2")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    await connector_factory(db_session, floor_id=floor.id)
    await connector_factory(db_session, floor_id=floor.id)
    repo = FloorConnectorRepository(db_session)

    created = await repo.replace_all_for_floor(floor.id, [])

    assert created == []
    remaining = await repo.list_by_floor(floor.id)
    assert remaining == []


@pytest.mark.asyncio
async def test_connector_repo_replace_all_for_floor_keeps_other_floors(db_session):
    building = await building_factory(db_session, code="C3", name="Conn Test 3")
    floor_a = await floor_factory(db_session, building_id=building.id, number=1)
    floor_b = await floor_factory(db_session, building_id=building.id, number=2)
    await connector_factory(db_session, floor_id=floor_b.id)
    repo = FloorConnectorRepository(db_session)

    await repo.replace_all_for_floor(floor_a.id, [{"points": [[0.0, 0.0], [1.0, 1.0]]}])

    assert len(await repo.list_by_floor(floor_a.id)) == 1
    assert len(await repo.list_by_floor(floor_b.id)) == 1  # untouched


@pytest.mark.asyncio
async def test_connector_repo_cascade_on_floor_delete_removes_connectors(db_session):
    building = await building_factory(db_session, code="C4", name="Conn Test 4")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    await connector_factory(db_session, floor_id=floor.id)
    await connector_factory(db_session, floor_id=floor.id)
    conn_repo = FloorConnectorRepository(db_session)
    assert len(await conn_repo.list_by_floor(floor.id)) == 2

    floor_repo = FloorRepository(db_session)
    await floor_repo.delete(floor.id)

    # ORM cascade should have removed connectors with the floor
    assert await conn_repo.list_by_floor(floor.id) == []


@pytest.mark.asyncio
async def test_connector_repo_replace_round_trips_json_unchanged(db_session):
    building = await building_factory(db_session, code="C5", name="Conn Test 5")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    repo = FloorConnectorRepository(db_session)
    item = {
        "points": [[0.12, 0.34], [0.56, 0.78], [0.9, 0.1]],
        "height_m": 2.7,
        "thickness_m": 0.15,
        "connects": [11, 22],
    }

    created = await repo.replace_all_for_floor(floor.id, [item])

    assert len(created) == 1
    c = created[0]
    assert c.points == item["points"]
    assert c.height_m == item["height_m"]
    assert c.thickness_m == item["thickness_m"]
    assert c.connects == item["connects"]
    # Verify persisted values survive a fresh read
    reread = (await repo.list_by_floor(floor.id))[0]
    assert reread.points == item["points"]
    assert reread.connects == item["connects"]


@pytest.mark.asyncio
async def test_reconstruction_repo_update_control_points_round_trips(db_session):
    building = await building_factory(db_session, code="C6", name="Conn Test 6")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    rec = await reconstruction_factory(
        db_session, plan_file_id="plan-cp-c6", status=3, floor_id=floor.id
    )
    repo = ReconstructionRepository(db_session)
    points = [{"id": "p1", "x": 0.25, "y": 0.5}, {"id": "p2", "x": 0.75, "y": 0.9}]

    updated = await repo.update_control_points(rec.id, points)

    assert updated is not None
    assert updated.control_points == points


@pytest.mark.asyncio
async def test_reconstruction_repo_update_control_points_missing_returns_none(db_session):
    repo = ReconstructionRepository(db_session)
    result = await repo.update_control_points(999999, [{"id": "p1", "x": 0.1, "y": 0.2}])
    assert result is None


@pytest.mark.asyncio
async def test_section_repo_update_master_control_points_round_trips(db_session):
    building = await building_factory(db_session, code="C7", name="Conn Test 7")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    section = await section_factory(db_session, floor_id=floor.id, number=1)
    repo = SectionRepository(db_session)
    points = [
        {"point_id": "a", "x": 0.1, "y": 0.2},
        {"point_id": "b", "x": 0.3, "y": 0.4},
    ]

    updated = await repo.update_master_control_points(section.id, points)

    assert updated is not None
    assert updated.control_points == points


@pytest.mark.asyncio
async def test_section_repo_update_transform_round_trips(db_session):
    building = await building_factory(db_session, code="C8", name="Conn Test 8")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    section = await section_factory(db_session, floor_id=floor.id, number=1)
    repo = SectionRepository(db_session)
    transform = {
        "scale": 1.25,
        "tx": 10.0,
        "ty": -5.0,
        "residual_rms_px": 0.42,
        "n_points": 3,
        "solved_at": "2026-05-30T00:00:00",
    }

    updated = await repo.update_transform(section.id, transform)

    assert updated is not None
    assert updated.transform == transform


@pytest.mark.asyncio
async def test_section_repo_update_transform_none_clears(db_session):
    building = await building_factory(db_session, code="C9", name="Conn Test 9")
    floor = await floor_factory(db_session, building_id=building.id, number=1)
    section = await section_factory(db_session, floor_id=floor.id, number=1)
    repo = SectionRepository(db_session)
    await repo.update_transform(section.id, {"scale": 1.0, "tx": 0.0, "ty": 0.0})

    cleared = await repo.update_transform(section.id, None)

    assert cleared is not None
    assert cleared.transform is None


@pytest.mark.asyncio
async def test_section_repo_update_transform_missing_returns_none(db_session):
    repo = SectionRepository(db_session)
    result = await repo.update_transform(999999, {"scale": 1.0, "tx": 0.0, "ty": 0.0})
    assert result is None
