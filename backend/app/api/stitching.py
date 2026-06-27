"""
API routes for stitching operations.
Thin router layer: validate → call service → return response.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models.stitching import StitchingRequest, StitchingResponse
from app.services.stitching_service import StitchingService
from app.api.deps import get_stitching_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stitching", tags=["stitching"])
security = HTTPBearer()


@router.post("/", response_model=StitchingResponse, status_code=status.HTTP_201_CREATED)
async def stitch_plans(
    request: StitchingRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    service: StitchingService = Depends(get_stitching_service),
) -> StitchingResponse:
    """
    Stitch multiple floor plans into one.

    Args:
        request: StitchingRequest with source plans and transforms
        service: StitchingService (injected)
        credentials: Authentication credentials (injected)

    Returns:
        StitchingResponse with new reconstruction details

    Raises:
        400: Invalid request (validation error, no walls after merge)
        404: Source reconstruction or building not found
        500: Processing error
    """
    try:
        # Extract user_id from token (placeholder - use 1 for now)
        user_id = 1
        response = await service.stitch_plans(request, user_id)
        return response
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Stitching failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Stitching failed: {str(e)}")
