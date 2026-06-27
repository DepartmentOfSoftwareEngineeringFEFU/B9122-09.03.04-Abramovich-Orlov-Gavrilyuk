"""
Repository for FloorConnector entities.

Pure data access — no business logic.
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.floor_connector import FloorConnector
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class FloorConnectorRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_floor(self, floor_id: int) -> list[FloorConnector]:
        """SELECT connectors for a floor ordered by id ASC."""
        logger.debug("list_by_floor: floor_id=%d", floor_id)
        result = await self._session.execute(
            select(FloorConnector)
            .where(FloorConnector.floor_id == floor_id)
            .order_by(FloorConnector.id)
        )
        return list(result.scalars().all())

    async def replace_all_for_floor(
        self, floor_id: int, items: list[dict]
    ) -> list[FloorConnector]:
        """Atomically replace all connectors for a floor.

        DELETE WHERE floor_id=? then INSERT the new items in a single
        transaction (one commit). On error nothing is committed, so no
        partial state remains. Empty ``items`` ⇒ clears the floor, returns [].

        Each item dict must contain: points (list).
        Optional: height_m, thickness_m, connects.
        Returns created FloorConnector objects (refreshed from DB).
        """
        logger.debug(
            "replace_all_for_floor: floor_id=%d, count=%d", floor_id, len(items)
        )
        await self._session.execute(
            delete(FloorConnector).where(FloorConnector.floor_id == floor_id)
        )
        connectors = [
            FloorConnector(
                floor_id=floor_id,
                points=item["points"],
                height_m=item.get("height_m"),
                thickness_m=item.get("thickness_m"),
                connects=item.get("connects"),
            )
            for item in items
        ]
        self._session.add_all(connectors)
        await self._session.flush()
        # Refresh to populate IDs and timestamps
        for connector in connectors:
            await self._session.refresh(connector)
        await self._session.commit()
        return connectors
