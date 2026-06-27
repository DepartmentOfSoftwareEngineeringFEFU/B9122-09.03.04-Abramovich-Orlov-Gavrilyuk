"""
API routes for Section hierarchy.
Thin router: validate → call service → return response.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.api.deps import get_section_service
from app.core.exceptions import FloorNotFoundError, SectionValidationError
from app.models.sections import ReplaceSectionsRequest, SectionResponse
from app.services.section_service import SectionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["sections"])
security = HTTPBearer()


@router.get("/floors/{floor_id}/sections", response_model=list[SectionResponse])
async def list_sections(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: SectionService = Depends(get_section_service),
) -> list[SectionResponse]:
    """List sections for a floor (admin only)."""
    try:
        return await svc.list_by_floor(floor_id)
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )


@router.put("/floors/{floor_id}/sections", response_model=list[SectionResponse])
async def replace_sections(
    floor_id: int,
    req: ReplaceSectionsRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: SectionService = Depends(get_section_service),
) -> list[SectionResponse]:
    """Atomically replace all sections for a floor (admin only).

    DELETE all existing sections for the floor, then INSERT the new set.
    Validates uniqueness of number and reconstruction_id within payload.
    reconstruction_id may belong to any floor.
    """
    try:
        return await svc.replace_sections(floor_id, req)
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )
    except SectionValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.detail,
        )


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(
    section_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: SectionService = Depends(get_section_service),
) -> None:
    """Delete a single section (admin only).

    The linked reconstruction remains in DB but becomes unbound.
    """
    await svc.delete_section(section_id)
