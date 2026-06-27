import pytest
from app.db.repositories.reconstruction_repo import ReconstructionRepository


@pytest.mark.asyncio
async def test_repo_create_reconstruction_returns_with_status_2(db_session):
    repo = ReconstructionRepository(db_session)
    r = await repo.create_reconstruction("plan-id", "mask-id", user_id=1)
    assert r.id is not None
    assert r.status == 2


@pytest.mark.asyncio
async def test_repo_get_by_id_existing_returns_reconstruction(db_session):
    repo = ReconstructionRepository(db_session)
    created = await repo.create_reconstruction("plan-x", "mask-x", user_id=1)
    result = await repo.get_by_id(created.id)
    assert result is not None
    assert result.id == created.id


@pytest.mark.asyncio
async def test_repo_get_by_id_missing_returns_none(db_session):
    repo = ReconstructionRepository(db_session)
    result = await repo.get_by_id(99999)
    assert result is None


@pytest.mark.asyncio
async def test_repo_update_reconstruction_updates_mesh_fields(db_session):
    repo = ReconstructionRepository(db_session)
    created = await repo.create_reconstruction("plan-y", "mask-y", user_id=1)
    updated = await repo.update_mesh(created.id, "path.obj", "path.glb", status=3)
    assert updated.status == 3
    assert updated.mesh_file_id_glb == "path.glb"
