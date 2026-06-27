"""
Shared fixtures for repository tests.

Uses an in-memory SQLite database via aiosqlite.
All models imported via app.db.base to ensure metadata is populated.
"""

import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
import app.db.base  # noqa: F401 — registers all ORM models with Base.metadata

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


# Data factories


async def building_factory(
    session: AsyncSession,
    code: str = "D",
    name: str = "Корпус D",
    address: str | None = None,
):
    """Create and persist a Building, return the ORM instance."""
    from app.db.models.building import Building

    b = Building(code=code.upper(), name=name, address=address)
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return b


async def floor_factory(
    session: AsyncSession,
    building_id: int,
    number: int = 1,
):
    """Create and persist a Floor, return the ORM instance."""
    from app.db.models.building import Floor

    f = Floor(building_id=building_id, number=number)
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


async def reconstruction_factory(
    session: AsyncSession,
    plan_file_id: str = "plan-file-uuid",
    status: int = 3,
    floor_id: int | None = None,
    name: str | None = "Test Reconstruction",
):
    """Create and persist a Reconstruction, return the ORM instance."""
    from datetime import datetime

    from app.db.models.reconstruction import Reconstruction, UploadedFile

    # Ensure plan UploadedFile exists
    existing = await session.get(UploadedFile, plan_file_id)
    if not existing:
        uf = UploadedFile(
            id=plan_file_id,
            filename="plan.jpg",
            file_path=f"/uploads/{plan_file_id}.jpg",
            url=f"/uploads/{plan_file_id}.jpg",
            file_type=1,
        )
        session.add(uf)
        await session.flush()

    r = Reconstruction(
        plan_file_id=plan_file_id,
        status=status,
        floor_id=floor_id,
        name=name,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    return r


async def section_factory(
    session: AsyncSession,
    floor_id: int,
    number: int = 1,
    reconstruction_id: int | None = None,
):
    """Create and persist a Section, return the ORM instance."""
    from app.db.models.section import Section

    s = Section(
        floor_id=floor_id,
        number=number,
        geometry={"points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]},
        section_type=1,
        reconstruction_id=reconstruction_id,
    )
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s


async def connector_factory(
    session: AsyncSession,
    floor_id: int,
    points: list | None = None,
    height_m: float | None = None,
    thickness_m: float | None = None,
    connects: list | None = None,
):
    """Create and persist a FloorConnector, return the ORM instance."""
    from app.db.models.floor_connector import FloorConnector

    c = FloorConnector(
        floor_id=floor_id,
        points=points if points is not None else [[0.2, 0.2], [0.6, 0.2]],
        height_m=height_m,
        thickness_m=thickness_m,
        connects=connects,
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return c
