"""API routes for cross-floor routing + link review (subfeature D).

Three thin, auth-protected endpoints over ``BuildingNavService``: find a
multifloor route, list the auto-matched transition links, and persist operator
overrides. Each route does only validate → call the service → return; ALL
business logic lives in the service. Domain exceptions map to HTTP codes via the
single ``_STATUS_BY_EXC`` table (mirrors ``floor_nav.py`` / ``building_assembly.py``).

Paths carry ``/buildings/...`` so the router uses ``prefix=""``; it is registered
in ``app/api/__init__.py`` (NOT ``main.py``). ``not_aligned`` / ``no_path`` are
business statuses returned as HTTP 200, not errors.
"""
import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_building_nav_service
from app.core.exceptions import (
    BuildingNotFoundError,
    FloorNavGraphNotFoundError,
    FloorNotFoundError,
    FloorSchemaError,
    ImageProcessingError,
)
from app.models.building_nav import (
    MultifloorRouteRequest,
    MultifloorRouteResponse,
    SaveTransitionLinksRequest,
    SaveTransitionLinksResponse,
    TransitionLinksResponse,
)
from app.services.building_nav_service import BuildingNavService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["building-nav"])
security = HTTPBearer()
# multifloor-route only: public so the end-user 3D-routes screen can compute a
# cross-floor path anonymously (read-style, no mutation). The transition-links
# GET/PUT (operator link review + overrides) stay admin-only on `security`.
optional_security = HTTPBearer(auto_error=False)


# Canonical domain-exception → HTTP-status table. Mirrors the actual ``raise``
# sites in BuildingNavService. ``ValueError`` (unknown room / missing mask dims)
# is a broad base, so it is kept LAST — no other leaf type subclasses it.
_STATUS_BY_EXC: dict[type[Exception], int] = {
    BuildingNotFoundError: status.HTTP_404_NOT_FOUND,
    FloorNotFoundError: status.HTTP_404_NOT_FOUND,
    FloorNavGraphNotFoundError: status.HTTP_404_NOT_FOUND,
    FloorSchemaError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ImageProcessingError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ValueError: status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@contextmanager
def _map_domain_errors() -> Iterator[None]:
    """Translate known service exceptions into HTTPException.

    Any exception NOT in ``_STATUS_BY_EXC`` (e.g. an unexpected IO failure) is
    re-raised unchanged so FastAPI's default handler logs the traceback / 500s.
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


@router.post("/buildings/{building_id}/multifloor-route")
async def post_multifloor_route(
    building_id: int,
    body: MultifloorRouteRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    svc: BuildingNavService = Depends(get_building_nav_service),
) -> MultifloorRouteResponse:
    """Cross-floor route (200 success/no_path/not_aligned · 404 missing · 422 room)."""
    with _map_domain_errors():
        return await svc.find_multifloor_route(
            building_id,
            body.from_floor_id,
            body.from_room,
            body.to_floor_id,
            body.to_room,
        )


@router.get("/buildings/{building_id}/transition-links")
async def get_transition_links(
    building_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: BuildingNavService = Depends(get_building_nav_service),
) -> TransitionLinksResponse:
    """Auto-matched cross-floor links + unmatched nodes (404 building missing)."""
    with _map_domain_errors():
        return await svc.list_links(building_id)


@router.put("/buildings/{building_id}/transition-links")
async def put_transition_links(
    building_id: int,
    body: SaveTransitionLinksRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: BuildingNavService = Depends(get_building_nav_service),
) -> SaveTransitionLinksResponse:
    """Persist operator overrides (404 building · 422 invalid force)."""
    with _map_domain_errors():
        return await svc.save_overrides(building_id, body.overrides)
