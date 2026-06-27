"""
API routes for Floor hierarchy.
Thin router: validate → call service → return response.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.api.deps import get_floor_service
from app.core.exceptions import (
    BuildingNotFoundError,
    FloorDuplicateNumberError,
    FloorNotFoundError,
)
from app.models.floors import (
    FloorCreateRequest,
    FloorResponse,
    FloorWithBuildingResponse,
)
from app.services.floor_service import FloorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["floors"])
security = HTTPBearer()


@router.post(
    "/buildings/{building_id}/floors",
    response_model=FloorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_floor(
    building_id: int,
    req: FloorCreateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorService = Depends(get_floor_service),
) -> FloorResponse:
    """Create a new floor in a building (admin only)."""
    try:
        return await svc.create_floor(building_id, req)
    except BuildingNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building {e.building_id} not found",
        )
    except FloorDuplicateNumberError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Floor {e.number} already exists in building {e.building_code}",
        )


@router.get(
    "/buildings/{building_id}/floors",
    response_model=list[FloorResponse],
)
async def list_floors(
    building_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorService = Depends(get_floor_service),
) -> list[FloorResponse]:
    """List floors for a building ordered by number ASC (admin only)."""
    try:
        return await svc.list_by_building(building_id)
    except BuildingNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Building {e.building_id} not found",
        )


@router.get("/floors/{floor_id}", response_model=FloorWithBuildingResponse)
async def get_floor(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorService = Depends(get_floor_service),
) -> FloorWithBuildingResponse:
    """Get floor detail with embedded building info and schema fields (admin only)."""
    try:
        return await svc.get_by_id(floor_id)
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )


@router.delete("/floors/{floor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_floor(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorService = Depends(get_floor_service),
) -> None:
    """Delete floor and cascade to sections (admin only).

    Reconstructions with this floor_id become unbound (floor_id=NULL).
    schema_image_id is NOT deleted automatically.
    """
    try:
        await svc.delete(floor_id)
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )
