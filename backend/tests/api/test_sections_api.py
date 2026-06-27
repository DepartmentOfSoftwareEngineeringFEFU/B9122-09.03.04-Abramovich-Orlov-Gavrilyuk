"""
API tests for Section hierarchy endpoints.
6 tests covering list, replace, and delete.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from main import app
from app.api.deps import get_section_service
from app.core.exceptions import FloorNotFoundError, SectionValidationError
from app.models.sections import SectionGeometry, SectionResponse, ReconstructionBrief


def _section_resp(sid: int = 555, floor_id: int = 101, number: int = 4) -> SectionResponse:
    return SectionResponse(
        id=sid,
        floor_id=floor_id,
        number=number,
        geometry=SectionGeometry(points=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]),
        section_type=1,
        reconstruction=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _make_mock_svc():
    svc = MagicMock()
    svc.list_by_floor = AsyncMock()
    svc.replace_sections = AsyncMock()
    svc.delete_section = AsyncMock()
    return svc


# GET /api/v1/floors/{floor_id}/sections

@pytest.mark.asyncio
async def test_list_sections_returns_all_with_reconstructions(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.list_by_floor.return_value = [
        _section_resp(555, number=4),
        _section_resp(556, number=5),
    ]
    app.dependency_overrides[get_section_service] = lambda: mock_svc
    try:
        resp = await client.get("/api/v1/floors/101/sections", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["number"] == 4
    finally:
        app.dependency_overrides.pop(get_section_service, None)


# PUT /api/v1/floors/{floor_id}/sections

@pytest.mark.asyncio
async def test_replace_sections_valid_returns_200(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.replace_sections.return_value = [_section_resp(555, number=4)]
    app.dependency_overrides[get_section_service] = lambda: mock_svc
    try:
        resp = await client.put(
            "/api/v1/floors/101/sections",
            json={
                "sections": [
                    {
                        "number": 4,
                        "geometry": {
                            "points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]
                        },
                        "section_type": 1,
                        "reconstruction_id": None,
                    }
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["number"] == 4
    finally:
        app.dependency_overrides.pop(get_section_service, None)


@pytest.mark.asyncio
async def test_replace_sections_duplicate_number_returns_422(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.replace_sections.side_effect = SectionValidationError("Duplicate section number: 4")
    app.dependency_overrides[get_section_service] = lambda: mock_svc
    try:
        resp = await client.put(
            "/api/v1/floors/101/sections",
            json={
                "sections": [
                    {
                        "number": 4,
                        "geometry": {"points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]},
                        "section_type": 1,
                    },
                    {
                        "number": 4,
                        "geometry": {"points": [[0.5, 0.1], [0.8, 0.1], [0.8, 0.5], [0.5, 0.5]]},
                        "section_type": 1,
                    },
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert "Duplicate" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_section_service, None)


@pytest.mark.asyncio
async def test_replace_sections_reconstruction_already_used_returns_422(client, auth_headers):
    """duplicate reconstruction_id in payload → 422."""
    mock_svc = _make_mock_svc()
    mock_svc.replace_sections.side_effect = SectionValidationError(
        "Reconstruction 777 already used by another section in payload"
    )
    app.dependency_overrides[get_section_service] = lambda: mock_svc
    try:
        resp = await client.put(
            "/api/v1/floors/101/sections",
            json={
                "sections": [
                    {
                        "number": 4,
                        "geometry": {"points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5], [0.1, 0.5]]},
                        "reconstruction_id": 777,
                    },
                    {
                        "number": 5,
                        "geometry": {"points": [[0.5, 0.1], [0.8, 0.1], [0.8, 0.5], [0.5, 0.5]]},
                        "reconstruction_id": 777,
                    },
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        assert "777" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_section_service, None)


@pytest.mark.asyncio
async def test_replace_sections_missing_floor_returns_404(client, auth_headers):
    mock_svc = _make_mock_svc()
    mock_svc.replace_sections.side_effect = FloorNotFoundError(999)
    app.dependency_overrides[get_section_service] = lambda: mock_svc
    try:
        resp = await client.put(
            "/api/v1/floors/999/sections",
            json={"sections": []},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_section_service, None)


# DELETE /api/v1/sections/{id}

@pytest.mark.asyncio
async def test_delete_section_keeps_reconstruction_unbound(client, auth_headers):
    """DELETE section → 204. Reconstruction remains unbound (service handles that)."""
    mock_svc = _make_mock_svc()
    mock_svc.delete_section.return_value = None
    app.dependency_overrides[get_section_service] = lambda: mock_svc
    try:
        resp = await client.delete("/api/v1/sections/555", headers=auth_headers)
        assert resp.status_code == 204
        mock_svc.delete_section.assert_called_once_with(555)
    finally:
        app.dependency_overrides.pop(get_section_service, None)
