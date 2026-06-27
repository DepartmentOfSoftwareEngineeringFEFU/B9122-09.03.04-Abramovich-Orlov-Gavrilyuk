"""
API routes for the Floor Stitching feature.

Thin router for the assembly read. Each route does only:
validate (Pydantic request models) → call ``FloorAssemblyService`` → return the
response model. ALL business logic lives in the service; the router's sole extra
job is mapping the service's domain exceptions onto HTTP status codes via the
single canonical table in ``_STATUS_BY_EXC``.

Paths already carry ``/floors/...`` so the router uses ``prefix=""``.
"""
import logging
from contextlib import contextmanager
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_floor_assembly_service
from app.core.exceptions import (
    FloorAssemblyConflictError,
    FloorNotFoundError,
    FloorSchemaError,
    ImageProcessingError,
    PreviewNotFoundError,
    SectionNotBoundError,
    SectionNotFoundError,
    SectionValidationError,
)
from app.models.floor_assembly import (
    BuildFloorPreviewResponse,
    ConfirmMeshRequest,
    ConfirmMeshResponse,
    ConnectorsResponse,
    CutoutsResponse,
    FloorAssemblyResponse,
    ReplaceConnectorsRequest,
    ReplaceCutoutsRequest,
    SaveMasterControlPointsRequest,
    SectionControlPointsResponse,
    SolveTransformsResponse,
)
from app.services.floor_assembly_service import FloorAssemblyService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["floor-assembly"])
security = HTTPBearer()


# Canonical domain-exception → HTTP-status table. Mirrors the actual ``raise``
# sites in FloorAssemblyService (verified). Order matters only if two
# entries are in a subclass relationship — here they are all independent leaf
# types, so any matching ``isinstance`` is unambiguous.
_STATUS_BY_EXC: dict[type[Exception], int] = {
    FloorNotFoundError: status.HTTP_404_NOT_FOUND,
    SectionNotFoundError: status.HTTP_404_NOT_FOUND,
    SectionNotBoundError: status.HTTP_409_CONFLICT,
    FloorAssemblyConflictError: status.HTTP_409_CONFLICT,
    SectionValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    FloorSchemaError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    PreviewNotFoundError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ImageProcessingError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@contextmanager
def _map_domain_errors() -> Iterator[None]:
    """Translate known service exceptions into HTTPException.

    Any exception NOT in ``_STATUS_BY_EXC`` (e.g. an unexpected trimesh/export
    failure during build) is re-raised unchanged so FastAPI's default handler
    logs the traceback and returns 500.
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
    "/floors/{floor_id}/sections/{section_id}/control-points",
    response_model=SectionControlPointsResponse,
)
async def put_section_control_points(
    floor_id: int,
    section_id: int,
    req: SaveMasterControlPointsRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> SectionControlPointsResponse:
    """Replace a section's master-schema control points.

    404 section missing · 409 section not bound to a plan · 422 unknown point_id.
    """
    with _map_domain_errors():
        return await svc.save_section_control_points(
            floor_id, section_id, req.points
        )


@router.post(
    "/floors/{floor_id}/solve-transforms",
    response_model=SolveTransformsResponse,
)
async def post_solve_transforms(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> SolveTransformsResponse:
    """Solve every bound section's uniform similarity + derive ppm_floor.

    404 floor missing · 409 no sections bound. Per-section failures surface as
    statuses inside the 200 response, never as errors.
    """
    with _map_domain_errors():
        return await svc.solve_transforms(floor_id)


@router.get(
    "/floors/{floor_id}/connectors",
    response_model=ConnectorsResponse,
)
async def get_connectors(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> ConnectorsResponse:
    """List a floor's connector polylines. 404 floor missing."""
    with _map_domain_errors():
        return await svc.get_connectors(floor_id)


@router.put(
    "/floors/{floor_id}/connectors",
    response_model=ConnectorsResponse,
)
async def put_connectors(
    floor_id: int,
    req: ReplaceConnectorsRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> ConnectorsResponse:
    """Atomically replace ALL connector polylines for a floor.

    404 floor missing · 422 invalid payload (caps/coords enforced by the request
    model). An empty list clears the floor.
    """
    with _map_domain_errors():
        return await svc.replace_connectors(floor_id, req.connectors)


@router.get(
    "/floors/{floor_id}/cutouts",
    response_model=CutoutsResponse,
)
async def get_cutouts(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> CutoutsResponse:
    """List a floor's cutout zones. 404 floor missing."""
    with _map_domain_errors():
        return await svc.get_cutouts(floor_id)


@router.put(
    "/floors/{floor_id}/cutouts",
    response_model=CutoutsResponse,
)
async def put_cutouts(
    floor_id: int,
    req: ReplaceCutoutsRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> CutoutsResponse:
    """Atomically replace ALL cutout zones for a floor.

    404 floor missing · 422 invalid payload (caps/coords enforced by the request
    model; each zone needs >= 3 points). An empty list clears the floor.
    """
    with _map_domain_errors():
        return await svc.replace_cutouts(floor_id, req.cutouts)


@router.post(
    "/floors/{floor_id}/build-mesh",
    response_model=BuildFloorPreviewResponse,
)
async def post_build_mesh(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> BuildFloorPreviewResponse:
    """Assemble the stitched floor mask → preview GLB (build).

    404 floor missing · 409 not solved yet · 422 schema/mask problem · 500 on an
    unexpected export failure. ``floors.mesh_file_glb`` is NOT touched here.
    """
    with _map_domain_errors():
        return await svc.build_floor_mesh(floor_id)


@router.post(
    "/floors/{floor_id}/confirm-mesh",
    response_model=ConfirmMeshResponse,
)
async def post_confirm_mesh(
    floor_id: int,
    req: ConfirmMeshRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> ConfirmMeshResponse:
    """Promote a built preview GLB to the persisted floor model (confirm).

    404 floor missing · 422 unknown/expired preview handle. The ONLY endpoint
    that writes ``floors.mesh_file_glb``.
    """
    with _map_domain_errors():
        return await svc.confirm_floor_mesh(floor_id, req.glb_file_id)


@router.get(
    "/floors/{floor_id}/assembly",
    response_model=FloorAssemblyResponse,
)
async def get_assembly(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorAssemblyService = Depends(get_floor_assembly_service),
) -> FloorAssemblyResponse:
    """Single read powering the whole Floor Editor (assembly read). 404 floor missing."""
    with _map_domain_errors():
        return await svc.get_assembly(floor_id)
