"""Pydantic models for the Floor Stitching feature.

These models ARE the contract — request validation and response serialisation
both flow through here. Pure declarations only; no business logic.

All coordinates are normalised ``[0, 1]`` unless a field name ends in ``_px``.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.floor_stitching_constants import (
    MAX_CONNECTOR_POINTS,
    MAX_CONNECTORS,
    MAX_CONTROL_POINTS,
    MAX_CUTOUT_POINTS,
    MAX_CUTOUTS,
)
from app.models.floors import CropBboxModel

# Shared type aliases

# Solve status — defined ONCE and reused by SolveSectionResult.status and
# AssemblySection.status (no free-string statuses anywhere).
SectionStatus = Literal["ok", "needs_points", "degenerate"]

# Stable control-point id pattern, e.g. "cp-1". Used by ControlPoint.id and
# MasterControlPoint.point_id.
_CP_ID_PATTERN = r"^cp-\d+$"

# Build-preview handle pattern, e.g. "floor-3-preview-7f3a".
_PREVIEW_ID_PATTERN = r"^floor-\d+-preview-[0-9a-f]{8}$"


# Point / element models


class ControlPoint(BaseModel):
    """Section-local control point (stored on ``reconstruction.control_points``).

    ``x``/``y`` are normalised ``[0, 1]`` over the cropped section plan image.
    """

    id: str = Field(..., pattern=_CP_ID_PATTERN)
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class MasterControlPoint(BaseModel):
    """Master-schema control point (stored on ``section.control_points``).

    ``point_id`` MUST equal a ``ControlPoint.id`` of the bound reconstruction.
    ``x``/``y`` are normalised ``[0, 1]`` over the cropped master schema.
    """

    point_id: str = Field(..., pattern=_CP_ID_PATTERN)
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class SectionTransform(BaseModel):
    """Solved uniform-similarity transform (read-only to clients).

    The transform maps section pixels to master pixels as
    ``y = scale * R(rotation_rad) @ x + (tx, ty)``. ``rotation_rad`` is additive
    and defaults to ``0.0`` so legacy ``section.transform`` blobs (written before
    rotation existed, with no ``rotation_rad`` key) still deserialise — as an
    unrotated section — with no DB migration.

    Stored on ``section.transform``. ``solved_at`` is timezone-aware UTC, so Pydantic
    v2 serialises the ``+00:00``/``Z`` offset the contract
    shows; a naive datetime would emit no offset and break the contract test.
    """

    scale: float
    rotation_rad: float = 0.0
    tx: float
    ty: float
    residual_rms_px: float
    n_points: int
    solved_at: datetime


class Connector(BaseModel):
    """A connecting line — an OPEN polyline tracing one corridor wall.

    ``points`` is an ordered list of >= 2 master-norm ``[0, 1]`` vertices.
    ``connects`` is reserved for future inter-section routing (not used by the
    mesh build).
    """

    id: int
    points: list[tuple[float, float]] = Field(..., min_length=2)
    height_m: Optional[float] = None
    thickness_m: Optional[float] = None
    connects: Optional[list[int]] = None

    @field_validator("points")
    @classmethod
    def _coords_in_range(
        cls, v: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        for idx, (x, y) in enumerate(v):
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(
                    f"point[{idx}] coords must be in [0, 1], got [{x}, {y}]"
                )
        return v


class ConnectorInput(BaseModel):
    """A connector in a replace-all request — same as ``Connector`` without ``id``.

    Ids are assigned server-side; the response echoes them as ``Connector``.
    """

    points: list[tuple[float, float]] = Field(..., min_length=2)
    height_m: Optional[float] = None
    thickness_m: Optional[float] = None
    connects: Optional[list[int]] = None

    @field_validator("points")
    @classmethod
    def _coords_in_range(
        cls, v: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        if len(v) > MAX_CONNECTOR_POINTS:
            raise ValueError(
                f"Too many points in connector line "
                f"(max {MAX_CONNECTOR_POINTS}), got {len(v)}"
            )
        for idx, (x, y) in enumerate(v):
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(
                    f"point[{idx}] coords must be in [0, 1], got [{x}, {y}]"
                )
        return v


class Cutout(BaseModel):
    """A cutout zone — a CLOSED polygon (rectangle = 4 corners) that ERASES walls.

    ``points`` is an ordered list of >= 3 master-norm ``[0, 1]`` vertices (an
    area, not a line — that is the only shape difference from ``Connector``).
    ``id`` is a 0-based index assigned server-side by list order (the JSON column
    has no child PK); clients use it only to key list rows.
    """

    id: int
    points: list[tuple[float, float]] = Field(..., min_length=3)

    @field_validator("points")
    @classmethod
    def _coords_in_range(
        cls, v: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        for idx, (x, y) in enumerate(v):
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(
                    f"point[{idx}] coords must be in [0, 1], got [{x}, {y}]"
                )
        return v


class CutoutInput(BaseModel):
    """A cutout in a replace-all request — same as ``Cutout`` without ``id``."""

    points: list[tuple[float, float]] = Field(..., min_length=3)

    @field_validator("points")
    @classmethod
    def _coords_in_range(
        cls, v: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        if len(v) > MAX_CUTOUT_POINTS:
            raise ValueError(
                f"Too many points in cutout zone "
                f"(max {MAX_CUTOUT_POINTS}), got {len(v)}"
            )
        for idx, (x, y) in enumerate(v):
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(
                    f"point[{idx}] coords must be in [0, 1], got [{x}, {y}]"
                )
        return v


# Request models


class SaveControlPointsRequest(BaseModel):
    """PUT .../reconstructions/{id}/control-points — replace section-local points."""

    points: list[ControlPoint]

    @field_validator("points")
    @classmethod
    def _unique_and_capped(cls, v: list[ControlPoint]) -> list[ControlPoint]:
        if len(v) > MAX_CONTROL_POINTS:
            raise ValueError(
                f"Too many control points (max {MAX_CONTROL_POINTS}), got {len(v)}"
            )
        ids = [p.id for p in v]
        if len(ids) != len(set(ids)):
            seen: set[str] = set()
            for cp_id in ids:
                if cp_id in seen:
                    raise ValueError(f"Duplicate control-point id: {cp_id}")
                seen.add(cp_id)
        return v


class SaveMasterControlPointsRequest(BaseModel):
    """PUT /floors/{id}/sections/{sid}/control-points — replace master points."""

    points: list[MasterControlPoint]

    @field_validator("points")
    @classmethod
    def _unique_and_capped(
        cls, v: list[MasterControlPoint]
    ) -> list[MasterControlPoint]:
        if len(v) > MAX_CONTROL_POINTS:
            raise ValueError(
                f"Too many control points (max {MAX_CONTROL_POINTS}), got {len(v)}"
            )
        ids = [p.point_id for p in v]
        if len(ids) != len(set(ids)):
            seen: set[str] = set()
            for cp_id in ids:
                if cp_id in seen:
                    raise ValueError(f"Duplicate control-point id: {cp_id}")
                seen.add(cp_id)
        return v


class ReplaceConnectorsRequest(BaseModel):
    """PUT /floors/{id}/connectors — atomic replace of all connector lines."""

    connectors: list[ConnectorInput]

    @field_validator("connectors")
    @classmethod
    def _capped(cls, v: list[ConnectorInput]) -> list[ConnectorInput]:
        if len(v) > MAX_CONNECTORS:
            raise ValueError(
                f"Too many connectors (max {MAX_CONNECTORS}), got {len(v)}"
            )
        return v


class ReplaceCutoutsRequest(BaseModel):
    """PUT /floors/{id}/cutouts — atomic replace of all cutout zones."""

    cutouts: list[CutoutInput]

    @field_validator("cutouts")
    @classmethod
    def _capped(cls, v: list[CutoutInput]) -> list[CutoutInput]:
        if len(v) > MAX_CUTOUTS:
            raise ValueError(
                f"Too many cutouts (max {MAX_CUTOUTS}), got {len(v)}"
            )
        return v


class ConfirmMeshRequest(BaseModel):
    """POST /floors/{id}/confirm-mesh — promote a built preview to the floor model.

    ``glb_file_id`` is validated at the contract boundary (defense in depth; the
    storage layer re-checks).
    """

    glb_file_id: str = Field(..., pattern=_PREVIEW_ID_PATTERN)


# Response: section-local control points


class ControlPointsResponse(BaseModel):
    """GET/PUT .../reconstructions/{id}/control-points response."""

    reconstruction_id: int
    image_size_cropped: Optional[tuple[int, int]] = None
    points: list[ControlPoint]


# Response: master control points


class SectionControlPointsResponse(BaseModel):
    """PUT /floors/{id}/sections/{sid}/control-points response.

    ``matched_ids`` = master ids that exist on the section; ``unmatched_ids`` =
    section ids not yet placed on the master.
    """

    section_id: int
    points: list[MasterControlPoint]
    section_point_ids: list[str]
    matched_ids: list[str]
    unmatched_ids: list[str]


# Response: solve transforms


class SolveSectionResult(BaseModel):
    """Per-section solve outcome. Only ``status == "ok"`` carries a transform."""

    section_id: int
    status: SectionStatus
    transform: Optional[SectionTransform] = None
    implied_ppm: Optional[float] = None
    warning: Optional[str] = None


class SolveTransformsResponse(BaseModel):
    """POST /floors/{id}/solve-transforms response."""

    floor_id: int
    pixels_per_meter: Optional[float] = None
    anchor_section_id: Optional[int] = None
    sections: list[SolveSectionResult]


# Response: connectors


class ConnectorsResponse(BaseModel):
    """GET/PUT /floors/{id}/connectors response."""

    floor_id: int
    connectors: list[Connector]


class CutoutsResponse(BaseModel):
    """GET/PUT /floors/{id}/cutouts response."""

    floor_id: int
    cutouts: list[Cutout]


# Response: build preview / confirm


class ExcludedSection(BaseModel):
    """A section left out of the build, with the reason (e.g. ``needs_points``)."""

    section_id: int
    reason: str


class BuildWarning(BaseModel):
    """A non-fatal build warning naming the affected section (e.g. ``low_detail``)."""

    section_id: int
    code: str
    message: str


class BuildFloorPreviewResponse(BaseModel):
    """POST /floors/{id}/build-mesh response.

    Assembles a PREVIEW GLB (not persisted). ``glb_file_id`` is an opaque handle
    passed to confirm-mesh; ``floors.mesh_file_glb`` is unchanged until confirm.
    """

    floor_id: int
    glb_file_id: str
    glb_url: str
    persisted: bool
    pixels_per_meter: Optional[float] = None
    canvas_size_px: tuple[int, int]
    included_sections: list[int]
    excluded_sections: list[ExcludedSection]
    warnings: list[BuildWarning]
    connector_count: int
    cutout_count: int


class ConfirmMeshResponse(BaseModel):
    """POST /floors/{id}/confirm-mesh response. Sets ``floors.mesh_file_glb``."""

    floor_id: int
    mesh_file_glb: str
    glb_url: str
    persisted: bool


# Response: assembly read (drives the Floor Editor)


class MasterSchemaInfo(BaseModel):
    """Master-schema block of the assembly read.

    Response key is ``crop_bbox``; it is
    populated from the ORM attribute ``Floor.schema_crop_bbox`` — the name mapping
    is done in the service, the source attr and the response key differ
    on purpose. ``crop_bbox`` reuses ``CropBboxModel`` (normalised
    ``{x, y, width, height, rotation}``) so the assembly read echoes the SAME shape
    the floor-detail endpoint already returns (``FloorWithBuildingResponse``).
    """

    image_id: str
    url: str
    crop_bbox: Optional[CropBboxModel] = None
    size_px: Optional[tuple[int, int]] = None
    # Vectorised "карта отсеков": floor wall contours normalised [0,1] over the
    # CROPPED+rotated master frame (same frame as master_control_points). The Floor
    # Editor draws these as the master backdrop (vector); None until wall extraction.
    wall_polygons: Optional[list[list[tuple[float, float]]]] = None


class AssemblySection(BaseModel):
    """One section's full assembly state (bind / solve / points / transform).

    ``status`` reuses the shared ``SectionStatus`` literal.
    """

    section_id: int
    number: int
    reconstruction_id: Optional[int] = None
    mask_file_id: Optional[str] = None
    # Viewable URL of the section's cropped wall mask (the "эталон" backdrop the
    # editor places section-local control points on). None when unbound / no mask.
    mask_url: Optional[str] = None
    # Section outline polygon, normalised [0,1] over the master (floor-schema) frame
    # — drawn on the карта отсеков so the operator sees where each отсек sits.
    geometry: Optional[list[tuple[float, float]]] = None
    image_size_cropped: Optional[tuple[int, int]] = None
    section_control_points: list[ControlPoint]
    master_control_points: list[MasterControlPoint]
    transform: Optional[SectionTransform] = None
    status: SectionStatus


class FloorAssemblyResponse(BaseModel):
    """GET /floors/{id}/assembly — single read for the whole Floor Editor.

    ``mesh_file_glb`` is the last CONFIRMED floor mesh (``null`` until a
    confirm-mesh runs — an unconfirmed preview is never reflected here).
    """

    floor_id: int
    pixels_per_meter: Optional[float] = None
    mesh_file_glb: Optional[str] = None
    master_schema: MasterSchemaInfo
    sections: list[AssemblySection]
    connectors: list[Connector]
    cutouts: list[Cutout] = []
