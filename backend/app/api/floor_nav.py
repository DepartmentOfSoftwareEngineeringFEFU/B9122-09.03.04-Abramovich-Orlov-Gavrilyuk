"""API routes for the Floor Nav Graph feature (connector-editor-navgraph).

Three thin endpoints — build the floor nav graph, find a route between two rooms,
and read room 3D bboxes. Each route does only: validate → call ``FloorNavService``
→ return. ALL business logic lives in the service; the router's sole extra job is
mapping domain exceptions onto HTTP status codes via the single ``_STATUS_BY_EXC``
table (mirrors ``floor_assembly.py``).

Paths already carry ``/floors/...`` so the router uses ``prefix=""``; it is
registered in ``app/api/__init__.py`` (NOT ``main.py``).
"""
import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import get_floor_nav_service
from app.core.exceptions import (
    FloorAssemblyConflictError,
    FloorNavGraphNotFoundError,
    FloorNotFoundError,
    FloorSchemaError,
    ImageProcessingError,
)
from app.services.floor_nav_service import FloorNavService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["floor-nav"])
security = HTTPBearer()
# rooms-3d only: public so the end-user 3D-routes screen can list room labels /
# pickable cabinets anonymously. The graph-building / route / 2d endpoints stay
# admin-only on `security`. Optional bearer accepts but ignores any token.
optional_security = HTTPBearer(auto_error=False)


# Canonical domain-exception → HTTP-status table. Mirrors the actual ``raise``
# sites in FloorNavService. ``ValueError`` (unknown room id) is a broad base, so it
# is kept LAST — none of the other leaf types subclass it, so the ordering is safe.
_STATUS_BY_EXC: dict[type[Exception], int] = {
    FloorNotFoundError: status.HTTP_404_NOT_FOUND,
    FloorNavGraphNotFoundError: status.HTTP_404_NOT_FOUND,
    FloorAssemblyConflictError: status.HTTP_409_CONFLICT,
    FloorSchemaError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ImageProcessingError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ValueError: status.HTTP_422_UNPROCESSABLE_ENTITY,  # unknown room id
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


@router.post("/floors/{floor_id}/build-floor-graph")
async def build_floor_graph(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorNavService = Depends(get_floor_nav_service),
) -> dict:
    """Build the floor nav graph (404 floor · 409 no transforms · 422 no ppm/empty)."""
    with _map_domain_errors():
        return await svc.build_floor_nav_graph(floor_id)


@router.get("/floors/{floor_id}/route")
async def get_floor_route(
    floor_id: int,
    from_room: str = Query(...),
    to_room: str = Query(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorNavService = Depends(get_floor_nav_service),
) -> dict:
    """Route between two rooms (404 graph not built · 422 unknown room)."""
    with _map_domain_errors():
        return await svc.find_floor_route(floor_id, from_room, to_room)


@router.get("/floors/{floor_id}/nav-graph-2d")
async def get_floor_nav_graph_2d(
    floor_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    svc: FloorNavService = Depends(get_floor_nav_service),
) -> dict:
    """2D nav-graph node/edge data for visualization (404 if graph not built)."""
    with _map_domain_errors():
        return await svc.get_floor_nav_graph_2d(floor_id)


@router.get("/floors/{floor_id}/rooms-3d")
async def get_floor_rooms_3d(
    floor_id: int,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    svc: FloorNavService = Depends(get_floor_nav_service),
) -> dict:
    """Room bboxes in floor 3D coords (200 empty list if graph not built)."""
    with _map_domain_errors():
        rooms = await svc.get_floor_rooms_3d(floor_id)
        return {"floor_id": floor_id, "rooms": rooms}
