"""
Tests for NavService.find_multifloor_route() — mocks repos and file I/O.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import networkx as nx

from app.processing.nav_graph import FloorGraphData, serialize_nav_graph
from app.services.nav_service import NavService
from app.core.exceptions import NavGraphNotFoundError


def _make_recon(id: int, building_id: str = "A", floor_number: int = 1):
    r = MagicMock()
    r.id = id
    r.building_id = building_id
    r.name = f"Floor {id}"
    r.floor_number = floor_number
    # NavService reads the floor *relationship* (recon.floor.number) for 3D
    # stacking, so the mock must expose it — otherwise an unconfigured MagicMock
    # is coerced to 1.0 and the per-floor Y offset is wrong.
    r.floor = MagicMock(number=floor_number)
    r.mask_file_id = f"mask_{id}"
    return r


def _make_transition(from_id: int = 1, to_id: int = 2):
    t = MagicMock()
    t.id = 10
    t.name = "Лестница А"
    t.building_id = "A"
    t.from_reconstruction_id = from_id
    t.from_x = 0.5
    t.from_y = 0.5
    t.to_reconstruction_id = to_id
    t.to_x = 0.5
    t.to_y = 0.5
    return t


def _make_simple_nav_data(mask_width: int = 100, mask_height: int = 100) -> dict:
    """Build a minimal serialized nav graph with two rooms and a corridor."""
    G = nx.Graph()
    G.add_node("room_A", type="room", pos=(10.0, 50.0), room_name="A")
    G.add_node("corridor_1", type="corridor_node", pos=(50.0, 50.0))
    G.add_node("room_B", type="room", pos=(90.0, 50.0), room_name="B")
    G.add_edge("room_A", "corridor_1", weight=40.0, type="room_to_door")
    G.add_edge("corridor_1", "room_B", weight=40.0, type="room_to_door")
    return serialize_nav_graph(G, mask_width, mask_height, scale_factor=0.02)


@pytest.mark.asyncio
async def test_find_multifloor_same_floor_delegates_to_single_floor():
    """When from == to reconstruction, delegates to find_route()."""
    service = NavService(upload_dir="/tmp")
    ft_repo = AsyncMock()
    recon_repo = AsyncMock()
    recon_repo.get_by_id.return_value = _make_recon(1, floor_number=1)

    expected_result = {
        "status": "success",
        "total_distance_meters": 10.0,
        "estimated_time_seconds": 8,
        "coordinates": [[1.0, 0.1, -1.0]],
        "from_room_3d": None,
        "to_room_3d": None,
    }

    with patch.object(service, "find_route", new=AsyncMock(return_value=expected_result)):
        result = await service.find_multifloor_route(
            building_id="A",
            from_reconstruction_id=1,
            from_room_id="A",
            to_reconstruction_id=1,
            to_room_id="B",
            ft_repo=ft_repo,
            recon_repo=recon_repo,
        )

    assert result.status == "success"
    assert len(result.path_segments) == 1
    ft_repo.get_by_building.assert_not_called()


@pytest.mark.asyncio
async def test_find_multifloor_two_floors_returns_result():
    """Two floors with a transition → returns MultifloorRouteResponse."""
    service = NavService(upload_dir="/tmp")
    ft_repo = AsyncMock()
    recon_repo = AsyncMock()

    ft_repo.get_by_building.return_value = [_make_transition(1, 2)]
    recon_repo.get_by_id.side_effect = lambda id: _make_recon(id, floor_number=id)

    nav_data = _make_simple_nav_data()

    with patch.object(service, "load_graph", return_value=nav_data):
        result = await service.find_multifloor_route(
            building_id="A",
            from_reconstruction_id=1,
            from_room_id="A",
            to_reconstruction_id=2,
            to_room_id="B",
            ft_repo=ft_repo,
            recon_repo=recon_repo,
        )

    assert result.status in ("success", "no_path")


@pytest.mark.asyncio
async def test_find_multifloor_missing_graph_raises_error():
    """FileNotFoundError from load_graph → NavGraphNotFoundError."""
    service = NavService(upload_dir="/tmp")
    ft_repo = AsyncMock()
    recon_repo = AsyncMock()

    ft_repo.get_by_building.return_value = [_make_transition(1, 2)]
    recon_repo.get_by_id.side_effect = lambda id: _make_recon(id, floor_number=id)

    with patch.object(service, "load_graph", side_effect=FileNotFoundError("not found")):
        with pytest.raises(NavGraphNotFoundError):
            await service.find_multifloor_route(
                building_id="A",
                from_reconstruction_id=1,
                from_room_id="A",
                to_reconstruction_id=2,
                to_room_id="B",
                ft_repo=ft_repo,
                recon_repo=recon_repo,
            )


@pytest.mark.asyncio
async def test_find_multifloor_no_path_returns_no_path_status():
    """No transitions → no path → status='no_path'."""
    service = NavService(upload_dir="/tmp")
    ft_repo = AsyncMock()
    recon_repo = AsyncMock()

    ft_repo.get_by_building.return_value = []
    recon_repo.get_by_id.side_effect = lambda id: _make_recon(id, floor_number=id)

    nav_data = _make_simple_nav_data()

    with patch.object(service, "load_graph", return_value=nav_data):
        result = await service.find_multifloor_route(
            building_id="A",
            from_reconstruction_id=1,
            from_room_id="A",
            to_reconstruction_id=2,
            to_room_id="B",
            ft_repo=ft_repo,
            recon_repo=recon_repo,
        )

    assert result.status == "no_path"


@pytest.mark.asyncio
async def test_find_multifloor_y_offset_per_floor_in_3d_coords():
    """y coordinate in 3D = floor_number * FLOOR_HEIGHT_METERS + 0.1."""
    from app.processing.nav_graph import FLOOR_HEIGHT_METERS

    service = NavService(upload_dir="/tmp")
    ft_repo = AsyncMock()
    recon_repo = AsyncMock()

    ft_repo.get_by_building.return_value = [_make_transition(1, 2)]
    recon_repo.get_by_id.side_effect = lambda id: _make_recon(id, floor_number=id)

    nav_data = _make_simple_nav_data()

    with patch.object(service, "load_graph", return_value=nav_data):
        result = await service.find_multifloor_route(
            building_id="A",
            from_reconstruction_id=1,
            from_room_id="A",
            to_reconstruction_id=2,
            to_room_id="B",
            ft_repo=ft_repo,
            recon_repo=recon_repo,
        )

    if result.status == "success":
        for seg in result.path_segments:
            expected_y = seg.floor_number * FLOOR_HEIGHT_METERS + 0.1
            for coord in seg.coordinates_3d:
                assert abs(coord[1] - expected_y) < 0.01, (
                    f"y={coord[1]} expected ~{expected_y} for floor {seg.floor_number}"
                )
