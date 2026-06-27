"""
FloorService — CRUD for Floor entities with number uniqueness validation.
"""

import logging

from app.core.exceptions import (
    BuildingNotFoundError,
    FloorDuplicateNumberError,
    FloorNotFoundError,
)
from app.db.repositories.building_repo import BuildingRepository
from app.db.repositories.floor_repo import FloorRepository
from app.models.floors import (
    FloorCreateRequest,
    FloorResponse,
    FloorWithBuildingResponse,
    BuildingBrief,
    CropBboxModel,
)

logger = logging.getLogger(__name__)


class FloorService:
    def __init__(
        self,
        building_repo: BuildingRepository,
        floor_repo: FloorRepository,
    ) -> None:
        self._building_repo = building_repo
        self._floor_repo = floor_repo

    async def create_floor(
        self, building_id: int, req: FloorCreateRequest
    ) -> FloorResponse:
        """Create a new floor for a building.

        Raises:
            BuildingNotFoundError: if building does not exist.
            FloorDuplicateNumberError: if floor number already taken.
        """
        logger.info("create_floor: building_id=%d, number=%d", building_id, req.number)
        building = await self._building_repo.get_by_id(building_id)
        if not building:
            raise BuildingNotFoundError(building_id)

        existing = await self._floor_repo.get_by_building_and_number(
            building_id, req.number
        )
        if existing:
            raise FloorDuplicateNumberError(building.code, req.number)

        floor = await self._floor_repo.create(building_id=building_id, number=req.number)
        sections_count = await self._floor_repo.count_sections(floor.id)
        unbound_count = await self._floor_repo.count_unbound_reconstructions(floor.id)
        return FloorResponse(
            id=floor.id,
            building_id=floor.building_id,
            number=floor.number,
            sections_count=sections_count,
            reconstructions_unbound_count=unbound_count,
            created_at=floor.created_at,
        )

    async def list_by_building(self, building_id: int) -> list[FloorResponse]:
        """List floors for a building ordered by number ASC.

        Raises BuildingNotFoundError if building does not exist.
        """
        logger.debug("list_by_building: building_id=%d", building_id)
        building = await self._building_repo.get_by_id(building_id)
        if not building:
            raise BuildingNotFoundError(building_id)

        floors = await self._floor_repo.list_by_building(building_id)
        result: list[FloorResponse] = []
        for floor in floors:
            sections_count = await self._floor_repo.count_sections(floor.id)
            unbound_count = await self._floor_repo.count_unbound_reconstructions(floor.id)
            result.append(
                FloorResponse(
                    id=floor.id,
                    building_id=floor.building_id,
                    number=floor.number,
                    sections_count=sections_count,
                    reconstructions_unbound_count=unbound_count,
                    created_at=floor.created_at,
                )
            )
        return result

    async def get_by_id(self, floor_id: int) -> FloorWithBuildingResponse:
        """Return floor detail with embedded building info + schema fields.

        Raises FloorNotFoundError if absent.
        """
        logger.debug("get_by_id: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        sections_count = await self._floor_repo.count_sections(floor.id)
        unbound_count = await self._floor_repo.count_unbound_reconstructions(floor.id)

        building = floor.building
        building_brief = BuildingBrief(
            id=building.id,
            code=building.code,
            name=building.name,
        )

        # Build schema_image_url from the UploadedFile.url (which includes extension)
        schema_image_url = None
        if floor.schema_image_id and floor.schema_image is not None:
            schema_image_url = floor.schema_image.url

        # Persisted wall-mask URL — mirrors schema_image_url.
        mask_file_url = None
        if floor.mask_file_id and floor.mask_file is not None:
            mask_file_url = floor.mask_file.url

        # Parse crop bbox from JSON dict
        schema_crop_bbox = None
        if floor.schema_crop_bbox:
            schema_crop_bbox = CropBboxModel(**floor.schema_crop_bbox)

        return FloorWithBuildingResponse(
            id=floor.id,
            building_id=floor.building_id,
            number=floor.number,
            sections_count=sections_count,
            reconstructions_unbound_count=unbound_count,
            created_at=floor.created_at,
            building=building_brief,
            schema_image_id=floor.schema_image_id,
            schema_image_url=schema_image_url,
            schema_crop_bbox=schema_crop_bbox,
            wall_polygons=floor.wall_polygons,
            mask_file_id=floor.mask_file_id,
            mask_file_url=mask_file_url,
        )

    async def delete(self, floor_id: int) -> None:
        """Delete floor. Raises FloorNotFoundError if absent."""
        logger.info("delete floor: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)
        await self._floor_repo.delete(floor_id)
