"""
Repository for floor_transitions table — data access layer.
"""

import logging
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.floor_transition import FloorTransition
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class FloorTransitionRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        name: str,
        building_id: Optional[str],
        from_reconstruction_id: int,
        from_x: float,
        from_y: float,
        from_geometry: list[list[float]] | None,
        to_reconstruction_id: int,
        to_x: float,
        to_y: float,
        to_geometry: list[list[float]] | None,
        created_by: Optional[int] = None,
    ) -> FloorTransition:
        """INSERT a new floor transition."""
        logger.debug(
            "create: name=%s, from_recon=%d, to_recon=%d",
            name, from_reconstruction_id, to_reconstruction_id,
        )
        obj = FloorTransition(
            name=name,
            building_id=building_id,
            from_reconstruction_id=from_reconstruction_id,
            from_x=from_x,
            from_y=from_y,
            from_geometry=from_geometry,
            to_reconstruction_id=to_reconstruction_id,
            to_x=to_x,
            to_y=to_y,
            to_geometry=to_geometry,
            created_by=created_by,
        )
        self._session.add(obj)
        await self._session.commit()
        await self._session.refresh(obj)
        return obj

    async def get_by_id(self, transition_id: int) -> Optional[FloorTransition]:
        """SELECT by PK. Returns None if not found."""
        logger.debug("get_by_id: transition_id=%d", transition_id)
        result = await self._session.execute(
            select(FloorTransition).where(FloorTransition.id == transition_id)
        )
        return result.scalar_one_or_none()

    async def get_by_building(self, building_id: str) -> list[FloorTransition]:
        """SELECT WHERE building_id = ?"""
        logger.debug("get_by_building: building_id=%s", building_id)
        result = await self._session.execute(
            select(FloorTransition).where(FloorTransition.building_id == building_id)
        )
        return list(result.scalars().all())

    async def get_by_reconstruction(self, reconstruction_id: int) -> list[FloorTransition]:
        """SELECT WHERE from_reconstruction_id=? OR to_reconstruction_id=?"""
        logger.debug("get_by_reconstruction: reconstruction_id=%d", reconstruction_id)
        result = await self._session.execute(
            select(FloorTransition).where(
                or_(
                    FloorTransition.from_reconstruction_id == reconstruction_id,
                    FloorTransition.to_reconstruction_id == reconstruction_id,
                )
            )
        )
        return list(result.scalars().all())

    async def delete(self, transition_id: int) -> bool:
        """DELETE WHERE id=?. Returns True if deleted, False if not found."""
        logger.debug("delete: transition_id=%d", transition_id)
        obj = await self._session.get(FloorTransition, transition_id)
        if not obj:
            return False
        await self._session.delete(obj)
        await self._session.commit()
        return True
