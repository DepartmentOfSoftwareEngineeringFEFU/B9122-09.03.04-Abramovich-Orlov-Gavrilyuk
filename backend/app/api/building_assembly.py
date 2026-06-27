"""API routes for Vertical Floor Stitching (subfeature A).

Thin router for the three building-assembly endpoints. Each route does only:
validate (Pydantic request models) → call ``BuildingAssemblyService`` → return the
response model. ALL business logic (pairing, solve, compose, persist) lives in the
service; the router's sole extra job is mapping the service's domain exceptions
onto HTTP status codes via the single canonical table in ``_STATUS_BY_EXC``.

Paths span both ``/floors/...`` and ``/buildings/...`` so the router uses
``prefix=""`` (the ``/api/v1`` prefix is applied where the router is included).
Per-pair solve statuses (``needs_points`` / ``degenerate`` / ``no_mask``) are 200
body fields, NOT HTTP errors (../02 error table).
"""
import logging
from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_building_assembly_service
from app.core.exceptions import (
    BuildingNotFoundError,
    FloorAssemblyConflictError,
    FloorNotFoundError,
    ImageProcessingError,
)
from app.models.building_assembly import (
    BuildingAssemblyResponse,
    SaveStitchPointsRequest,
    SaveStitchPointsResponse,
    SolveStitchResponse,
)
from app.services.building_assembly_service import BuildingAssemblyService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["building-assembly"])
security = HTTPBearer()


# Canonical domain-exception → HTTP-status table. Mirrors the actual ``raise``
# sites in BuildingAssemblyService. All entries are independent leaf types, so any
# matching ``isinstance`` is unambiguous.
_STATUS_BY_EXC: dict[type[Exception], int] = {
    FloorNotFoundError: status.HTTP_404_NOT_FOUND,
    BuildingNotFoundError: status.HTTP_404_NOT_FOUND,
    FloorAssemblyConflictError: status.HTTP_409_CONFLICT,
    ImageProcessingError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@contextmanager
def _map_domain_errors() -> Iterator[None]:
    """Translate known service exceptions into HTTPException.

    Any exception NOT in ``_STATUS_BY_EXC`` (an unexpected failure) is re-raised
    unchanged so FastAPI's default handler logs the traceback and returns 500.
    """
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — narrowed via the mapping below
        for exc_type, code in _STATUS_BY_EXC.items():
            if isinstance(exc, exc_type):
                raise HTTPException(status_code=code, detail=str(exc)) from exc
        raise


@router.put(
    "/floors/{floor_id}/stitch-points",
    response_model=SaveStitchPointsResponse,
)
async def put_stitch_points(
    floor_id: int,
    req: SaveStitchPointsRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: BuildingAssemblyService = Depends(get_building_assembly_service),
) -> SaveStitchPointsResponse:
    """Save the anchor points for the pair (this floor = upper, floor below = ref).

    The pair is keyed on the UPPER floor's row. 404 floor missing · 409 floor
    is the lowest in its building · 422 unpaired ids / bad id / coord out of range /
    over cap (enforced by the request model).
    """
    with _map_domain_errors():
        return await svc.save_stitch_points(floor_id, req.points, req.ref_points)


@router.post(
    "/buildings/{building_id}/solve-stitch",
    response_model=SolveStitchResponse,
)
async def post_solve_stitch(
    building_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: BuildingAssemblyService = Depends(get_building_assembly_service),
) -> SolveStitchResponse:
    """Solve every adjacent pair and compose per-floor building transforms.

    404 building missing · 409 fewer than two floors. Per-pair failures
    (``needs_points`` / ``degenerate`` / ``no_mask``) surface as statuses inside
    the 200 response, never as HTTP errors.
    """
    with _map_domain_errors():
        return await svc.solve_stitch(building_id)


@router.get(
    "/buildings/{building_id}/assembly",
    response_model=BuildingAssemblyResponse,
)
async def get_assembly(
    building_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: BuildingAssemblyService = Depends(get_building_assembly_service),
) -> BuildingAssemblyResponse:
    """Read the assembly state powering the building-assembly page.

    404 building missing. Exposes each floor's ``mask_width``/``mask_height`` (D's
    canvas-factor recovery) + the persisted ``building_transform``.
    """
    with _map_domain_errors():
        return await svc.get_assembly(building_id)
