"""
BuildingService — CRUD + hierarchical published filtering.
"""

import logging
from typing import Optional

from app.core.exceptions import (
    BuildingDuplicateCodeError,
    BuildingNotFoundError,
)
from app.db.models.building import Building
from app.db.repositories.building_repo import BuildingRepository
from app.db.repositories.floor_repo import FloorRepository
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.db.repositories.section_repo import SectionRepository
from app.models.buildings import (
    BuildingCreateRequest,
    BuildingDetailResponse,
    BuildingPublicResponse,
    BuildingResponse,
    BuildingUpdateRequest,
    FloorPublic,
    SectionPublic,
)
from app.models.floors import FloorBriefFromFloors

logger = logging.getLogger(__name__)

# Reconstruction status = Done
_STATUS_DONE = 3


class BuildingService:
    def __init__(
        self,
        building_repo: BuildingRepository,
        floor_repo: FloorRepository,
        section_repo: SectionRepository,
        reconstruction_repo: ReconstructionRepository,
    ) -> None:
        self._building_repo = building_repo
        self._floor_repo = floor_repo
        self._section_repo = section_repo
        self._reconstruction_repo = reconstruction_repo

    # Create

    async def create_building(self, req: BuildingCreateRequest) -> BuildingResponse:
        """Create a new building, normalising code to uppercase.

        Raises BuildingDuplicateCodeError if code is already taken.
        """
        logger.info("create_building: code=%s, name=%s", req.code, req.name)
        # Check duplicate code (repo also raises, but we do it explicitly for clarity)
        existing = await self._building_repo.get_by_code(req.code)
        if existing:
            raise BuildingDuplicateCodeError(req.code)

        building = await self._building_repo.create(
            code=req.code.upper(),
            name=req.name,
            address=req.address,
        )
        floors = await self._floor_repo.list_by_building(building.id)
        return self._to_response(building, len(floors))

    # List / Detail

    async def list_admin(self) -> list[BuildingResponse]:
        """Return all buildings with floors_count and computed published flag."""
        logger.debug("list_admin buildings")
        buildings = await self._building_repo.list_all()
        result: list[BuildingResponse] = []
        for b in buildings:
            floors = await self._floor_repo.list_by_building(b.id)
            published = await self._is_published(b.id)
            resp = BuildingResponse(
                id=b.id,
                code=b.code,
                name=b.name,
                address=b.address,
                created_at=b.created_at,
                floors_count=len(floors),
                published=published,
            )
            result.append(resp)
        return result

    async def list_published(self) -> list[BuildingPublicResponse]:
        """Return only published buildings with hierarchical filtering.

        Published: building has ≥1 floor with ≥1 section whose
        reconstruction.status == Done.
        """
        logger.debug("list_published buildings")
        buildings = await self._building_repo.list_all()
        result: list[BuildingPublicResponse] = []

        for building in buildings:
            floors = await self._floor_repo.list_by_building(building.id)
            published_floors: list[FloorPublic] = []

            for floor in floors:
                sections = await self._section_repo.list_by_floor(floor.id)
                published_sections: list[SectionPublic] = []

                for section in sections:
                    if section.reconstruction and section.reconstruction.status == _STATUS_DONE:
                        mesh_url_glb: Optional[str] = None
                        if section.reconstruction.mesh_file_id_glb:
                            mesh_url_glb = (
                                f"/api/v1/uploads/models/"
                                f"reconstruction_{section.reconstruction.id}.glb"
                            )
                        published_sections.append(
                            SectionPublic(
                                id=section.id,
                                number=section.number,
                                geometry=section.geometry,
                                reconstruction_id=section.reconstruction_id,
                                mesh_url_glb=mesh_url_glb,
                                section_type=section.section_type,
                            )
                        )

                if published_sections:
                    published_floors.append(
                        FloorPublic(
                            id=floor.id,
                            number=floor.number,
                            wall_polygons=floor.wall_polygons,
                            sections=published_sections,
                        )
                    )

            if published_floors:
                result.append(
                    BuildingPublicResponse(
                        id=building.id,
                        code=building.code,
                        name=building.name,
                        floors=published_floors,
                    )
                )

        return result

    async def get_by_id(self, building_id: int) -> BuildingDetailResponse:
        """Return building detail. Raises BuildingNotFoundError if absent."""
        logger.debug("get_by_id: building_id=%d", building_id)
        building = await self._building_repo.get_by_id(building_id)
        if not building:
            raise BuildingNotFoundError(building_id)
        floors = await self._floor_repo.list_by_building(building.id)
        published = await self._is_published(building.id)
        floor_briefs = [FloorBriefFromFloors(id=f.id, number=f.number) for f in floors]
        return BuildingDetailResponse(
            id=building.id,
            code=building.code,
            name=building.name,
            address=building.address,
            created_at=building.created_at,
            floors_count=len(floors),
            published=published,
            floors=floor_briefs,
        )

    # Update / Delete

    async def update(self, building_id: int, req: BuildingUpdateRequest) -> BuildingResponse:
        """Partial update of mutable fields. Raises BuildingNotFoundError if absent."""
        logger.info("update building: building_id=%d", building_id)
        update_fields = {k: v for k, v in req.model_dump().items() if v is not None}
        building = await self._building_repo.update(building_id, **update_fields)
        floors = await self._floor_repo.list_by_building(building.id)
        published = await self._is_published(building.id)
        return self._to_response(building, len(floors), published)

    async def delete(self, building_id: int) -> None:
        """Cascade-delete building. Raises BuildingNotFoundError if absent."""
        logger.info("delete building: building_id=%d", building_id)
        building = await self._building_repo.get_by_id(building_id)
        if not building:
            raise BuildingNotFoundError(building_id)
        await self._building_repo.delete(building_id)

    # Private helpers

    async def _is_published(self, building_id: int) -> bool:
        """Return True if the building has ≥1 section with reconstruction.status=Done."""
        floors = await self._floor_repo.list_by_building(building_id)
        for floor in floors:
            sections = await self._section_repo.list_by_floor(floor.id)
            for section in sections:
                if section.reconstruction and section.reconstruction.status == _STATUS_DONE:
                    return True
        return False

    @staticmethod
    def _to_response(
        building: Building,
        floors_count: int,
        published: bool = False,
    ) -> BuildingResponse:
        return BuildingResponse(
            id=building.id,
            code=building.code,
            name=building.name,
            address=building.address,
            created_at=building.created_at,
            floors_count=floors_count,
            published=published,
        )
