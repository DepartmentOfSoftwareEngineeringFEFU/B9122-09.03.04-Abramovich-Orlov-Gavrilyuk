"""FloorAssemblyService — the registration brain for floor stitching.

Implements (bind master control points), (solve every section's uniform
similarity + derive ``ppm_floor``) and (connector CRUD). The mesh build /
confirm / assembly-read (+ GET) live in on this same class.

Layer rules (``prompts/architecture.md``):
- This is a SERVICE: it owns ALL IO (DB via repositories, masks/images via
  ``FileStorage``) and calls the PURE ``processing.registration`` solver with
  plain numpy arrays. The solver knows nothing about IDs, normalisation or files.
- ``vectorization_data`` is **read-only** here — used only to read
  ``estimated_pixels_per_meter`` and ``image_size_cropped``.
  No code path writes it.
- Loaded masks are never mutated.

Coordinate maths — de-normalisation, master/section pixel dims, ppm derivation —
is handled inside this service.
"""

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np

from app.core.exceptions import (
    FileStorageError,
    FloorAssemblyConflictError,
    FloorNotFoundError,
    FloorSchemaError,
    ImageProcessingError,
    PreviewNotFoundError,
    SectionNotBoundError,
    SectionNotFoundError,
    SectionValidationError,
)
from app.core.floor_stitching_constants import (
    CANVAS_TRUST_RESIDUAL_M,
    DEFAULT_CONNECTOR_THICKNESS_M,
    DETAIL_WARN_SCALE,
    FLOOR_HEIGHT,
    MAX_FLOOR_CANVAS_PX,
    MIN_CONNECTOR_THICKNESS_PX,
    MIN_CONTROL_POINTS,
    PPM_WARN_RATIO,
    R_MIN_BASELINE_FRAC,
    RESIDUAL_WARN_M,
)
from app.db.repositories.floor_connector_repo import FloorConnectorRepository
from app.db.repositories.floor_repo import FloorRepository
from app.db.repositories.reconstruction_repo import ReconstructionRepository
from app.db.repositories.section_repo import SectionRepository
from app.models.floor_assembly import (
    AssemblySection,
    BuildFloorPreviewResponse,
    BuildWarning,
    ConfirmMeshResponse,
    Connector,
    ConnectorInput,
    ConnectorsResponse,
    ControlPoint,
    Cutout,
    CutoutInput,
    CutoutsResponse,
    ExcludedSection,
    FloorAssemblyResponse,
    MasterControlPoint,
    MasterSchemaInfo,
    SectionControlPointsResponse,
    SectionTransform,
    SolveSectionResult,
    SolveTransformsResponse,
)
from app.models.floors import CropBboxModel
from app.processing.floor_assembly import (
    ConnectorRaster,
    CutoutRaster,
    SectionWarpInput,
    assemble_floor_mask,
    compute_canvas_factor,
)
from app.processing.mesh_builder import build_mesh_from_mask
from app.processing.registration import (
    DegenerateControlPointsError,
    solve_similarity,
)
from app.services.file_storage import FileStorage

logger = logging.getLogger(__name__)

# Aspect-ratio tolerance between the loaded mask's true dims and the stored
# ``image_size_cropped`` (assert they match, surface a data error if grossly
# off). 5% absorbs integer rounding in the crop pipeline without masking a genuine
# stale-size mismatch.
_ASPECT_TOL = 0.05


# Pure helpers (module-level so can unit-test them)


@dataclass(frozen=True)
class _OkSolve:
    """One successfully-solved section, for anchor selection + ppm derivation.

    Plain value object (no DB/Pydantic) so ``_derive_ppm_floor`` stays pure and
    trivially unit-testable.

    Attributes:
        section_id: id of the solved section.
        section_number: ``section.number`` (tie-break key — smaller wins).
        n_matched: number of matched control-point pairs used in the fit.
        scale: solved isotropic scale ``s`` (master_px / section_px).
        ppm_section: ``estimated_pixels_per_meter`` from the section's
            ``vectorization_data`` (section-pixel scale), or ``None`` if absent.
    """

    section_id: int
    section_number: int
    n_matched: int
    scale: float
    ppm_section: Optional[float]


def _is_positive_finite(value: Optional[float]) -> bool:
    """True iff ``value`` is a real number that is finite and strictly positive."""
    return (
        value is not None
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
    )


def _derive_ppm_floor(
    ok_results: list[_OkSolve],
) -> tuple[Optional[int], Optional[float]]:
    """Select the anchor section and derive ``ppm_floor``.

    Pure function: no IO, no DB. The anchor is the ok-section with the MOST
    matched control points (tie-break: smallest ``section_number``), considering
    ONLY sections whose ``ppm_section`` is present, finite and ``> 0`` (the ppm
    guard — ``vectorization_data`` is nullable so the field may be missing / 0 /
    NaN). ``ppm_floor = ppm_section_anchor * scale_anchor``.

    Args:
        ok_results: every successfully-solved section (status ``ok``).

    Returns:
        ``(anchor_section_id, ppm_floor)``. Both are ``None`` when NO ok-section
        has a valid metric scale — the caller must NOT raise (build-mesh surfaces a
        clean 422); never let ``0``/``None`` ppm propagate to the
        builder (which does ``1 / ppm``).
    """
    candidates = [r for r in ok_results if _is_positive_finite(r.ppm_section)]
    if not candidates:
        return None, None

    # Most matched points wins; ties broken by the smaller section number. Sorting
    # by (-n_matched, section_number) puts the anchor first.
    anchor = min(candidates, key=lambda r: (-r.n_matched, r.section_number))
    ppm_floor = anchor.ppm_section * anchor.scale  # type: ignore[operator]
    if not _is_positive_finite(ppm_floor):
        return None, None
    return anchor.section_id, ppm_floor


# Russian labels for the pure solver's degenerate reasons (the English strings in
# processing.registration are left untouched — translation is an operator-UI
# concern, so it lives here at the service boundary). Unknown reasons fall through
# verbatim so nothing is ever swallowed.
_DEGENERATE_REASON_RU: dict[str, str] = {
    "too few points": "слишком мало точек",
    "baseline too short": "точки расположены слишком близко друг к другу",
    "non-finite": "неустойчивое решение (расчёт не сошёлся)",
}


