"""
API routes for navigation and route building
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_nav_service, get_floor_transition_repo, get_reconstruction_repo, get_transition_repo
from app.core.exceptions import NavGraphNotFoundError
from app.models import FindRouteRequest, FindRouteResponse
from app.models.transition import MultiPlanRouteRequest, MultiPlanRouteResponse
from app.models.floor_transition import MultifloorRouteRequest, MultifloorRouteResponse
from app.services.nav_service import NavService

router = APIRouter(prefix="/navigation", tags=["Navigation"])
security = HTTPBearer()


@router.post("/multifloor-route", response_model=MultifloorRouteResponse)
async def find_multifloor_route(
    request: MultifloorRouteRequest,
    nav_service: NavService = Depends(get_nav_service),
    ft_repo=Depends(get_floor_transition_repo),
    recon_repo=Depends(get_reconstruction_repo),
) -> MultifloorRouteResponse:
    """
    Find a route between rooms, possibly spanning multiple floors.

    Returns path segments per floor with 3D coordinates.
    """
    try:
        result = await nav_service.find_multifloor_route(
            building_id=request.building_id,
            from_reconstruction_id=request.from_reconstruction_id,
            from_room_id=request.from_room_id,
            to_reconstruction_id=request.to_reconstruction_id,
            to_room_id=request.to_room_id,
            ft_repo=ft_repo,
            recon_repo=recon_repo,
        )
        return result
    except NavGraphNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/route", response_model=FindRouteResponse)
async def build_route(
    request: FindRouteRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: NavService = Depends(get_nav_service),
):
    result = await svc.find_route(
        graph_id=request.graph_id,
        from_room_id=request.from_room_id,
        to_room_id=request.to_room_id,
    )
    return FindRouteResponse(**result)


@router.post("/route/multi", response_model=MultiPlanRouteResponse)
async def build_multi_route(
    request: MultiPlanRouteRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: NavService = Depends(get_nav_service),
    transition_repo=Depends(get_transition_repo),
    recon_repo=Depends(get_reconstruction_repo),
):
    return await svc.find_multi_plan_route(request, transition_repo, recon_repo)


@router.get("/graphs/{graph_id}/rooms_3d")
async def get_rooms_3d(
    graph_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: NavService = Depends(get_nav_service),
):
    """Returns 3D positions for every room in the nav graph, using the same
    pixel→world formula as route markers. Frontend uses this for the
    «Кабинеты» overlay so positions match exactly."""
    try:
        return svc.get_rooms_3d(graph_id)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph not found")
