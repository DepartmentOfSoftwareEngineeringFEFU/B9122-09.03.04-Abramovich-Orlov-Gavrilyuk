"""
Repository for transition groups and points.
"""

import logging
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.reconstruction import Reconstruction
from app.db.models.transition import TransitionGroup, TransitionPoint
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class TransitionRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_group(
        self,
        building_id: str | None,
        group_type: str,
        label: str | None,
        target_hint_building_id: str | None,
        target_hint_floor_number: int | None,
        user_id: int | None,
    ) -> TransitionGroup:
        group = TransitionGroup(
            building_id=building_id,
            type=group_type,
            label=label,
            target_hint_building_id=target_hint_building_id,
            target_hint_floor_number=target_hint_floor_number,
            created_by=user_id,
        )
        self._session.add(group)
        await self._session.commit()
        await self._session.refresh(group)
        return group

    async def get_group(self, group_id: int) -> Optional[TransitionGroup]:
        result = await self._session.execute(
            select(TransitionGroup)
            .options(selectinload(TransitionGroup.points))
            .where(TransitionGroup.id == group_id)
        )
        return result.scalar_one_or_none()

    async def list_groups_by_building(self, building_id: str) -> list[TransitionGroup]:
        result = await self._session.execute(
            select(TransitionGroup)
            .options(selectinload(TransitionGroup.points))
            .where(TransitionGroup.building_id == building_id)
            .order_by(TransitionGroup.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all_groups(self) -> list[TransitionGroup]:
        result = await self._session.execute(
            select(TransitionGroup)
            .options(selectinload(TransitionGroup.points))
            .order_by(TransitionGroup.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_group(
        self,
        group_id: int,
        group_type: str | None,
        label: str | None,
        target_hint_building_id: str | None,
        target_hint_floor_number: int | None,
    ) -> Optional[TransitionGroup]:
        group = await self._session.get(TransitionGroup, group_id)
        if not group:
            return None
        if group_type is not None:
            group.type = group_type
        if label is not None:
            group.label = label
        if target_hint_building_id is not None:
            group.target_hint_building_id = target_hint_building_id
        if target_hint_floor_number is not None:
            group.target_hint_floor_number = target_hint_floor_number
        await self._session.commit()
        await self._session.refresh(group)
        return group

    async def delete_group(self, group_id: int) -> bool:
        group = await self._session.get(TransitionGroup, group_id)
        if not group:
            return False
        await self._session.delete(group)
        await self._session.commit()
        return True

    async def create_point(
        self,
        reconstruction_id: int,
        group_id: int,
        position_x: float,
        position_y: float,
        geometry: list[list[float]] | None,
        label: str | None,
        user_id: int | None,
    ) -> TransitionPoint:
        point = TransitionPoint(
            reconstruction_id=reconstruction_id,
            group_id=group_id,
            position_x=position_x,
            position_y=position_y,
            geometry=geometry,
            label=label,
            created_by=user_id,
        )
        self._session.add(point)
        await self._session.commit()
        await self._session.refresh(point)
        return point

    async def get_point(self, point_id: int) -> Optional[TransitionPoint]:
        return await self._session.get(TransitionPoint, point_id)

    async def list_points_by_reconstruction(self, reconstruction_id: int) -> list[TransitionPoint]:
        result = await self._session.execute(
            select(TransitionPoint)
            .options(selectinload(TransitionPoint.group))
            .where(TransitionPoint.reconstruction_id == reconstruction_id)
            .order_by(TransitionPoint.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_points_by_building(self, building_id: str) -> list[TransitionPoint]:
        result = await self._session.execute(
            select(TransitionPoint)
            .join(TransitionPoint.reconstruction)
            .options(selectinload(TransitionPoint.group))
            .where(Reconstruction.building_id == building_id)
            .order_by(TransitionPoint.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_point(
        self,
        point_id: int,
        position_x: float | None,
        position_y: float | None,
        geometry: list[list[float]] | None,
        label: str | None,
    ) -> Optional[TransitionPoint]:
        point = await self._session.get(TransitionPoint, point_id)
        if not point:
            return None
        if position_x is not None:
            point.position_x = position_x
        if position_y is not None:
            point.position_y = position_y
        if geometry is not None:
            point.geometry = geometry
        if label is not None:
            point.label = label
        await self._session.commit()
        await self._session.refresh(point)
        return point

    async def delete_point(self, point_id: int) -> bool:
        point = await self._session.get(TransitionPoint, point_id)
        if not point:
            return False
        await self._session.delete(point)
        await self._session.commit()
        return True
