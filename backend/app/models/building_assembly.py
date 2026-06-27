"""Pydantic models for Vertical Floor Stitching (subfeature A).

Exact JSON shapes are the contract in
 These models ARE
that contract — request validation and response serialisation both flow through
here. Pure declarations only; no business logic.

All coordinates are normalised ``[0, 1]`` over each floor's wall mask. The
``building_transform`` shape (``StitchTransform``) and the per-floor
``mask_width``/``mask_height`` are a SHARED contract consumed by subfeatures B
(mesh placement) and D (routing) — do NOT change them silently (plan/README).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.floor_stitching_constants import MAX_CONTROL_POINTS

# Shared type aliases

# Stable control-point id pattern, e.g. "cp-1".
_CP_ID_PATTERN = r"^cp-\d+$"

# Solve status (POST solve-stitch). ``reference`` = lowest floor (identity);
# ``ok`` = solved; ``needs_points`` = < 3 paired points; ``degenerate`` =
# collinear / tiny baseline; ``no_mask`` = a floor's wall mask is missing.
SolveStatus = Literal["reference", "ok", "needs_points", "degenerate", "no_mask"]

# Pair status (GET assembly). ``unsolved`` = points present but solve not yet run
# (or chain broken below). Otherwise mirrors ``SolveStatus`` minus ``degenerate``
# (a degenerate solve leaves no transform → reads back as ``unsolved``).
PairStatus = Literal["reference", "ok", "needs_points", "unsolved", "no_mask"]


# Point model


class ControlPoint(BaseModel):
    """An anchor point on a floor's wall mask, normalised ``[0, 1]``.

    ``id`` (e.g. ``cp-1``) pairs a point on THIS floor with the matching point on
    the floor below (same id on both sides = one correspondence).
    """

    id: str = Field(..., pattern=_CP_ID_PATTERN)
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


# Request models


class SaveStitchPointsRequest(BaseModel):
    """PUT /floors/{floor_id}/stitch-points — anchor points for the pair.

    ``points`` are on THIS floor's mask (the upper/moving floor); ``ref_points``
    are on the floor BELOW's mask (the reference). Every ``points[].id`` MUST have
    a matching ``ref_points[].id`` and vice-versa (mirror the section pairing
    rule). Each side is capped at ``MAX_CONTROL_POINTS``.
    """

    points: list[ControlPoint]
    ref_points: list[ControlPoint]

    @field_validator("points", "ref_points")
    @classmethod
    def _capped_and_unique(cls, v: list[ControlPoint]) -> list[ControlPoint]:
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

    @model_validator(mode="after")
    def _ids_paired(self) -> "SaveStitchPointsRequest":
        point_ids = {p.id for p in self.points}
        ref_ids = {p.id for p in self.ref_points}
        if point_ids != ref_ids:
            missing_ref = point_ids - ref_ids
            missing_pts = ref_ids - point_ids
            details: list[str] = []
            if missing_ref:
                details.append(f"points without a ref_point: {sorted(missing_ref)}")
            if missing_pts:
                details.append(f"ref_points without a point: {sorted(missing_pts)}")
            raise ValueError("Unpaired control-point ids — " + "; ".join(details))
        return self


# Shared transform shape (B/D contract)


class StitchTransform(BaseModel):
    """Solved similarity mapping this floor's mask-px → reference-floor mask-px.

    SHARED B/D CONTRACT — exact field set (plan/README). Reference floor =
    identity (``scale=1, rotation_rad=0, tx=0, ty=0, residual_rms_px=0,
    n_points=0``). ``rotation_rad`` defaults to ``0.0`` so a legacy
    ``building_transform`` blob written without the key still deserialises as an
    unrotated transform.
    """

    scale: float
    rotation_rad: float = 0.0
    tx: float
    ty: float
    residual_rms_px: float
    n_points: int


# Response: PUT stitch-points


class SaveStitchPointsResponse(BaseModel):
    """PUT /floors/{floor_id}/stitch-points response."""

    floor_id: int
    points_count: int
    ref_points_count: int


# Response: POST solve-stitch


class FloorStitchStatus(BaseModel):
    """One floor's solve outcome. Only solved floors carry a ``building_transform``.

    ``residual_rms_m`` = ``residual_rms_px / pixels_per_meter`` (operator-facing
    quality, ``None`` when no metric scale). ``elevation_m`` =
    ``(number − min_number) × FLOOR_HEIGHT``.
    """

    floor_id: int
    number: int
    status: SolveStatus
    building_transform: Optional[StitchTransform] = None
    residual_rms_m: Optional[float] = None
    elevation_m: float


class SolveStitchResponse(BaseModel):
    """POST /buildings/{building_id}/solve-stitch response."""

    building_id: int
    reference_floor_id: Optional[int] = None
    floors: list[FloorStitchStatus]


# Response: GET assembly


class AssemblyFloor(BaseModel):
    """One floor's assembly state powering the building-assembly page.

    ``mask_url`` is the persisted wall mask (``Floor.mask_file``; ``None`` until
    the floor is edited). ``mask_width``/``mask_height`` are the wall-mask pixel
    dims used to de-normalise points — REQUIRED for subfeature D's canvas factor
    ``k`` recovery (do NOT omit).
    """

    id: int
    number: int
    mask_url: Optional[str] = None
    mask_width: Optional[int] = None
    mask_height: Optional[int] = None
    pixels_per_meter: Optional[float] = None
    elevation_m: float
    points_count: int
    ref_points_count: int
    # Saved anchor coordinates so the editor can REDRAW them on reload (no
    # re-placing each session). ``points`` = this floor's own anchors (when it is
    # the upper of a pair); ``ref_points`` = the matching anchors on the floor below.
    points: list[ControlPoint] = []
    ref_points: list[ControlPoint] = []
    building_transform: Optional[StitchTransform] = None
    pair_status: PairStatus


class BuildingAssemblyResponse(BaseModel):
    """GET /buildings/{building_id}/assembly — drives the assembly page."""

    building_id: int
    reference_floor_id: Optional[int] = None
    floors: list[AssemblyFloor]
