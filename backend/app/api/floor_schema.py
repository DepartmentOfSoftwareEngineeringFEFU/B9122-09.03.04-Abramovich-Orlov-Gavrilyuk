"""
API routes for Floor schema editor pipeline.
Endpoints: PUT /floors/{id}/schema, POST /floors/{id}/extract-walls,
           PUT /floors/{id}/walls.
Thin router: validate → call service → return response.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.api.deps import get_floor_schema_service, get_floor_service
from app.core.exceptions import FloorNotFoundError, FloorSchemaError, ImageProcessingError
from app.models.floors import (
    FloorMaskUpdateRequest,
    FloorSchemaUpdateRequest,
    FloorWallsUpdateRequest,
    FloorWithBuildingResponse,
)
from app.services.floor_schema_service import FloorSchemaService
from app.services.floor_service import FloorService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["floor-schema"])
security = HTTPBearer()


@router.put("/floors/{floor_id}/schema", response_model=FloorWithBuildingResponse)
async def update_floor_schema(
    floor_id: int,
    req: FloorSchemaUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    schema_svc: FloorSchemaService = Depends(get_floor_schema_service),
    floor_svc: FloorService = Depends(get_floor_service),
) -> FloorWithBuildingResponse:
    """Set or update the schema image and optional crop bbox for a floor (admin only).

    - Assigns schema_image_id to the floor.
    - Optionally persists schema_crop_bbox if provided.
    - Returns full FloorWithBuildingResponse including schema fields.
    """
    try:
        await schema_svc.upload_schema(floor_id, req.schema_image_id)
        if req.schema_crop_bbox is not None:
            await schema_svc.update_crop(floor_id, req.schema_crop_bbox)
        return await floor_svc.get_by_id(floor_id)
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )
    except FloorSchemaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.detail,
        )


@router.delete("/floors/{floor_id}/schema", status_code=status.HTTP_204_NO_CONTENT)
async def reset_floor_schema(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    schema_svc: FloorSchemaService = Depends(get_floor_schema_service),
) -> None:
    """Fully clear a floor's schema image, crop, walls and mask (admin only).

    Used by the editor's "delete карта отсеков" action so the operator can load a
    brand-new floor map from scratch. Sections are removed separately by the
    client (sections replace-all).
    """
    try:
        await schema_svc.reset_schema(floor_id)
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )


@router.post("/floors/{floor_id}/extract-walls")
async def extract_walls(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    schema_svc: FloorSchemaService = Depends(get_floor_schema_service),
) -> dict:
    """Run CV pipeline to extract wall polygons from the floor schema image (admin only).

    Requires schema_image_id to be set on the floor.
    May take up to ~30 seconds for large images.
    Side effect: Floor.wall_polygons is updated in DB.
    """
    try:
        polygons = await schema_svc.extract_walls(floor_id)
        return {"wall_polygons": polygons}
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )
    except FloorSchemaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.detail,
        )
    except ImageProcessingError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wall extraction failed: {e}",
        )
    except Exception as e:
        logger.error("extract_walls unexpected error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Wall extraction failed: {e}",
        )


@router.put("/floors/{floor_id}/walls")
async def update_walls(
    floor_id: int,
    req: FloorWallsUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    schema_svc: FloorSchemaService = Depends(get_floor_schema_service),
) -> dict:
    """Manually save corrected wall polygons for a floor (admin only).

    Replaces the stored wall_polygons with the provided payload.
    All coordinates must be in [0, 1].
    """
    try:
        await schema_svc.update_walls(floor_id, req.wall_polygons)
        return {"wall_polygons": req.wall_polygons}
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )


@router.put("/floors/{floor_id}/mask", response_model=FloorWithBuildingResponse)
async def update_floor_mask(
    floor_id: int,
    req: FloorMaskUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    schema_svc: FloorSchemaService = Depends(get_floor_schema_service),
    floor_svc: FloorService = Depends(get_floor_service),
) -> FloorWithBuildingResponse:
    """Persist the user-edited wall mask for a floor (admin only).

    Links an already-uploaded mask file (POST /upload/user-mask/) so the Step-3
    wall edit survives reload. Returns the full FloorWithBuildingResponse.
    """
    try:
        await schema_svc.update_mask(floor_id, req.mask_file_id)
        return await floor_svc.get_by_id(floor_id)
    except FloorNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Floor {e.floor_id} not found",
        )