def _ru_degenerate_reason(reason: str) -> str:
    """Translate a solver ``DegenerateControlPointsError.reason`` to Russian."""
    return "Точки вырождены: " + _DEGENERATE_REASON_RU.get(reason, reason)


# Internal in-memory solve record (atomicity — compute, THEN persist)


@dataclass
class _SectionSolve:
    """Per-section solve outcome held in memory before the single persist pass.

    Mutable on purpose: warnings are appended during the post-ppm cross-check pass
    (after the anchor and ``ppm_floor`` are known). ``transform`` is the dict to
    persist (``None`` clears a stale transform).
    """

    section_id: int
    status: str  # "ok" | "needs_points" | "degenerate"
    transform: Optional[dict]
    implied_ppm: Optional[float]
    warnings: list[str]
    # Bookkeeping for the post-ppm cross-check (only meaningful when status == ok)
    scale: Optional[float] = None
    residual_rms_px: Optional[float] = None
    ppm_section: Optional[float] = None


class FloorAssemblyService:
    """Registration + connector orchestration for a floor (//)."""

    def __init__(
        self,
        floor_repo: FloorRepository,
        section_repo: SectionRepository,
        reconstruction_repo: ReconstructionRepository,
        connector_repo: FloorConnectorRepository,
        storage: FileStorage,
    ) -> None:
        self._floor_repo = floor_repo
        self._section_repo = section_repo
        self._reconstruction_repo = reconstruction_repo
        self._connector_repo = connector_repo
        self._storage = storage

    # master control points

    async def save_section_control_points(
        self,
        floor_id: int,
        section_id: int,
        points: list[MasterControlPoint],
    ) -> SectionControlPointsResponse:
        """Replace a section's master-schema control points.

        Coord range / cap / id-uniqueness are enforced by
        ``SaveMasterControlPointsRequest``. This method enforces the
        cross-entity rule: every ``point_id`` MUST be an id of the bound
        reconstruction's section-local control points (orphan-proofing).

        Args:
            floor_id: owning floor (for routing context; section is the entity).
            section_id: section to update.
            points: validated master control points (may be empty).

        Returns:
            SectionControlPointsResponse with matched / unmatched id lists.

        Raises:
            SectionNotFoundError: if the section is not found (-> 404).
            SectionNotBoundError: if the section has no bound reconstruction (409).
            SectionValidationError: if a ``point_id`` is not one of the section's
                control points (-> 422).
        """
        logger.info(
            "save_section_control_points: floor_id=%d, section_id=%d, count=%d",
            floor_id,
            section_id,
            len(points),
        )
        section = await self._section_repo.get_by_id(section_id)
        if section is None:
            raise SectionNotFoundError(section_id)
        if section.reconstruction is None:
            raise SectionNotBoundError(section_id)

        # Section-local ids come from the bound reconstruction's control points.
        section_point_ids = [
            str(cp.get("id"))
            for cp in (section.reconstruction.control_points or [])
            if isinstance(cp, dict) and cp.get("id") is not None
        ]
        section_id_set = set(section_point_ids)

        for p in points:
            if p.point_id not in section_id_set:
                raise SectionValidationError(
                    f"point_id {p.point_id} is not a control point of the section"
                )

        await self._section_repo.update_master_control_points(
            section_id, [p.model_dump() for p in points]
        )

        master_ids = [p.point_id for p in points]
        master_id_set = set(master_ids)
        matched_ids = [pid for pid in section_point_ids if pid in master_id_set]
        unmatched_ids = [pid for pid in section_point_ids if pid not in master_id_set]

        return SectionControlPointsResponse(
            section_id=section_id,
            points=points,
            section_point_ids=section_point_ids,
            matched_ids=matched_ids,
            unmatched_ids=unmatched_ids,
        )

    # solve transforms

    async def solve_transforms(self, floor_id: int) -> SolveTransformsResponse:
        """Solve every bound section's uniform similarity + derive ``ppm_floor``.

        Atomicity: ALL computation happens first — load every mask,
        run every ``solve_similarity``, choose the anchor, compute ``ppm_floor`` —
        into an in-memory list. Expected per-section failures (< 3 matched,
        degenerate) are recorded as STATUSES, not exceptions. Only AFTER the full
        pass succeeds is anything persisted (transforms + ppm + cleared stale
        transforms). An UNEXPECTED error (e.g. ``load_mask`` IO failure) aborts
        BEFORE any write, so the floor is never left half-solved.

        Args:
            floor_id: floor whose sections to solve.

        Returns:
            SolveTransformsResponse with per-section status, ppm and warnings.

        Raises:
            FloorNotFoundError: floor absent (404).
            FloorAssemblyConflictError: no sections bound to reconstructions (409).
            ImageProcessingError / FileStorageError: unexpected mask IO failure
                (aborts before any persist).
            FloorSchemaError: master schema dims unreadable.
        """
        logger.info("solve_transforms: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        sections = await self._section_repo.list_by_floor(floor_id)
        bound = [s for s in sections if s.reconstruction is not None]
        if not bound:
            raise FloorAssemblyConflictError("No sections bound to plans")

        # Master-pixel canvas dims — read once, used to de-normalise every
        # master control point. Unexpected failure aborts before any DB write.
        master_w, master_h = await self._master_pixel_dims(floor)

        # PASS 1: pure computation into in-memory records (no persistence)
        solves: list[_SectionSolve] = []
        ok_for_anchor: list[_OkSolve] = []

        for section in bound:
            solve = self._solve_one_section(
                section, master_w=master_w, master_h=master_h
            )
            solves.append(solve)
            if solve.status == "ok":
                ok_for_anchor.append(
                    _OkSolve(
                        section_id=section.id,
                        section_number=section.number,
                        n_matched=solve.transform["n_points"],  # type: ignore[index]
                        scale=solve.scale,  # type: ignore[arg-type]
                        ppm_section=solve.ppm_section,
                    )
                )

        anchor_section_id, ppm_floor = _derive_ppm_floor(ok_for_anchor)

        # PASS 2 (still in memory): ppm cross-check + residual warnings
        if _is_positive_finite(ppm_floor):
            for solve in solves:
                if solve.status != "ok":
                    continue
                self._apply_post_ppm_warnings(solve, ppm_floor)  # type: ignore[arg-type]

        # PERSIST: only after the full pass succeeded
        for solve in solves:
            # Sections that failed to solve get any stale transform cleared so it
            # never lingers (transform == None).
            await self._section_repo.update_transform(
                solve.section_id, solve.transform
            )
        if _is_positive_finite(ppm_floor):
            await self._floor_repo.update_pixels_per_meter(
                floor_id, ppm_floor  # type: ignore[arg-type]
            )

        return SolveTransformsResponse(
            floor_id=floor_id,
            pixels_per_meter=ppm_floor,
            anchor_section_id=anchor_section_id,
            sections=[
                SolveSectionResult(
                    section_id=s.section_id,
                    status=s.status,  # type: ignore[arg-type]
                    transform=(
                        SectionTransform(**s.transform) if s.transform else None
                    ),
                    implied_ppm=s.implied_ppm,
                    warning=("; ".join(s.warnings) if s.warnings else None),
                )
                for s in solves
            ],
        )

    def _solve_one_section(
        self, section, master_w: int, master_h: int  # type: ignore[no-untyped-def]
    ) -> _SectionSolve:
        """Match ids, de-normalise, solve one section (PURE of persistence).

        Returns a ``_SectionSolve`` record; never writes to the DB. Raises only on
        UNEXPECTED errors (mask IO, data inconsistency) — expected solve failures
        are encoded as ``needs_points`` / ``degenerate`` statuses.
        """
        reconstruction = section.reconstruction

        # Section-local points keyed by id (normalised [0,1] over cropped section).
        section_local: dict[str, tuple[float, float]] = {}
        for cp in reconstruction.control_points or []:
            if isinstance(cp, dict) and cp.get("id") is not None:
                section_local[str(cp["id"])] = (float(cp["x"]), float(cp["y"]))

        # Master points keyed by point_id (normalised [0,1] over cropped master).
        master_local: dict[str, tuple[float, float]] = {}
        for mp in section.control_points or []:
            if isinstance(mp, dict) and mp.get("point_id") is not None:
                master_local[str(mp["point_id"])] = (float(mp["x"]), float(mp["y"]))

        # Match by ID: only ids present on BOTH sides form a correspondence pair.
        matched_ids = [pid for pid in master_local if pid in section_local]
        ppm_section = self._read_section_ppm(reconstruction)

        if len(matched_ids) < MIN_CONTROL_POINTS:
            return _SectionSolve(
                section_id=section.id,
                status="needs_points",
                transform=None,
                implied_ppm=None,
                warnings=[
                    f"Сопоставлено только {len(matched_ids)} "
                    f"точек (нужно ≥ {MIN_CONTROL_POINTS})"
                ],
                ppm_section=ppm_section,
            )

        # Load the section wall mask to get its TRUE pixel dims (Hs, Ws). An IO
        # failure here is UNEXPECTED → propagates and aborts before any persist.
        mask = self._storage_load_mask_sync_guard(section, reconstruction)
        h_s, w_s = mask.shape[:2]

        #assert mask aspect ≈ image_size_cropped, else surface a data error.
        self._assert_mask_matches_cropped(reconstruction, w_s=w_s, h_s=h_s)

        # De-normalise: section-local ×(Ws,Hs) → section-pixel (src);
        #               master      ×(Wm,Hm) → master-pixel  (dst).
        src = np.array(
            [
                [section_local[pid][0] * w_s, section_local[pid][1] * h_s]
                for pid in matched_ids
            ],
            dtype=np.float64,
        )
        dst = np.array(
            [
                [master_local[pid][0] * master_w, master_local[pid][1] * master_h]
                for pid in matched_ids
            ],
            dtype=np.float64,
        )

        min_baseline_px = R_MIN_BASELINE_FRAC * math.hypot(w_s, h_s)

        try:
            result = solve_similarity(src, dst, min_baseline_px)
        except DegenerateControlPointsError as exc:
            logger.info(
                "section %d degenerate: %s", section.id, exc.reason
            )
            return _SectionSolve(
                section_id=section.id,
                status="degenerate",
                transform=None,
                implied_ppm=None,
                warnings=[_ru_degenerate_reason(exc.reason)],
                ppm_section=ppm_section,
            )

        # Success — build the transform dict to persist. solved_at is a timezone-
        # AWARE UTC ISO-8601 STRING (not a datetime object): section.transform is a
        # JSON column, and json.dumps cannot serialise a datetime — storing the ISO
        # string keeps the offset and Pydantic v2 coerces it back to a tz-aware
        # datetime when SectionTransform(**transform) is built (contract).
        transform = {
            "scale": result.scale,
            "rotation_rad": result.rotation_rad,
            "tx": result.tx,
            "ty": result.ty,
            "residual_rms_px": result.residual_rms,
            "n_points": result.n_points,
            "solved_at": datetime.now(timezone.utc).isoformat(),
        }
        implied_ppm = (
            ppm_section * result.scale
            if _is_positive_finite(ppm_section)
            else None
        )
        return _SectionSolve(
            section_id=section.id,
            status="ok",
            transform=transform,
            implied_ppm=implied_ppm,
            warnings=[],
            scale=result.scale,
            residual_rms_px=result.residual_rms,
            ppm_section=ppm_section,
        )

    @staticmethod
    def _apply_post_ppm_warnings(solve: _SectionSolve, ppm_floor: float) -> None:
        """Append non-fatal ppm-spread + residual warnings (status stays ``ok``).

        Only called when ``ppm_floor`` is positive finite. A section
        can carry BOTH warnings; ``SolveSectionResult.warning`` is a single string,
        so the caller joins ``solve.warnings`` with ``"; "``.
        """
        # ppm-spread cross-check: implied_ppm = ppm_section * scale.
        if _is_positive_finite(solve.implied_ppm):
            ratio = solve.implied_ppm / ppm_floor  # type: ignore[operator]
            spread = abs(ratio - 1.0)
            if spread > PPM_WARN_RATIO:
                solve.warnings.append(
                    f"Масштаб отличается от опорного отсека на "
                    f"{round(spread * 100)}% — проверьте точки"
                )

        # Residual warning: convert master-pixel residual to metres via ppm_floor.
        if solve.residual_rms_px is not None:
            residual_rms_m = solve.residual_rms_px / ppm_floor
            if residual_rms_m > RESIDUAL_WARN_M:
                solve.warnings.append(
                    f"Точки подогнаны неточно (СКО {residual_rms_m:.2f} м) "
                    f"— возможно, расставлены неверно"
                )

    # connectors

    async def get_connectors(self, floor_id: int) -> ConnectorsResponse:
        """List a floor's connector lines.

        Raises FloorNotFoundError (404) if the floor is absent.
        """
        logger.debug("get_connectors: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        rows = await self._connector_repo.list_by_floor(floor_id)
        return ConnectorsResponse(
            floor_id=floor_id,
            connectors=[self._connector_to_model(r) for r in rows],
        )

    async def replace_connectors(
        self, floor_id: int, items: list[ConnectorInput]
    ) -> ConnectorsResponse:
        """Atomically replace ALL connector lines for a floor.

        Per-line ``>= 2`` points, coord range, ``MAX_CONNECTOR_POINTS`` and
        ``MAX_CONNECTORS`` caps are enforced by ``ReplaceConnectorsRequest`` /
        ``ConnectorInput``. An empty ``items`` list clears the floor
        (valid, 200). The repo delete+insert is a single transaction.

        Raises FloorNotFoundError (404) if the floor is absent.
        """
        logger.info(
            "replace_connectors: floor_id=%d, count=%d", floor_id, len(items)
        )
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        rows = await self._connector_repo.replace_all_for_floor(
            floor_id,
            [
                {
                    "points": [list(pt) for pt in item.points],
                    "height_m": item.height_m,
                    "thickness_m": item.thickness_m,
                    "connects": item.connects,
                }
                for item in items
            ],
        )
        return ConnectorsResponse(
            floor_id=floor_id,
            connectors=[self._connector_to_model(r) for r in rows],
        )

    # cutouts (zones that ERASE walls; stored on floors.nav_cutouts)

    async def get_cutouts(self, floor_id: int) -> CutoutsResponse:
        """List a floor's cutout zones (stored as the ``nav_cutouts`` JSON column).

        Raises FloorNotFoundError (404) if the floor is absent.
        """
        logger.debug("get_cutouts: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        return CutoutsResponse(
            floor_id=floor_id,
            cutouts=[
                self._cutout_to_model(c, i)
                for i, c in enumerate(floor.nav_cutouts or [])
            ],
        )

    async def replace_cutouts(
        self, floor_id: int, items: list[CutoutInput]
    ) -> CutoutsResponse:
        """Atomically replace ALL cutout zones for a floor.

        Per-zone ``>= 3`` points, coord range, ``MAX_CUTOUT_POINTS`` and
        ``MAX_CUTOUTS`` caps are enforced by ``ReplaceCutoutsRequest`` /
        ``CutoutInput``. An empty ``items`` list clears the floor (valid, 200).
        The whole list is written to the single ``nav_cutouts`` column.

        Raises FloorNotFoundError (404) if the floor is absent.
        """
        logger.info("replace_cutouts: floor_id=%d, count=%d", floor_id, len(items))
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        payload = [{"points": [list(pt) for pt in item.points]} for item in items]
        floor = await self._floor_repo.update_nav_cutouts(floor_id, payload)
        return CutoutsResponse(
            floor_id=floor_id,
            cutouts=[
                self._cutout_to_model(c, i)
                for i, c in enumerate(floor.nav_cutouts or [])
            ],
        )

    # build (preview) / confirm / assembly read

    async def build_floor_mesh(
        self, floor_id: int
    ) -> BuildFloorPreviewResponse:
        """Assemble the stitched floor mask → preview GLB (build).

        Warps every ok-section's wall mask by its persisted uniform similarity
        into the master-pixel canvas, rasterises connectors as wall bands, extrudes
        the combined mask with the UNCHANGED ``build_mesh_from_mask`` and writes a
        PREVIEW GLB. ``floors.mesh_file_glb`` is NEVER touched here — only
        ``confirm_floor_mesh`` promotes the preview (preview-only build).

        Memory guard ``k``computed ONCE and threaded *identically* into
        all five consumers — canvas dims, each section transform (``scale,tx,ty``),
        connector point de-norm, connector thickness (incl. the default) and the
        builder ``pixels_per_meter`` — so the floor's shapes are preserved (any
        single omission silently rescales the floor).

        Args:
            floor_id: floor to build.

        Returns:
            BuildFloorPreviewResponse (``persisted=False``) with the preview handle,
            included/excluded sections, low-detail warnings, connector count and
            canvas size.

        Raises:
            FloorNotFoundError: floor absent (404).
            FloorAssemblyConflictError: no ok-section has a transform (409).
            FloorSchemaError: master schema missing, no usable section masks, no
                metric scale, or an empty combined mask (422).
            ImageProcessingError / FileStorageError: unexpected IO failure.
        """
        logger.info("build_floor_mesh: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        sections = await self._section_repo.list_by_floor(floor_id)
        # An ok-section is one carrying a persisted transform (wrote it).
        ok_sections = [s for s in sections if s.transform]
        if not ok_sections:
            raise FloorAssemblyConflictError("Run solve-transforms first")

        # ppm guard: never let 0/None/non-finite reach the
        # builder, which divides by ppm. No metric scale ⇒ solve never produced one.
        ppm_floor = floor.pixels_per_meter
        if not _is_positive_finite(ppm_floor):
            raise FloorSchemaError(
                "Floor has no metric scale — re-run solve/vectorization"
            )

        # Master-pixel canvas dims (Wm, Hm) = the cropped master-schema raster.
        master_w, master_h = await self._master_pixel_dims(floor)

        # k: the SINGLE scale scalar — now UP- *and* downscales.
        # The "карта отсеков" master schema is a low-res mini-map, so the solved
        # section scales are tiny (e.g. 0.12×): warping a high-res section mask
        # into the raw master-px canvas collapses every wall to sub-pixel and the
        # floor extrudes as blank scraps with no outer walls. Fix: choose k so the
        # MOST-detailed section (the smallest scale) rasterises at ~native
        # resolution — k = 1 / min(scale) — instead of the old downscale-only
        # guard. ppm is multiplied by the SAME k (consumer e), so the floor's
        # metric size is unchanged; only the raster gets crisp enough to keep
        # walls. Still capped at MAX_FLOOR_CANVAS_PX (a huge master scales DOWN).
        # The shared helper derives k = 1/min(scale), clamped to the canvas cap.
        # A MIS-REGISTERED section (high residual) has a spuriously shrunk scale
        # that would inflate k and over-upscale the WHOLE floor, so it is excluded
        # from the min-scale estimate. The nav service calls the SAME helper with
        # the same arguments so both builds size the canvas IDENTICALLY.
        long_side = max(master_w, master_h)
        k = compute_canvas_factor(
            [
                (
                    float(s.transform["scale"]),
                    float(s.transform.get("residual_rms_px", 0.0)),
                )
                for s in ok_sections
                if s.transform
                and _is_positive_finite(float(s.transform["scale"]))
            ],
            long_side_px=long_side,
            ppm=ppm_floor,
            max_canvas_px=MAX_FLOOR_CANVAS_PX,
            trust_residual_m=CANVAS_TRUST_RESIDUAL_M,
        )
        # (a) canvas dims × k.
        canvas_w = round(master_w * k)
        canvas_h = round(master_h * k)
        canvas_size = (canvas_w, canvas_h)

        # Build warp inputs for each ok-section; a missing mask file excludes the
        # section (non-fatal) rather than aborting the whole build.
        warp_inputs: list[SectionWarpInput] = []
        included_ids: list[int] = []
        excluded: list[ExcludedSection] = []
        warnings: list[BuildWarning] = []

        for section in ok_sections:
            transform = section.transform  # persisted dict
            mask = self._load_section_mask_for_build(section)
            if mask is None:
                excluded.append(
                    ExcludedSection(section_id=section.id, reason="mask_missing")
                )
                continue

            # Normalise to strict {0,255} on a COPY (load_mask may return {0,1} or
            # grayscale; the builder thresholds at >127, so an un-normalised {0,1}
            # mask silently drops every wall). Never mutate the loaded array.
            mask_bin = np.where(mask.copy() > 127, 255, 0).astype(np.uint8)

            base_scale = float(transform["scale"])
            # Legacy transforms (solved before rotation existed) carry no
            # "rotation_rad" key → default 0.0 (unrotated). The angle is NOT
            # k-scaled (rotation is invariant to the uniform memory-guard scale).
            base_rot = float(transform.get("rotation_rad", 0.0))
            # (b) section transform pre-multiplied by k (angle passed unscaled).
            warp_inputs.append(
                SectionWarpInput(
                    section_id=section.id,
                    mask=mask_bin,
                    scale=base_scale * k,
                    rotation_rad=base_rot,
                    tx=float(transform["tx"]) * k,
                    ty=float(transform["ty"]) * k,
                )
            )
            included_ids.append(section.id)

            # Low-detail warning now compares the EFFECTIVE render scale
            # (base_scale * k). With the upscale above every section normally
            # renders at >= 1×, so this only fires when the canvas cap clamped k
            # and a section is still downsampled below DETAIL_WARN_SCALE.
            effective_scale = base_scale * k
            if effective_scale < DETAIL_WARN_SCALE:
                warnings.append(
                    BuildWarning(
                        section_id=section.id,
                        code="low_detail",
                        message=(
                            f"Отсек {section.number} отрисован в масштабе "
                            f"{effective_scale:.2f}× — карта отсеков слишком мелкая"
                        ),
                    )
                )

        # Guard: every ok-section's mask was missing ⇒ nothing to assemble. Do NOT
        # extrude an all-zero canvas (the builder would 500/empty-contour anyway).
        if not warp_inputs:
            raise FloorSchemaError("No section masks to assemble")

        # Connectors → ConnectorRaster (master-pixel, k-scaled)
        connector_rows = await self._connector_repo.list_by_floor(floor_id)
        # (d) default thickness derived ONCE, k-scaled, floored to MIN_CONNECTOR_
        # THICKNESS_PX so a low-ppm floor still rasterises a VISIBLE band (a 1px
        # hairline is invisible next to 4-6px section walls). At normal ppm the
        # metric calculation already exceeds the floor, so this is a no-op.
        default_thickness_px = max(
            MIN_CONNECTOR_THICKNESS_PX,
            round(DEFAULT_CONNECTOR_THICKNESS_M * ppm_floor * k),
        )
        connectors_raster: list[ConnectorRaster] = []
        for row in connector_rows:
            pts = row.points or []
            if len(pts) < 2:
                continue
            # (c) de-normalise master-norm points × the (k-scaled) canvas dims.
            points_px = np.array(
                [[round(px * canvas_w), round(py * canvas_h)] for px, py in pts],
                dtype=np.int32,
            )
            thickness_m = row.thickness_m or DEFAULT_CONNECTOR_THICKNESS_M
            # Per-connector thickness is k-scaled too (a default-thickness connector
            # uses ``default_thickness_px``, NOT the un-scaled master-px value).
            thickness_px = max(
                MIN_CONNECTOR_THICKNESS_PX, round(thickness_m * ppm_floor * k)
            )
            connectors_raster.append(
                ConnectorRaster(points_px=points_px, thickness_px=thickness_px)
            )

        # Cutouts → CutoutRaster (master-pixel, SAME k-scaled canvas)
        # De-normalised over the IDENTICAL canvas_w/canvas_h the nav build uses, so
        # a cutout erases the same pixels in BOTH 3D and nav outputs.
        cutouts_raster: list[CutoutRaster] = []
        for raw in (floor.nav_cutouts or []):
            pts = raw.get("points", [])
            if len(pts) < 3:
                continue
            points_px = np.array(
                [[round(px * canvas_w), round(py * canvas_h)] for px, py in pts],
                dtype=np.int32,
            )
            cutouts_raster.append(CutoutRaster(points_px=points_px))

        # Assemble + extrude (builder UNCHANGED)
        combined = assemble_floor_mask(
            warp_inputs,
            canvas_size,
            connectors_raster,
            default_wall_thickness_px=default_thickness_px,
            cutouts=cutouts_raster,
        )

        try:
            # (e) ppm × k so metres stay correct on the k-shrunk canvas.
            mesh = build_mesh_from_mask(
                combined,
                floor_height=FLOOR_HEIGHT,
                pixels_per_meter=ppm_floor * k,
                vr=None,
            )
        except ImageProcessingError as exc:
            # Empty combined mask (no wall contours) is a clean 422, not a 500.
            if "No wall contours" in str(exc):
                raise FloorSchemaError("Empty floor mask") from exc
            raise

        glb_file_id, glb_url = await self._storage.save_floor_preview_mesh(
            floor_id, mesh
        )

        return BuildFloorPreviewResponse(
            floor_id=floor_id,
            glb_file_id=glb_file_id,
            glb_url=glb_url,
            persisted=False,
            pixels_per_meter=ppm_floor,
            canvas_size_px=canvas_size,
            included_sections=included_ids,
            excluded_sections=excluded,
            warnings=warnings,
            connector_count=len(connectors_raster),
            cutout_count=len(cutouts_raster),
        )

    async def confirm_floor_mesh(
        self, floor_id: int, glb_file_id: str
    ) -> ConfirmMeshResponse:
        """Promote a built preview GLB to the persisted floor model (confirm).

        The ONLY path that writes ``floors.mesh_file_glb``. Delegates the
        path validation + atomic promote to ``FileStorage``; a missing/invalid
        preview surfaces as ``PreviewNotFoundError`` (422).

        Args:
            floor_id: floor to confirm.
            glb_file_id: handle returned by a prior ``build_floor_mesh``.

        Returns:
            ConfirmMeshResponse (``persisted=True``) with the promoted GLB path/url.

        Raises:
            FloorNotFoundError: floor absent (404).
            PreviewNotFoundError: handle invalid / cross-floor / preview gone (422).
        """
        logger.info(
            "confirm_floor_mesh: floor_id=%d, glb_file_id=%s",
            floor_id,
            glb_file_id,
        )
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        try:
            rel_path, url = await self._storage.promote_floor_preview(
                floor_id, glb_file_id
            )
        except FileStorageError as exc:
            raise PreviewNotFoundError(glb_file_id) from exc

        await self._floor_repo.update_mesh_glb(floor_id, rel_path)

        return ConfirmMeshResponse(
            floor_id=floor_id,
            mesh_file_glb=rel_path,
            glb_url=url,
            persisted=True,
        )

    async def get_assembly(self, floor_id: int) -> FloorAssemblyResponse:
        """Single read powering the whole Floor Editor (assembly read, 05).

        Returns master-schema info, every section's full bind/solve/points/transform
        state, connectors and the last CONFIRMED ``mesh_file_glb`` (``None`` until a
        confirm runs — an unconfirmed preview is never reflected). Read-only:
        ``vectorization_data`` is only read (for ``image_size_cropped``), never
        written.

        Args:
            floor_id: floor to read.

        Returns:
            FloorAssemblyResponse — the complete editor payload.

        Raises:
            FloorNotFoundError: floor absent (404).
            ImageProcessingError: schema image present but undecodable.
        """
        logger.debug("get_assembly: floor_id=%d", floor_id)
        floor = await self._floor_repo.get_by_id(floor_id)
        if floor is None:
            raise FloorNotFoundError(floor_id)

        master_schema = self._build_master_schema_info(floor)

        sections = await self._section_repo.list_by_floor(floor_id)
        assembly_sections = [
            self._section_to_assembly(section) for section in sections
        ]

        connector_rows = await self._connector_repo.list_by_floor(floor_id)

        return FloorAssemblyResponse(
            floor_id=floor_id,
            pixels_per_meter=floor.pixels_per_meter,
            mesh_file_glb=floor.mesh_file_glb,
            master_schema=master_schema,
            sections=assembly_sections,
            connectors=[self._connector_to_model(r) for r in connector_rows],
            cutouts=[
                self._cutout_to_model(c, i)
                for i, c in enumerate(floor.nav_cutouts or [])
            ],
        )

    # Private helpers (IO / mapping)

    async def _master_pixel_dims(self, floor) -> tuple[int, int]:  # type: ignore[no-untyped-def]
        """Compute master-pixel canvas dims ``(Wm, Hm)`` from the schema.

        The master canvas IS the cropped master schema raster. To stay consistent
        with the master-norm frame that ``section.control_points`` (and
        ``floor.wall_polygons``) are normalised over, this mirrors the EXACT
        rotate-then-crop dimension arithmetic of
        ``processing.preprocessor.preprocess_image`` — only the dims, not the
        binarisation. Rotation by 90/270 swaps W and H; crop multiplies the
        (rotated) dims by ``schema_crop_bbox.width/height``. If no crop bbox is
        present, the full (rotated) image dims are used.

        Args:
            floor: the Floor ORM row (must carry ``schema_image_id`` /
                ``schema_crop_bbox``).

        Returns:
            ``(Wm, Hm)`` master-pixel width and height (ints, >= 1).

        Raises:
            FloorSchemaError: schema image not set or file missing.
            ImageProcessingError: the image file cannot be decoded.
        """
        if not floor.schema_image_id:
            raise FloorSchemaError("Floor has no master schema image")

        image_path = self._find_schema_image(floor.schema_image_id)
        if image_path is None:
            raise FloorSchemaError(
                f"Schema image '{floor.schema_image_id}' not found in storage"
            )
        image = cv2.imread(image_path)
        if image is None:
            raise ImageProcessingError(
                "master_pixel_dims", f"Failed to read schema image: {image_path}"
            )

        h, w = image.shape[:2]

        crop = floor.schema_crop_bbox
        rotation = int(crop.get("rotation", 0)) % 360 if crop else 0

        # 1. Rotation swaps the axes for 90 / 270 (mirrors preprocess_image).
        if rotation in (90, 270):
            w, h = h, w

        # 2. Crop multiplies the (rotated) dims; clamp to >= 1 like preprocess_image.
        if crop:
            crop_w = int(float(crop["width"]) * w)
            crop_h = int(float(crop["height"]) * h)
            w = max(1, min(crop_w, w))
            h = max(1, min(crop_h, h))

        logger.debug(
            "master_pixel_dims: floor_id=%d → Wm=%d, Hm=%d (rotation=%d, cropped=%s)",
            floor.id,
            w,
            h,
            rotation,
            bool(crop),
        )
        return w, h

    def _find_schema_image(self, image_id: str) -> Optional[str]:
        """Resolve a schema image path across the candidate upload subfolders.

        Schema images are uploaded through the generic upload flow and may land in
        ``plans/`` (no dedicated ``schemas/`` folder exists), so this mirrors
        ``FloorSchemaService._find_image``: try each candidate subfolder via
        ``FileStorage.find_file`` and return the first match, or ``None``.
        """
        for subfolder in ("schemas", "plans", "masks", ""):
            try:
                return self._storage.find_file(image_id, subfolder)
            except FileStorageError:
                continue
        return None

    def _load_section_mask_for_build(
        self, section  # type: ignore[no-untyped-def]
    ) -> Optional[np.ndarray]:
        """Load a section's wall mask for the build, or ``None`` if absent.

        UNLIKE the solve path, a missing mask file here is EXPECTED and non-fatal:
        the build excludes the section (reason ``mask_missing``) and proceeds.
        Returns a fresh grayscale array (never mutated), or ``None`` when the
        section has no ``mask_file_id`` or the file is missing on disk. An
        undecodable file is still an UNEXPECTED ImageProcessingError.

        Raises:
            ImageProcessingError: the mask file exists but cannot be decoded.
        """
        reconstruction = section.reconstruction
        mask_file_id = reconstruction.mask_file_id if reconstruction else None
        if not mask_file_id:
            return None
        try:
            mask_path = self._storage.find_file(mask_file_id, "masks")
        except FileStorageError:
            return None
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise ImageProcessingError(
                "build_floor_mesh", f"Failed to load mask: {mask_path}"
            )
        return mask

    def _build_master_schema_info(
        self, floor  # type: ignore[no-untyped-def]
    ) -> MasterSchemaInfo:
        """Map a Floor's schema fields to the assembly-read ``MasterSchemaInfo``.

        ``crop_bbox`` (response key) is populated from ``Floor.schema_crop_bbox``
        (ORM attr — the names differ on purpose). ``size_px``
        is the FULL (uncropped) schema image dimensions read from the image file;
        ``None`` if the image is absent (the editor still renders the rest).
        """
        image_id = floor.schema_image_id or ""
        url = (
            floor.schema_image.url
            if floor.schema_image_id and floor.schema_image is not None
            else ""
        )
        crop_bbox = (
            CropBboxModel(**floor.schema_crop_bbox)
            if floor.schema_crop_bbox
            else None
        )
        size_px = self._full_schema_size_px(floor)
        # Vectorised карта отсеков (normalised over the cropped master frame). The
        # JSON column stores [[x, y], ...] lists; coerce to tuples for the contract.
        wall_polygons = (
            [[(float(pt[0]), float(pt[1])) for pt in poly] for poly in floor.wall_polygons]
            if floor.wall_polygons
            else None
        )
        return MasterSchemaInfo(
            image_id=image_id,
            url=url,
            crop_bbox=crop_bbox,
            size_px=size_px,
            wall_polygons=wall_polygons,
        )

    def _full_schema_size_px(
        self, floor  # type: ignore[no-untyped-def]
    ) -> Optional[tuple[int, int]]:
        """Full (uncropped) ``(W, H)`` of the schema image, or ``None`` if absent.

        Read-only convenience for the assembly read; unlike ``_master_pixel_dims``
        it does NOT apply the crop bbox — the editor receives the raw image size and
        overlays the crop itself.
        """
        if not floor.schema_image_id:
            return None
        image_path = self._find_schema_image(floor.schema_image_id)
        if image_path is None:
            return None
        image = cv2.imread(image_path)
        if image is None:
            raise ImageProcessingError(
                "get_assembly", f"Failed to read schema image: {image_path}"
            )
        h, w = image.shape[:2]
        return (w, h)

    def _section_to_assembly(
        self, section  # type: ignore[no-untyped-def]
    ) -> AssemblySection:
        """Map a Section ORM row (with reconstruction) to ``AssemblySection``.

        ``status`` is ``"ok"`` iff a transform is persisted, else ``"needs_points"``
        — a degenerate solve leaves no transform and is not re-derivable from stored
        state, so the editor prompts for better points. ``vectorization_data`` is
        read-only (used only for ``image_size_cropped``).
        """
        reconstruction = section.reconstruction
        reconstruction_id = reconstruction.id if reconstruction else None

        mask_file_id = reconstruction.mask_file_id if reconstruction else None
        # Viewable URL of the cropped wall mask (eager-loaded by the section repo).
        mask_url = (
            reconstruction.mask_file.url
            if reconstruction is not None and reconstruction.mask_file is not None
            else None
        )
        # Section outline polygon (normalised over the master frame). Stored as
        # {"points": [[x, y], ...]}; coerce to a list of (x, y) tuples or None.
        geometry = self._read_section_geometry(section)
        image_size_cropped = (
            self._read_image_size_cropped(reconstruction)
            if reconstruction
            else None
        )

        section_cps = [
            ControlPoint(id=str(cp["id"]), x=float(cp["x"]), y=float(cp["y"]))
            for cp in ((reconstruction.control_points if reconstruction else None) or [])
            if isinstance(cp, dict) and cp.get("id") is not None
        ]
        master_cps = [
            MasterControlPoint(
                point_id=str(mp["point_id"]),
                x=float(mp["x"]),
                y=float(mp["y"]),
            )
            for mp in (section.control_points or [])
            if isinstance(mp, dict) and mp.get("point_id") is not None
        ]

        transform = (
            SectionTransform(**section.transform) if section.transform else None
        )
        status = "ok" if section.transform else "needs_points"

        return AssemblySection(
            section_id=section.id,
            number=section.number,
            reconstruction_id=reconstruction_id,
            mask_file_id=mask_file_id,
            mask_url=mask_url,
            geometry=geometry,
            image_size_cropped=image_size_cropped,
            section_control_points=section_cps,
            master_control_points=master_cps,
            transform=transform,
            status=status,
        )

    @staticmethod
    def _read_section_geometry(
        section,  # type: ignore[no-untyped-def]
    ) -> Optional[list[tuple[float, float]]]:
        """Read a section's outline polygon from ``section.geometry`` (read-only).

        Stored as ``{"points": [[x, y], ...]}`` (normalised [0,1] over the master
        frame). Returns a list of ``(x, y)`` tuples, or ``None`` if absent/malformed.
        """
        geom = section.geometry
        if not isinstance(geom, dict):
            return None
        points = geom.get("points")
        if not isinstance(points, list) or len(points) < 3:
            return None
        try:
            return [(float(p[0]), float(p[1])) for p in points]
        except (TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def _read_image_size_cropped(
        reconstruction,  # type: ignore[no-untyped-def]
    ) -> Optional[tuple[int, int]]:
        """Read ``image_size_cropped`` from ``vectorization_data`` (read-only).

        Returns ``(W, H)`` as ints, or ``None`` if the column is empty/unparseable
        or the key is absent/malformed. Never writes ``vectorization_data``.
        """
        raw = reconstruction.vectorization_data
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        size = data.get("image_size_cropped")
        if not size or len(size) != 2:
            return None
        try:
            return (int(size[0]), int(size[1]))
        except (TypeError, ValueError):
            return None

    def _storage_load_mask_sync_guard(
        self, section, reconstruction  # type: ignore[no-untyped-def]
    ) -> np.ndarray:
        """Load a section's wall mask, never mutating the returned array.

        Wraps ``find_file`` + ``cv2.imread`` directly (the storage ``load_mask`` is
        async; this service method is sync because it is called inside the pure
        per-section computation). Returns a fresh grayscale array. Any IO failure
        propagates as an UNEXPECTED error so the atomic solve aborts before any
        persist.

        Raises:
            SectionValidationError: the section has no ``mask_file_id``.
            FileStorageError: the mask file is missing on disk.
            ImageProcessingError: the mask cannot be decoded.
        """
        mask_file_id = reconstruction.mask_file_id
        if not mask_file_id:
            raise SectionValidationError(
                f"Section {section.id} reconstruction has no mask file"
            )
        mask_path = self._storage.find_file(mask_file_id, "masks")
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise ImageProcessingError(
                "solve_transforms", f"Failed to load mask: {mask_path}"
            )
        return mask

    @staticmethod
    def _read_section_ppm(reconstruction) -> Optional[float]:  # type: ignore[no-untyped-def]
        """Read ``estimated_pixels_per_meter`` from ``vectorization_data`` (read-only).

        ``vectorization_data`` is a nullable JSON string. Returns the value as a
        float, or ``None`` if the column is empty / unparseable / the key is absent.
        Never writes ``vectorization_data``.
        """
        raw = reconstruction.vectorization_data
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "vectorization_data unparseable for reconstruction %s: %s",
                reconstruction.id,
                exc,
            )
            return None
        value = data.get("estimated_pixels_per_meter")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _assert_mask_matches_cropped(
        reconstruction, w_s: int, h_s: int  # type: ignore[no-untyped-def]
    ) -> None:
        """Assert the loaded mask aspect ≈ stored ``image_size_cropped``.

        The warp moves the mask's pixels, so the control points must be
        de-normalised by the mask's OWN dims. By construction the mask is the
        cropped plan raster, so its aspect must match ``image_size_cropped`` —
        a gross mismatch means a stale / wrong size and would silently shift
        geometry. Read-only on ``vectorization_data``.

        Raises:
            ImageProcessingError: aspect ratios disagree beyond ``_ASPECT_TOL``.
        """
        raw = reconstruction.vectorization_data
        if not raw:
            return  # no stored size to compare against — nothing to assert
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        size = data.get("image_size_cropped")
        if not size or len(size) != 2:
            return
        stored_w, stored_h = float(size[0]), float(size[1])
        if stored_w <= 0 or stored_h <= 0 or h_s <= 0:
            return
        mask_aspect = w_s / h_s
        stored_aspect = stored_w / stored_h
        if abs(mask_aspect - stored_aspect) > _ASPECT_TOL * stored_aspect:
            raise ImageProcessingError(
                "solve_transforms",
                f"Section {reconstruction.id} mask dims ({w_s}x{h_s}) do not match "
                f"image_size_cropped ({int(stored_w)}x{int(stored_h)})",
            )

    @staticmethod
    def _connector_to_model(row) -> Connector:  # type: ignore[no-untyped-def]
        """Map a ``FloorConnector`` ORM row to the ``Connector`` response model."""
        points = [(float(p[0]), float(p[1])) for p in (row.points or [])]
        return Connector(
            id=row.id,
            points=points,
            height_m=row.height_m,
            thickness_m=row.thickness_m,
            connects=row.connects,
        )

    @staticmethod
    def _cutout_to_model(raw: dict, idx: int) -> Cutout:
        """Map one ``nav_cutouts`` JSON entry to the ``Cutout`` response model.

        ``id`` is the 0-based list index (the column has no child PK).
        """
        points = [(float(p[0]), float(p[1])) for p in raw.get("points", [])]
        return Cutout(id=idx, points=points)
