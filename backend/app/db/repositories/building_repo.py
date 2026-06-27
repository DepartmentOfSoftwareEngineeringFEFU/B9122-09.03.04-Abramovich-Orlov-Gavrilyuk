"""
Repository for Building entities.

Pure data access — no business logic.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BuildingDuplicateCodeError, BuildingNotFoundError
from app.db.models.building import Building
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BuildingRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        code: str,
        name: str,
        address: Optional[str] = None,
    ) -> Building:
        """INSERT a new building. Raises BuildingDuplicateCodeError on duplicate code."""
        logger.debug("create building: code=%s, name=%s", code, name)
        building = Building(code=code.upper(), name=name, address=address)
        self._session.add(building)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise BuildingDuplicateCodeError(code)
        await self._session.refresh(building)
        return building

    async def get_by_id(self, building_id: int) -> Optional[Building]:
        """SELECT by PK. Returns None if not found."""
        logger.debug("get_by_id: building_id=%d", building_id)
        result = await self._session.execute(
            select(Building).where(Building.id == building_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[Building]:
        """SELECT by code (case-insensitive). Returns None if not found."""
        logger.debug("get_by_code: code=%s", code)
        result = await self._session.execute(
            select(Building).where(func.upper(Building.code) == code.upper())
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Building]:
        """SELECT all buildings, eager-loading floors."""
        logger.debug("list_all buildings")
        result = await self._session.execute(
            select(Building).options(selectinload(Building.floors))
        )
        return list(result.scalars().all())

    async def update(self, building_id: int, **fields: object) -> Building:
        """Partial UPDATE. Raises BuildingNotFoundError if not found."""
        logger.debug("update building: building_id=%d, fields=%s", building_id, list(fields))
        building = await self._session.get(Building, building_id)
        if not building:
            raise BuildingNotFoundError(building_id)
        for key, value in fields.items():
            setattr(building, key, value)
        await self._session.commit()
        await self._session.refresh(building)
        return building

    async def delete(self, building_id: int) -> None:
        """DELETE by PK. Cascade handled by ORM relationship. Raises BuildingNotFoundError."""
        logger.debug("delete building: building_id=%d", building_id)
        building = await self._session.get(Building, building_id)
        if not building:
            raise BuildingNotFoundError(building_id)
        await self._session.delete(building)
        await self._session.commit()
