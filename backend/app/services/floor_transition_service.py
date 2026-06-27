"""
Business logic for floor transition CRUD.
"""

import logging
from typing import Optional

from app.db.models.floor_transition import FloorTransition
from app.db.repositories.floor_transition_repo import FloorTransitionRepository
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.models.floor_transition import FloorTransitionRequest
from app.core.exceptions import FloorTransitionNotFoundError, FloorTransitionError

logger = logging.getLogger(__name__)


class FloorTransitionService:
    def __init__(
        self,
        repo: FloorTransitionRepository,
        recon_repo: ReconstructionRepository,
    ) -> None:
        self._repo = repo
        self._recon_repo = recon_repo

    async def create(self, request: FloorTransitionRequest) -> FloorTransition:
        """Validate reconstructions exist, derive building_id, persist transition."""
        from_recon = await self._recon_repo.get_by_id(request.from_reconstruction_id)
        if not from_recon:
            raise FloorTransitionError(
                f"Reconstruction {request.from_reconstruction_id} not found"
            )
        to_recon = await self._recon_repo.get_by_id(request.to_reconstruction_id)
        if not to_recon:
            raise FloorTransitionError(
                f"Reconstruction {request.to_reconstruction_id} not found"
            )
        # Derive building_id (= Building.code) via floor relationship.
        # Reconstruction has no direct building_id since.
        building_id: Optional[str] = None
        floor = getattr(from_recon, "floor", None)
        if floor is not None:
            building = getattr(floor, "building", None)
            if building is not None:
                building_id = building.code
        logger.debug(
            "FloorTransitionService.create: from=%d to=%d building=%s",
            request.from_reconstruction_id,
            request.to_reconstruction_id,
            building_id,
        )
        return await self._repo.create(
            name=request.name,
            building_id=building_id,
            from_reconstruction_id=request.from_reconstruction_id,
            from_x=request.from_x,
            from_y=request.from_y,
            from_geometry=request.from_geometry,
            to_reconstruction_id=request.to_reconstruction_id,
            to_x=request.to_x,
            to_y=request.to_y,
            to_geometry=request.to_geometry,
        )

    async def get_by_building(self, building_id: str) -> list[FloorTransition]:
        return await self._repo.get_by_building(building_id)

    async def get_by_reconstruction(self, reconstruction_id: int) -> list[FloorTransition]:
        return await self._repo.get_by_reconstruction(reconstruction_id)

    async def delete(self, transition_id: int) -> None:
        deleted = await self._repo.delete(transition_id)
        if not deleted:
            raise FloorTransitionNotFoundError(transition_id)
