"""
FastAPI router for floor transitions CRUD.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_floor_transition_service
from app.core.exceptions import FloorTransitionNotFoundError, FloorTransitionError
from app.models.floor_transition import FloorTransitionRequest, FloorTransitionResponse
from app.services.floor_transition_service import FloorTransitionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/floor-transitions", tags=["floor-transitions"])


@router.post("/", response_model=FloorTransitionResponse, status_code=status.HTTP_201_CREATED)
async def create_transition(
    request: FloorTransitionRequest,
    service: FloorTransitionService = Depends(get_floor_transition_service),
) -> FloorTransitionResponse:
    """Create a transition (teleport) between two floor plans."""
    try:
        result = await service.create(request)
        return FloorTransitionResponse.model_validate(result)
    except FloorTransitionError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=list[FloorTransitionResponse])
async def list_transitions(
    building_id: str | None = None,
    reconstruction_id: int | None = None,
    service: FloorTransitionService = Depends(get_floor_transition_service),
) -> list[FloorTransitionResponse]:
    """List transitions filtered by building_id or reconstruction_id."""
    if building_id:
        items = await service.get_by_building(building_id)
    elif reconstruction_id:
        items = await service.get_by_reconstruction(reconstruction_id)
    else:
        items = []
    return [FloorTransitionResponse.model_validate(i) for i in items]


@router.delete("/{transition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transition(
    transition_id: int,
    service: FloorTransitionService = Depends(get_floor_transition_service),
) -> None:
    """Delete a transition by id."""
    try:
        await service.delete(transition_id)
    except FloorTransitionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
