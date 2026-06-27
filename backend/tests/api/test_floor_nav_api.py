"""API tests for the floor-nav router.

Style mirrors ``test_floor_assembly_api.py``: the service is fully mocked and
injected via ``app.dependency_overrides[get_floor_nav_service]``; the tests assert
the thin router's contract — the exception→HTTP table and the JSON shapes.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from main import app
from app.api.deps import get_floor_nav_service
from app.core.exceptions import (
    FloorAssemblyConflictError,
    FloorNavGraphNotFoundError,
    FloorNotFoundError,
    FloorSchemaError,
)


def _mock_svc() -> MagicMock:
    svc = MagicMock()
    svc.build_floor_nav_graph = AsyncMock()
    svc.find_floor_route = AsyncMock()
    svc.get_floor_rooms_3d = AsyncMock()
    svc.get_floor_nav_graph_2d = AsyncMock()
    return svc


def _use(svc: MagicMock) -> None:
    app.dependency_overrides[get_floor_nav_service] = lambda: svc


def _clear() -> None:
    app.dependency_overrides.pop(get_floor_nav_service, None)


# build-floor-graph


@pytest.mark.asyncio
async def test_build_floor_graph_valid_floor_200(client, auth_headers):
    svc = _mock_svc()
    svc.build_floor_nav_graph.return_value = {
        "floor_id": 1,
        "nodes_count": 312,
        "edges_count": 287,
        "rooms_count": 14,
        "corridor_nodes_count": 298,
        "canvas_size_px": [1200, 900],
        "scale_factor": 0.0096,
    }
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/build-floor-graph", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes_count"] == 312
        assert data["rooms_count"] == 14
        assert data["canvas_size_px"] == [1200, 900]
    finally:
        _clear()


@pytest.mark.asyncio
async def test_build_floor_graph_200_includes_rooms_on_corridor(client, auth_headers):
    svc = _mock_svc()
    svc.build_floor_nav_graph.return_value = {
        "floor_id": 1,
        "nodes_count": 312,
        "edges_count": 287,
        "rooms_count": 14,
        "corridor_nodes_count": 298,
        "rooms_on_corridor": 14,
        "canvas_size_px": [1200, 900],
        "scale_factor": 0.0096,
    }
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/build-floor-graph", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rooms_on_corridor"] == 14
    finally:
        _clear()


@pytest.mark.asyncio
async def test_build_floor_graph_unknown_floor_404(client, auth_headers):
    svc = _mock_svc()
    svc.build_floor_nav_graph.side_effect = FloorNotFoundError(99)
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/99/build-floor-graph", headers=auth_headers
        )
        assert resp.status_code == 404
    finally:
        _clear()


@pytest.mark.asyncio
async def test_build_floor_graph_no_transforms_409(client, auth_headers):
    svc = _mock_svc()
    svc.build_floor_nav_graph.side_effect = FloorAssemblyConflictError(
        "Нет секций с рассчитанными преобразованиями"
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/build-floor-graph", headers=auth_headers
        )
        assert resp.status_code == 409
    finally:
        _clear()


@pytest.mark.asyncio
async def test_build_floor_graph_no_ppm_422(client, auth_headers):
    svc = _mock_svc()
    svc.build_floor_nav_graph.side_effect = FloorSchemaError(
        "Нет метрического масштаба — запустите расчёт преобразований"
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/build-floor-graph", headers=auth_headers
        )
        assert resp.status_code == 422
    finally:
        _clear()


# route


@pytest.mark.asyncio
async def test_floor_route_valid_rooms_200(client, auth_headers):
    svc = _mock_svc()
    svc.find_floor_route.return_value = {
        "floor_id": 1,
        "status": "found",
        "path_3d": [[1.23, 0.1, -4.56], [2.10, 0.1, -4.56]],
        "total_distance_m": 12.4,
        "from_room_id": "abc",
        "to_room_id": "def",
    }
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/floors/1/route?from_room=abc&to_room=def",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "found"
        assert len(data["path_3d"]) == 2
        assert data["total_distance_m"] == 12.4
    finally:
        _clear()


@pytest.mark.asyncio
async def test_floor_route_disconnected_200_no_path(client, auth_headers):
    svc = _mock_svc()
    svc.find_floor_route.return_value = {
        "floor_id": 1,
        "status": "no_path",
        "path_3d": [],
        "total_distance_m": None,
        "from_room_id": "abc",
        "to_room_id": "def",
    }
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/floors/1/route?from_room=abc&to_room=def",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_path"
        assert data["path_3d"] == []
        assert data["total_distance_m"] is None
    finally:
        _clear()


@pytest.mark.asyncio
async def test_floor_route_no_graph_404(client, auth_headers):
    svc = _mock_svc()
    svc.find_floor_route.side_effect = FloorNavGraphNotFoundError(1)
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/floors/1/route?from_room=abc&to_room=def",
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        _clear()


@pytest.mark.asyncio
async def test_floor_route_unknown_from_room_422(client, auth_headers):
    svc = _mock_svc()
    svc.find_floor_route.side_effect = ValueError("Комната 'x' не найдена в графе")
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/floors/1/route?from_room=x&to_room=def",
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        _clear()


@pytest.mark.asyncio
async def test_floor_route_unknown_to_room_422(client, auth_headers):
    svc = _mock_svc()
    svc.find_floor_route.side_effect = ValueError("Комната 'y' не найдена в графе")
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/floors/1/route?from_room=abc&to_room=y",
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        _clear()


# rooms-3d


@pytest.mark.asyncio
async def test_floor_rooms_3d_200(client, auth_headers):
    svc = _mock_svc()
    svc.get_floor_rooms_3d.return_value = [
        {
            "id": "abc",
            "name": "Аудитория 301",
            "room_type": "room",
            "position": [1.5, 1.5, -3.2],
            "size": [4.0, 3.0, 5.0],
        }
    ]
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/1/rooms-3d", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["floor_id"] == 1
        assert len(data["rooms"]) == 1
        assert data["rooms"][0]["id"] == "abc"
        assert data["rooms"][0]["position"] == [1.5, 1.5, -3.2]
    finally:
        _clear()


@pytest.mark.asyncio
async def test_floor_rooms_3d_no_graph_200_empty(client, auth_headers):
    svc = _mock_svc()
    svc.get_floor_rooms_3d.return_value = []
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/1/rooms-3d", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["rooms"] == []
    finally:
        _clear()


@pytest.mark.asyncio
async def test_floor_rooms_3d_public_no_auth_200(client):
    """rooms-3d is public (optional bearer) — the end-user 3D-routes screen lists
    pickable cabinets anonymously. No token still returns 200."""
    svc = _mock_svc()
    svc.get_floor_rooms_3d.return_value = []
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/1/rooms-3d")
        assert resp.status_code == 200
        svc.get_floor_rooms_3d.assert_called_once()
    finally:
        _clear()


# nav-graph-2d


@pytest.mark.asyncio
async def test_floor_nav_graph_2d_200(client, auth_headers):
    svc = _mock_svc()
    svc.get_floor_nav_graph_2d.return_value = {
        "metadata": {
            "nodes_count": 2,
            "edges_count": 1,
            "room_nodes": ["room_abc"],
            "door_nodes": [],
            "mask_width": 1200,
            "mask_height": 900,
        },
        "graph": {
            "nodes": [
                {
                    "id": "room_abc",
                    "type": "room",
                    "pos": [120.0, 340.0],
                    "room_name": "Аудитория 301",
                },
                {"id": 5, "type": "corridor_node", "pos": [50.0, 60.0]},
            ],
            "edges": [
                {
                    "source": "room_abc",
                    "target": 5,
                    "type": "corridor_edge",
                    "pts": [[120.0, 340.0], [50.0, 60.0]],
                }
            ],
        },
    }
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/floors/1/nav-graph-2d", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["nodes_count"] == 2
        assert data["metadata"]["room_nodes"] == ["room_abc"]
        assert "edges" in data["graph"] and "links" not in data["graph"]
        assert data["graph"]["nodes"][0]["pos"] == [120.0, 340.0]
        assert data["graph"]["edges"][0]["source"] == "room_abc"
    finally:
        _clear()


@pytest.mark.asyncio
async def test_floor_nav_graph_2d_no_graph_404(client, auth_headers):
    svc = _mock_svc()
    svc.get_floor_nav_graph_2d.side_effect = FloorNavGraphNotFoundError(1)
    _use(svc)
    try:
        resp = await client.get(
            "/api/v1/floors/1/nav-graph-2d", headers=auth_headers
        )
        assert resp.status_code == 404
    finally:
        _clear()
