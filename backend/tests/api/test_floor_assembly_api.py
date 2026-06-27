"""API tests for the floor-assembly router (-).

Style mirrors ``test_floors_api.py``: the service is fully mocked and injected via
``app.dependency_overrides[get_floor_assembly_service]``; the tests assert the thin
router's contract — status codes (the exception→HTTP table) and the JSON shapes.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from main import app
from app.api.deps import get_floor_assembly_service
from app.core.exceptions import (
    FloorAssemblyConflictError,
    FloorNotFoundError,
    FloorSchemaError,
    PreviewNotFoundError,
    SectionValidationError,
)
from app.models.floor_assembly import (
    AssemblySection,
    BuildFloorPreviewResponse,
    BuildWarning,
    ConfirmMeshResponse,
    Connector,
    ConnectorsResponse,
    Cutout,
    CutoutsResponse,
    ExcludedSection,
    FloorAssemblyResponse,
    MasterControlPoint,
    MasterSchemaInfo,
    SectionControlPointsResponse,
    SolveSectionResult,
    SolveTransformsResponse,
)


def _mock_svc() -> MagicMock:
    svc = MagicMock()
    svc.save_section_control_points = AsyncMock()
    svc.solve_transforms = AsyncMock()
    svc.get_connectors = AsyncMock()
    svc.replace_connectors = AsyncMock()
    svc.get_cutouts = AsyncMock()
    svc.replace_cutouts = AsyncMock()
    svc.build_floor_mesh = AsyncMock()
    svc.confirm_floor_mesh = AsyncMock()
    svc.get_assembly = AsyncMock()
    return svc


def _use(svc: MagicMock) -> None:
    app.dependency_overrides[get_floor_assembly_service] = lambda: svc


def _clear() -> None:
    app.dependency_overrides.pop(get_floor_assembly_service, None)


#PUT master control points


@pytest.mark.asyncio
async def test_put_master_points_happy_returns_200(client, auth_headers):
    svc = _mock_svc()
    svc.save_section_control_points.return_value = SectionControlPointsResponse(
        section_id=10,
        points=[MasterControlPoint(point_id="cp-1", x=0.5, y=0.5)],
        section_point_ids=["cp-1", "cp-2"],
        matched_ids=["cp-1"],
        unmatched_ids=["cp-2"],
    )
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/sections/10/control-points",
            json={"points": [{"point_id": "cp-1", "x": 0.5, "y": 0.5}]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["section_id"] == 10
        assert data["matched_ids"] == ["cp-1"]
        assert data["unmatched_ids"] == ["cp-2"]
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_master_points_unknown_id_returns_422(client, auth_headers):
    svc = _mock_svc()
    svc.save_section_control_points.side_effect = SectionValidationError(
        "point_id cp-9 is not a control point of the section"
    )
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/sections/10/control-points",
            json={"points": [{"point_id": "cp-9", "x": 0.5, "y": 0.5}]},
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        _clear()


#POST solve-transforms


@pytest.mark.asyncio
async def test_solve_transforms_happy_pins_status_enum_strings(client, auth_headers):
    """Happy solve — the ok/needs_points/degenerate status strings round-trip."""
    svc = _mock_svc()
    svc.solve_transforms.return_value = SolveTransformsResponse(
        floor_id=1,
        pixels_per_meter=50.0,
        anchor_section_id=10,
        sections=[
            SolveSectionResult(section_id=10, status="ok"),
            SolveSectionResult(section_id=20, status="needs_points"),
            SolveSectionResult(section_id=30, status="degenerate"),
        ],
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/solve-transforms", headers=auth_headers
        )
        assert resp.status_code == 200
        statuses = {s["section_id"]: s["status"] for s in resp.json()["sections"]}
        assert statuses == {10: "ok", 20: "needs_points", 30: "degenerate"}
    finally:
        _clear()


@pytest.mark.asyncio
async def test_solve_transforms_floor_not_found_returns_404(client, auth_headers):
    svc = _mock_svc()
    svc.solve_transforms.side_effect = FloorNotFoundError(99)
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/99/solve-transforms", headers=auth_headers
        )
        assert resp.status_code == 404
    finally:
        _clear()


@pytest.mark.asyncio
async def test_solve_transforms_no_sections_returns_409(client, auth_headers):
    svc = _mock_svc()
    svc.solve_transforms.side_effect = FloorAssemblyConflictError(
        "No sections bound to plans"
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/solve-transforms", headers=auth_headers
        )
        assert resp.status_code == 409
    finally:
        _clear()


#connectors


@pytest.mark.asyncio
async def test_get_connectors_returns_connectors_response_shape(client, auth_headers):
    svc = _mock_svc()
    svc.get_connectors.return_value = ConnectorsResponse(
        floor_id=1,
        connectors=[
            Connector(id=1, points=[(0.1, 0.1), (0.2, 0.2)], thickness_m=0.15)
        ],
    )
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/1/connectors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["floor_id"] == 1
        assert len(data["connectors"]) == 1
        assert data["connectors"][0]["id"] == 1
        assert data["connectors"][0]["points"] == [[0.1, 0.1], [0.2, 0.2]]
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_connectors_happy_returns_200(client, auth_headers):
    svc = _mock_svc()
    svc.replace_connectors.return_value = ConnectorsResponse(floor_id=1, connectors=[])
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/connectors",
            json={"connectors": [{"points": [[0.1, 0.1], [0.2, 0.2]]}]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["connectors"] == []
    finally:
        _clear()


@pytest.mark.asyncio
async def test_connectors_line_too_few_points_returns_422(client, auth_headers):
    """A 1-vertex connector line is rejected by the request model (422)."""
    svc = _mock_svc()
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/connectors",
            json={"connectors": [{"points": [[0.1, 0.1]]}]},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        svc.replace_connectors.assert_not_called()
    finally:
        _clear()


#cutouts
# NOTE: the design contract labels validation failures "400", but FastAPI returns
# 422 for Pydantic request-body validation (same as the connector slice above).


@pytest.mark.asyncio
async def test_get_cutouts_200(client, auth_headers):
    svc = _mock_svc()
    svc.get_cutouts.return_value = CutoutsResponse(
        floor_id=1,
        cutouts=[
            Cutout(id=0, points=[(0.4, 0.5), (0.55, 0.5), (0.55, 0.62), (0.4, 0.62)])
        ],
    )
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/1/cutouts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["floor_id"] == 1
        assert len(data["cutouts"]) == 1
        assert data["cutouts"][0]["id"] == 0
        assert data["cutouts"][0]["points"][0] == [0.4, 0.5]
    finally:
        _clear()


@pytest.mark.asyncio
async def test_get_cutouts_floor_not_found_404(client, auth_headers):
    svc = _mock_svc()
    svc.get_cutouts.side_effect = FloorNotFoundError(99)
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/99/cutouts", headers=auth_headers)
        assert resp.status_code == 404
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_cutouts_valid_200(client, auth_headers):
    svc = _mock_svc()
    svc.replace_cutouts.return_value = CutoutsResponse(
        floor_id=1,
        cutouts=[
            Cutout(id=0, points=[(0.4, 0.5), (0.55, 0.5), (0.55, 0.62), (0.4, 0.62)])
        ],
    )
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/cutouts",
            json={"cutouts": [
                {"points": [[0.4, 0.5], [0.55, 0.5], [0.55, 0.62], [0.4, 0.62]]}
            ]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["cutouts"][0]["id"] == 0
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_cutouts_empty_clears_200(client, auth_headers):
    svc = _mock_svc()
    svc.replace_cutouts.return_value = CutoutsResponse(floor_id=1, cutouts=[])
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/cutouts",
            json={"cutouts": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["cutouts"] == []
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_cutouts_coord_out_of_range_422(client, auth_headers):
    """A coord outside [0,1] is rejected by the request model (422)."""
    svc = _mock_svc()
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/cutouts",
            json={"cutouts": [{"points": [[0.4, 0.5], [1.4, 0.5], [0.55, 0.62]]}]},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        svc.replace_cutouts.assert_not_called()
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_cutouts_too_few_points_422(client, auth_headers):
    """A 2-vertex cutout (needs >= 3 for an area) is rejected by the model (422)."""
    svc = _mock_svc()
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/1/cutouts",
            json={"cutouts": [{"points": [[0.4, 0.5], [0.55, 0.5]]}]},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        svc.replace_cutouts.assert_not_called()
    finally:
        _clear()


@pytest.mark.asyncio
async def test_put_cutouts_floor_not_found_404(client, auth_headers):
    svc = _mock_svc()
    svc.replace_cutouts.side_effect = FloorNotFoundError(99)
    _use(svc)
    try:
        resp = await client.put(
            "/api/v1/floors/99/cutouts",
            json={"cutouts": [{"points": [[0.4, 0.5], [0.55, 0.5], [0.55, 0.62]]}]},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        _clear()


#build / confirm


@pytest.mark.asyncio
async def test_build_mesh_happy_pins_excluded_reason(client, auth_headers):
    """Build 200 — persisted=False and the 'mask_missing' excluded reason round-trips."""
    svc = _mock_svc()
    svc.build_floor_mesh.return_value = BuildFloorPreviewResponse(
        floor_id=1,
        glb_file_id="floor-1-preview-abcd1234",
        glb_url="/api/v1/uploads/models/floor-1-preview-abcd1234.glb",
        persisted=False,
        pixels_per_meter=50.0,
        canvas_size_px=(800, 600),
        included_sections=[10],
        excluded_sections=[ExcludedSection(section_id=20, reason="mask_missing")],
        warnings=[BuildWarning(section_id=10, code="low_detail", message="low res")],
        connector_count=2,
        cutout_count=1,
    )
    _use(svc)
    try:
        resp = await client.post("/api/v1/floors/1/build-mesh", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["persisted"] is False
        assert data["glb_file_id"] == "floor-1-preview-abcd1234"
        assert data["excluded_sections"][0]["reason"] == "mask_missing"
        assert data["warnings"][0]["code"] == "low_detail"
        assert data["connector_count"] == 2
        assert data["cutout_count"] == 1
    finally:
        _clear()


@pytest.mark.asyncio
async def test_build_mesh_no_transform_returns_409(client, auth_headers):
    svc = _mock_svc()
    svc.build_floor_mesh.side_effect = FloorAssemblyConflictError(
        "Run solve-transforms first"
    )
    _use(svc)
    try:
        resp = await client.post("/api/v1/floors/1/build-mesh", headers=auth_headers)
        assert resp.status_code == 409
    finally:
        _clear()


@pytest.mark.asyncio
async def test_build_mesh_empty_mask_returns_422(client, auth_headers):
    svc = _mock_svc()
    svc.build_floor_mesh.side_effect = FloorSchemaError("Empty floor mask")
    _use(svc)
    try:
        resp = await client.post("/api/v1/floors/1/build-mesh", headers=auth_headers)
        assert resp.status_code == 422
    finally:
        _clear()


@pytest.mark.asyncio
async def test_confirm_mesh_happy_returns_200(client, auth_headers):
    svc = _mock_svc()
    svc.confirm_floor_mesh.return_value = ConfirmMeshResponse(
        floor_id=1,
        mesh_file_glb="models/floor-1.glb",
        glb_url="/api/v1/uploads/models/floor-1.glb",
        persisted=True,
    )
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/confirm-mesh",
            json={"glb_file_id": "floor-1-preview-abcd1234"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["persisted"] is True
        assert data["mesh_file_glb"] == "models/floor-1.glb"
    finally:
        _clear()


@pytest.mark.asyncio
async def test_confirm_mesh_unknown_preview_returns_422(client, auth_headers):
    svc = _mock_svc()
    svc.confirm_floor_mesh.side_effect = PreviewNotFoundError("floor-1-preview-deadbeef")
    _use(svc)
    try:
        resp = await client.post(
            "/api/v1/floors/1/confirm-mesh",
            json={"glb_file_id": "floor-1-preview-deadbeef"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
    finally:
        _clear()


# Assembly read


@pytest.mark.asyncio
async def test_assembly_returns_full_payload_shape(client, auth_headers):
    svc = _mock_svc()
    svc.get_assembly.return_value = FloorAssemblyResponse(
        floor_id=1,
        pixels_per_meter=50.0,
        mesh_file_glb=None,
        master_schema=MasterSchemaInfo(
            image_id="schema-1",
            url="/api/v1/uploads/plans/schema-1.png",
            crop_bbox=None,
            size_px=(3200, 2400),
            wall_polygons=[[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9)]],
        ),
        sections=[
            AssemblySection(
                section_id=10,
                number=1,
                reconstruction_id=5,
                mask_file_id="mask-1",
                mask_url="/api/v1/uploads/masks/mask-1.png",
                image_size_cropped=(800, 600),
                section_control_points=[],
                master_control_points=[],
                transform=None,
                status="needs_points",
            )
        ],
        connectors=[],
    )
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/1/assembly", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["floor_id"] == 1
        assert data["master_schema"]["image_id"] == "schema-1"
        # Vectorised карта отсеков is echoed for the master backdrop.
        assert data["master_schema"]["wall_polygons"] == [
            [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]
        ]
        assert data["sections"][0]["status"] == "needs_points"
        # Section's cropped-mask URL is exposed for the эталон backdrop.
        assert data["sections"][0]["mask_url"] == "/api/v1/uploads/masks/mask-1.png"
        assert data["connectors"] == []
    finally:
        _clear()


@pytest.mark.asyncio
async def test_assembly_floor_not_found_returns_404(client, auth_headers):
    svc = _mock_svc()
    svc.get_assembly.side_effect = FloorNotFoundError(99)
    _use(svc)
    try:
        resp = await client.get("/api/v1/floors/99/assembly", headers=auth_headers)
        assert resp.status_code == 404
    finally:
        _clear()
