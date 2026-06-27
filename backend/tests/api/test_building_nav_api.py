"""API tests for the building-nav router (subfeature D).

 (API section, 8
tests). Style mirrors ``test_building_scene_api.py``: the service is fully mocked
and injected via ``app.dependency_overrides[get_building_nav_service]``; the tests
assert the thin router's contract — status codes + the JSON shape from
. ``not_aligned`` is a 200 body status, not an HTTP error.

POST multifloor-route is public (optional bearer) so the end-user 3D-routes
screen can compute a path anonymously; transition-links GET/PUT stay admin-only.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.deps import get_building_nav_service
from app.core.exceptions import BuildingNotFoundError, FloorNavGraphNotFoundError
from app.models.building_nav import (
    FloorPathSegment3D,
    MultifloorRouteResponse,
    SaveTransitionLinksResponse,
    TransitionLink,
    TransitionLinksResponse,
    TransitionUsed3D,
    UnmatchedTransition,
)
from main import app


def _mock_svc() -> MagicMock:
    svc = MagicMock()
    svc.find_multifloor_route = AsyncMock()
    svc.list_links = AsyncMock()
    svc.save_overrides = AsyncMock()
    return svc


def _use(svc: MagicMock) -> None:
    app.dependency_overrides[get_building_nav_service] = lambda: svc


def _clear() -> None:
    app.dependency_overrides.pop(get_building_nav_service, None)


_ROUTE_BODY = {
    "from_floor_id": 10, "from_room": "A", "to_floor_id": 20, "to_room": "B",
}


# POST multifloor-route


@pytest.mark.asyncio
async def test_multifloor_route_valid_200(client, auth_headers):
    svc = _mock_svc()
    svc.find_multifloor_route.return_value = MultifloorRouteResponse(
        status="success",
        total_distance_meters=19.0,
        estimated_time_seconds=16,
        path_segments=[
            FloorPathSegment3D(
                floor_id=10, floor_number=1,
                coordinates_3d=[[1.0, 0.1, -2.0], [3.0, 0.1, -2.0]],
            ),
            FloorPathSegment3D(
                floor_id=20, floor_number=2,
                coordinates_3d=[[3.0, 3.1, -2.0], [8.0, 3.1, -1.0]],
            ),
        ],
        transitions_used=[
            TransitionUsed3D(
                type="staircase", from_3d=[3.0, 0.1, -2.0], to_3d=[3.0, 3.1, -2.0],
                from_floor_id=10, to_floor_id=20,
            )
        ],
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/buildings/3/multifloor-route", json=_ROUTE_BODY, headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["path_segments"]) == 2
        assert data["path_segments"][1]["floor_number"] == 2
        assert data["transitions_used"][0]["type"] == "staircase"
    finally:
        _clear()


@pytest.mark.asyncio
async def test_multifloor_route_unaligned_status(client, auth_headers):
    """A not-aligned building returns HTTP 200 with status=not_aligned (not an error)."""
    svc = _mock_svc()
    svc.find_multifloor_route.return_value = MultifloorRouteResponse(
        status="not_aligned", message="Этажи не выровнены — выполните сборку здания"
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/buildings/3/multifloor-route", json=_ROUTE_BODY, headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_aligned"
        assert data["path_segments"] == []
        assert data["message"]
    finally:
        _clear()


@pytest.mark.asyncio
async def test_multifloor_route_missing_404(client, auth_headers):
    svc = _mock_svc()
    svc.find_multifloor_route.side_effect = FloorNavGraphNotFoundError(20)
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/buildings/3/multifloor-route", json=_ROUTE_BODY, headers=auth_headers
        )
        assert resp.status_code == 404
    finally:
        _clear()


@pytest.mark.asyncio
async def test_multifloor_route_unknown_room_422(client, auth_headers):
    svc = _mock_svc()
    svc.find_multifloor_route.side_effect = ValueError("Комната 'X' не найдена в графе")
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/buildings/3/multifloor-route", json=_ROUTE_BODY, headers=auth_headers
        )
        assert resp.status_code == 422
    finally:
        _clear()


@pytest.mark.asyncio
async def test_multifloor_route_public_no_auth_200(client):
    """Public compute: no bearer token still returns 200 (end-user 3D-routes screen)."""
    svc = _mock_svc()
    svc.find_multifloor_route.return_value = MultifloorRouteResponse(status="no_path")
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/buildings/3/multifloor-route", json=_ROUTE_BODY
        )
        assert resp.status_code == 200
        svc.find_multifloor_route.assert_called_once()
    finally:
        _clear()


# GET / PUT transition-links


@pytest.mark.asyncio
async def test_transition_links_list_200(client, auth_headers):
    svc = _mock_svc()
    svc.list_links.return_value = TransitionLinksResponse(
        building_id=3,
        links=[
            TransitionLink(
                lower_floor_id=10, lower_floor_number=1, lower_node="room_s1",
                upper_floor_id=20, upper_floor_number=2, upper_node="room_s2",
                type="staircase", source="auto", enabled=True, distance_m=0.4,
            )
        ],
        unmatched=[
            UnmatchedTransition(
                floor_id=10, floor_number=1, node="room_e1",
                type="elevator", reason="no_partner_within_tolerance",
            )
        ],
    )
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/buildings/3/transition-links", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["building_id"] == 3
        assert data["links"][0]["enabled"] is True
        assert data["links"][0]["type"] == "staircase"
        assert data["unmatched"][0]["node"] == "room_e1"
    finally:
        _clear()


@pytest.mark.asyncio
async def test_transition_links_missing_building_404(client, auth_headers):
    svc = _mock_svc()
    svc.list_links.side_effect = BuildingNotFoundError(999)
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/buildings/999/transition-links", headers=auth_headers
        )
        assert resp.status_code == 404
    finally:
        _clear()


@pytest.mark.asyncio
async def test_transition_links_save_200(client, auth_headers):
    svc = _mock_svc()
    svc.save_overrides.return_value = SaveTransitionLinksResponse(
        building_id=3, overrides_count=2
    )
    body = {
        "overrides": [
            {"lower_floor_id": 10, "lower_node": "room_s1", "upper_floor_id": 20,
             "upper_node": "room_s2", "action": "disable"},
            {"lower_floor_id": 20, "lower_node": "room_e1", "upper_floor_id": 30,
             "upper_node": "room_e2", "action": "force"},
        ]
    }
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/buildings/3/transition-links", json=body, headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["overrides_count"] == 2
    finally:
        _clear()


@pytest.mark.asyncio
async def test_transition_links_force_invalid_422(client, auth_headers):
    svc = _mock_svc()
    svc.save_overrides.side_effect = ValueError(
        "force override references a node not in the graph"
    )
    body = {
        "overrides": [
            {"lower_floor_id": 10, "lower_node": "room_nope", "upper_floor_id": 20,
             "upper_node": "room_s2", "action": "force"},
        ]
    }
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/buildings/3/transition-links", json=body, headers=auth_headers
        )
        assert resp.status_code == 422
    finally:
        _clear()
