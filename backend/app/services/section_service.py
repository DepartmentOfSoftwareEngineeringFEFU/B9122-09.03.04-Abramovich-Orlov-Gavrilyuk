"""
SectionService — atomic replace strategy + validation.
"""

import logging

from app.core.exceptions import FloorNotFoundError, SectionValidationError
from app.db.repositories.floor_repo import FloorRepository
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.db.repositories.section_repo import SectionRepository
from app.models.sections import (
    ReplaceSectionsRequest,
    SectionPayloadItem,
    SectionResponse,
    ReconstructionBrief,
    SectionGeometry,
)

logger = logging.getLogger(__name__)


class SectionService:
    def __init__(
        self,
        floor_repo: FloorRepository,
        section_repo: SectionRepository,
        reconstruction_repo: ReconstructionRepository,
    ) -> None:
        self._floor_repo = floor_repo
        self._section_repo = section_repo
        self._reconstruction_repo = reconstruction_repo

    async def list_by_floor(self, floor_id: int) -> list[SectionResponse]:
        """List sections for a floor ordered by number ASC.

        Raises FloorNotFoundError if floor does not exist.
        """
        logger.debug("list_by_floor: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        sections = await self._section_repo.list_by_floor(floor_id)
        return [self._to_response(s) for s in sections]

    async def replace_sections(
        self, floor_id: int, req: ReplaceSectionsRequest
    ) -> list[SectionResponse]:
        """Atomically replace all sections for a floor.

        Steps:
        1. Validate floor exists.
        2. Validate payload (duplicates, reconstruction existence —).
        3. Within implicit transaction: delete all + bulk insert.
        4. Return refreshed list.

        Raises:
            FloorNotFoundError: if floor absent.
            SectionValidationError: on duplicate numbers, duplicate reconstruction_ids,
                or missing reconstructions.
        """
        logger.info("replace_sections: floor_id=%d, count=%d", floor_id, len(req.sections))
        floor = await self._floor_repo.get_by_id(floor_id)
        if not floor:
            raise FloorNotFoundError(floor_id)

        # Validate payload before touching DB
        await self._validate_payload(req.sections)

        # Atomic replace: delete all + insert new (uses flush, session commit happens after)
        await self._section_repo.delete_all_for_floor(floor_id)

        if req.sections:
            items = [
                {
                    "floor_id": floor_id,
                    "number": item.number,
                    "geometry": item.geometry.model_dump() if item.geometry else None,
                    "section_type": item.section_type,
                    "reconstruction_id": item.reconstruction_id,
                }
                for item in req.sections
            ]
            await self._section_repo.bulk_create(items)
            # Commit happens here via session; re-fetch to get reconstruction loaded
            await self._section_repo._session.commit()
        else:
            await self._section_repo._session.commit()

        # Re-fetch with reconstruction loaded for response
        sections = await self._section_repo.list_by_floor(floor_id)
        return [self._to_response(s) for s in sections]

    async def delete_section(self, section_id: int) -> None:
        """Delete a single section. No-op if already absent."""
        logger.info("delete_section: section_id=%d", section_id)
        await self._section_repo.delete(section_id)

    # Private helpers

    async def _validate_payload(self, sections: list[SectionPayloadItem]) -> None:
        """Validate section payload items.

        Checks:
        - No duplicate `number` values.
        - No duplicate `reconstruction_id` values (where not null).
        - Each `reconstruction_id` must reference an existing Reconstruction
          (cross-floor is allowed — no floor_id check).

        Raises SectionValidationError on first violation found.
        """
        seen_numbers: set[int] = set()
        seen_recon_ids: set[int] = set()

        for item in sections:
            # Duplicate number check
            if item.number in seen_numbers:
                raise SectionValidationError(f"Duplicate section number: {item.number}")
            seen_numbers.add(item.number)

            # Duplicate reconstruction_id check
            if item.reconstruction_id is not None:
                if item.reconstruction_id in seen_recon_ids:
                    raise SectionValidationError(
                        f"Reconstruction {item.reconstruction_id} already used"
                        " by another section in payload"
                    )
                seen_recon_ids.add(item.reconstruction_id)

                # Existence check (any floor allowed)
                recon = await self._reconstruction_repo.get_by_id(item.reconstruction_id)
                if not recon:
                    raise SectionValidationError(
                        f"Reconstruction {item.reconstruction_id} does not exist"
                    )

    @staticmethod
    def _to_response(section) -> SectionResponse:  # type: ignore[no-untyped-def]
        recon_brief = None
        if section.reconstruction:
            r = section.reconstruction
            preview_url = None
            if r.plan_file:
                preview_url = r.plan_file.url
            recon_brief = ReconstructionBrief(
                id=r.id,
                name=r.name,
                status=r.status,
                preview_url=preview_url,
            )

        geometry = None
        if section.geometry:
            geometry = SectionGeometry(**section.geometry)

        return SectionResponse(
            id=section.id,
            floor_id=section.floor_id,
            number=section.number,
            geometry=geometry,
            section_type=section.section_type,
            reconstruction=recon_brief,
            created_at=section.created_at,
            updated_at=section.updated_at,
        )
