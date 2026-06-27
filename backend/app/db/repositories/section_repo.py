"""
Repository for Section entities.

Pure data access — no business logic.
"""

import logging
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.section import Section
from app.db.models.reconstruction import Reconstruction
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SectionRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_by_floor(self, floor_id: int) -> list[Section]:
        """SELECT sections for a floor, eager-loading reconstruction + its files.

        ``mask_file`` is eager-loaded (alongside ``plan_file``) so the assembly
        read can expose the section's cropped wall-mask URL without a lazy load in
        async context.
        """
        logger.debug("list_by_floor: floor_id=%d", floor_id)
        result = await self._session.execute(
            select(Section)
            .options(
                selectinload(Section.reconstruction).selectinload(
                    Reconstruction.plan_file
                ),
                selectinload(Section.reconstruction).selectinload(
                    Reconstruction.mask_file
                ),
            )
            .where(Section.floor_id == floor_id)
            .order_by(Section.number)
        )
        return list(result.scalars().all())

    async def delete_all_for_floor(self, floor_id: int) -> None:
        """DELETE FROM sections WHERE floor_id=?."""
        logger.debug("delete_all_for_floor: floor_id=%d", floor_id)
        await self._session.execute(
            delete(Section).where(Section.floor_id == floor_id)
        )
        await self._session.flush()

    async def bulk_create(self, items: list[dict]) -> list[Section]:
        """INSERT multiple sections in one batch.

        Each item dict must contain: floor_id, number, geometry, section_type.
        Optional: reconstruction_id.
        Returns created Section objects (refreshed from DB).
        """
        logger.debug("bulk_create: count=%d", len(items))
        sections = [
            Section(
                floor_id=item["floor_id"],
                number=item["number"],
                geometry=item.get("geometry"),
                section_type=item.get("section_type", 1),
                reconstruction_id=item.get("reconstruction_id"),
            )
            for item in items
        ]
        self._session.add_all(sections)
        await self._session.flush()
        # Refresh to populate IDs and timestamps
        for section in sections:
            await self._session.refresh(section)
        return sections

    async def get_by_id(self, section_id: int) -> Optional[Section]:
        """SELECT by PK with reconstruction + its files loaded. None if not found."""
        logger.debug("get_by_id: section_id=%d", section_id)
        result = await self._session.execute(
            select(Section)
            .options(
                selectinload(Section.reconstruction).selectinload(
                    Reconstruction.plan_file
                ),
                selectinload(Section.reconstruction).selectinload(
                    Reconstruction.mask_file
                ),
            )
            .where(Section.id == section_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, section_id: int) -> None:
        """DELETE by PK. No-op if not found (caller checks existence)."""
        logger.debug("delete section: section_id=%d", section_id)
        section = await self._session.get(Section, section_id)
        if section:
            await self._session.delete(section)
            await self._session.commit()

    async def update_master_control_points(
        self, section_id: int, points: list[dict]
    ) -> Optional[Section]:
        """UPDATE master-schema control_points field. Returns None if not found."""
        logger.debug("update_master_control_points: section_id=%d", section_id)
        section = await self._session.get(Section, section_id)
        if not section:
            return None
        section.control_points = points
        await self._session.commit()
        await self._session.refresh(section)
        return section

    async def update_transform(
        self, section_id: int, transform: Optional[dict]
    ) -> Optional[Section]:
        """UPDATE solved similarity transform. None clears a stale transform.

        Returns None if the section is not found.
        """
        logger.debug("update_transform: section_id=%d", section_id)
        section = await self._session.get(Section, section_id)
        if not section:
            return None
        section.transform = transform
        await self._session.commit()
        await self._session.refresh(section)
        return section
