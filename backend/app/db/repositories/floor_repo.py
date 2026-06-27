"""
Repository for Floor entities.

Pure data access — no business logic.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import FloorDuplicateNumberError, FloorNotFoundError
from app.db.models.building import Building, Floor
from app.db.models.reconstruction import Reconstruction
from app.db.models.section import Section
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class FloorRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(self, building_id: int, number: int) -> Floor:
        """INSERT a new floor. Raises FloorDuplicateNumberError on duplicate (building_id, number).

        Also raises FloorDuplicateNumberError wrapping IntegrityError when building code
        cannot be resolved (uses 'UNKNOWN' as building_code placeholder in that case).
        """
        logger.debug("create floor: building_id=%d, number=%d", building_id, number)
        floor = Floor(building_id=building_id, number=number)
        self._session.add(floor)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            # Fetch building code for the error message (best-effort)
            building = await self._session.get(Building, building_id)
            code = building.code if building else "UNKNOWN"
            raise FloorDuplicateNumberError(code, number)
        await self._session.refresh(floor)
        return floor

    async def get_by_id(self, floor_id: int) -> Optional[Floor]:
        """SELECT by PK with eager-loaded building + schema_image + mask_file.

        Returns None if not found.
        """
        logger.debug("get_by_id: floor_id=%d", floor_id)
        result = await self._session.execute(
            select(Floor)
            .options(selectinload(Floor.building))
            .options(selectinload(Floor.schema_image))
            .options(selectinload(Floor.mask_file))
            .where(Floor.id == floor_id)
        )
        return result.scalar_one_or_none()

    async def get_by_building_and_number(
        self, building_id: int, number: int
    ) -> Optional[Floor]:
        """SELECT by (building_id, number) composite key. Returns None if not found."""
        logger.debug(
            "get_by_building_and_number: building_id=%d, number=%d", building_id, number
        )
        result = await self._session.execute(
            select(Floor).where(
                Floor.building_id == building_id,
                Floor.number == number,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_building(self, building_id: int) -> list[Floor]:
        """SELECT floors for a building ordered by number ASC."""
        logger.debug("list_by_building: building_id=%d", building_id)
        result = await self._session.execute(
            select(Floor)
            .where(Floor.building_id == building_id)
            .order_by(Floor.number)
        )
        return list(result.scalars().all())

    async def delete(self, floor_id: int) -> None:
        """DELETE by PK. Cascade to sections via ORM. Raises FloorNotFoundError."""
        logger.debug("delete floor: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        await self._session.delete(floor)
        await self._session.commit()

    async def count_sections(self, floor_id: int) -> int:
        """COUNT(*) of sections belonging to this floor."""
        logger.debug("count_sections: floor_id=%d", floor_id)
        result = await self._session.execute(
            select(func.count()).select_from(Section).where(Section.floor_id == floor_id)
        )
        return result.scalar_one()

    async def count_unbound_reconstructions(self, floor_id: int) -> int:
        """COUNT reconstructions with floor_id=?, status=Done(3), not linked to any section.

        Uses LEFT OUTER JOIN on sections: only rows where sections.id IS NULL are counted.
        """
        logger.debug("count_unbound_reconstructions: floor_id=%d", floor_id)
        result = await self._session.execute(
            select(func.count())
            .select_from(Reconstruction)
            .outerjoin(Section, Section.reconstruction_id == Reconstruction.id)
            .where(
                Reconstruction.floor_id == floor_id,
                Reconstruction.status == 3,  # Done
                Section.id.is_(None),
            )
        )
        return result.scalar_one()

    async def update_schema(
        self,
        floor_id: int,
        schema_image_id: Optional[str],
        schema_crop_bbox: Optional[dict],
    ) -> Floor:
        """UPDATE schema_image_id + schema_crop_bbox. Raises FloorNotFoundError."""
        logger.debug("update_schema: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.schema_image_id = schema_image_id
        floor.schema_crop_bbox = schema_crop_bbox
        await self._session.commit()
        await self._session.refresh(floor)
        return floor

    async def update_wall_polygons(
        self,
        floor_id: int,
        wall_polygons: list,
    ) -> Floor:
        """UPDATE wall_polygons field. Raises FloorNotFoundError."""
        logger.debug("update_wall_polygons: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.wall_polygons = wall_polygons
        await self._session.commit()
        await self._session.refresh(floor)
        return floor

    async def update_nav_cutouts(
        self,
        floor_id: int,
        nav_cutouts: list,
    ) -> Floor:
        """UPDATE nav_cutouts field (wizard step 8). Raises FloorNotFoundError."""
        logger.debug("update_nav_cutouts: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.nav_cutouts = nav_cutouts
        await self._session.commit()
        await self._session.refresh(floor)
        return floor

    async def update_pixels_per_meter(
        self,
        floor_id: int,
        ppm: float,
    ) -> Floor:
        """UPDATE pixels_per_meter (floor metric scale). Raises FloorNotFoundError."""
        logger.debug("update_pixels_per_meter: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.pixels_per_meter = ppm
        await self._session.commit()
        await self._session.refresh(floor)
        return floor

    async def update_mesh_glb(
        self,
        floor_id: int,
        mesh_file_glb: str,
    ) -> Floor:
        """UPDATE mesh_file_glb (assembled floor GLB path). Raises FloorNotFoundError."""
        logger.debug("update_mesh_glb: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.mesh_file_glb = mesh_file_glb
        await self._session.commit()
        await self._session.refresh(floor)
        return floor

    async def update_mask(
        self,
        floor_id: int,
        mask_file_id: Optional[str],
    ) -> Floor:
        """UPDATE mask_file_id (persisted wall-mask file). Raises FloorNotFoundError."""
        logger.debug("update_mask: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.mask_file_id = mask_file_id
        await self._session.commit()
        await self._session.refresh(floor)
        return floor

    async def update_stitch_points(
        self,
        floor_id: int,
        points: list,
        ref_points: list,
    ) -> Floor:
        """UPDATE stitch_points + stitch_ref_points (vertical stitching, A).

        ``points`` are this floor's anchor points; ``ref_points`` are the matching
        points on the floor below (paired by id). Raises FloorNotFoundError.
        """
        logger.debug("update_stitch_points: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.stitch_points = points
        floor.stitch_ref_points = ref_points
        await self._session.commit()
        await self._session.refresh(floor)
        return floor

    async def update_building_transform(
        self,
        floor_id: int,
        building_transform: Optional[dict],
    ) -> Floor:
        """UPDATE building_transform (vertical stitching, A).

        Accepts ``None`` to reset an unlinked floor on re-solve. Raises
        FloorNotFoundError.
        """
        logger.debug("update_building_transform: floor_id=%d", floor_id)
        floor = await self._session.get(Floor, floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        floor.building_transform = building_transform
        await self._session.commit()
        await self._session.refresh(floor)
        return floor
