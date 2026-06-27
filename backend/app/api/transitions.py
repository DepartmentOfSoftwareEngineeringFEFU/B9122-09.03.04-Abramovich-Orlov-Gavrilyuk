"""
API routes for transition groups and transition points.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_current_user, get_transition_service
from app.models.transition import (
    MultiPlanRouteRequest,
    MultiPlanRouteResponse,
    TransitionGroupCreate,
    TransitionGroupResponse,
    TransitionGroupUpdate,
    TransitionPointCreate,
    TransitionPointResponse,
    TransitionPointUpdate,
)
from app.services.transition_service import TransitionService

router = APIRouter(prefix="/transitions", tags=["Transitions"])
security = HTTPBearer()


@router.post("/groups", response_model=TransitionGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    request: TransitionGroupCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    user = await get_current_user()
    return await service.create_group(request, getattr(user, "id", None))


@router.get("/groups", response_model=list[TransitionGroupResponse])
async def list_groups_by_building(
    building_id: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    if building_id:
        return await service.list_groups_for_building(building_id)
    return await service.list_all_groups()


@router.patch("/groups/{group_id}", response_model=TransitionGroupResponse)
async def update_group(
    group_id: int = Path(...),
    request: TransitionGroupUpdate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    group = await service.update_group(group_id, request)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition group not found")
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int = Path(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    deleted = await service.delete_group(group_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition group not found")


@router.post("/points", response_model=TransitionPointResponse, status_code=status.HTTP_201_CREATED)
async def create_point(
    request: TransitionPointCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    user = await get_current_user()
    try:
        return await service.create_point(request, getattr(user, "id", None))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/points/{point_id}", response_model=TransitionPointResponse)
async def update_point(
    point_id: int = Path(...),
    request: TransitionPointUpdate = ...,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    point = await service.update_point(point_id, request)
    if point is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition point not found")
    return point


@router.delete("/points/{point_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_point(
    point_id: int = Path(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    deleted = await service.delete_point(point_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition point not found")


@router.get("/reconstructions/{reconstruction_id}/points", response_model=list[TransitionPointResponse])
async def list_points_by_reconstruction(
    reconstruction_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    return await service.list_points_for_reconstruction(reconstruction_id)


@router.get("/buildings/{building_id}/points", response_model=list[TransitionPointResponse])
async def list_points_by_building(
    building_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: TransitionService = Depends(get_transition_service),
):
    return await service.list_points_for_building(building_id)


