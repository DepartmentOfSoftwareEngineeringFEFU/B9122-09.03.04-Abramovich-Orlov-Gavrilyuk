"""Pure mask assembly for the stitched-floor pipeline — PURE layer.

Warps each section wall mask by its solved uniform similarity
``(scale, rotation_rad, tx, ty)``, OR-composites the warped masks into the
master-pixel canvas, rasterises the floor connectors as OPEN-polyline wall
bands, and finally ERASES cutout zones (fill ``0``) so they become passable for
nav AND un-extruded in 3D. Returns a binary ``{0, 255}`` mask ready for the
unchanged ``build_mesh_from_mask`` (design pipeline spec).

NOTE: ``processing/`` is the PURE layer. This module imports ONLY ``cv2``,
``numpy`` and ``dataclasses`` — no core config, no DB/IO/Pydantic/ORM, no service.
``SectionWarpInput`` / ``ConnectorRaster`` are plain frozen dataclasses (no
Pydantic, no ORM) so the layer stays pure.

The canvas size and the per-section transforms are decided by the SERVICE: it
knows the master-schema crop dims and the memory-guard factor ``k``
(``MAX_FLOOR_CANVAS_PX``), and passes ``canvas_size`` with the transforms already
pre-multiplied by ``k`` (pipeline spec). This function only honours the
``canvas_size`` it is handed — it never derives ``k`` or reads any constant.
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SectionWarpInput:
    """One section's wall mask plus its solved uniform-similarity transform.

    The applied transform is ``scale * R(rotation_rad)`` plus translation, with
    ``R(rotation_rad) = [[cos, -sin], [sin, cos]]``; ``rotation_rad == 0`` reduces
    to the plain ``[[scale, 0, tx], [0, scale, ty]]`` warp (prior behaviour).

    Attributes:
        section_id: id of the source section (for callers; unused by the warp).
        mask: ``(Hs, Ws)`` uint8 binary ``{0, 255}`` section wall mask. Never
            mutated — ``warpAffine`` reads it into a fresh output array.
        scale: single isotropic scale ``s`` (same on both axes).
        rotation_rad: section->master rotation in radians. Invariant to the
            memory-guard factor ``k`` (which scales only scale/tx/ty).
        tx: translation in x, in master pixels.
        ty: translation in y, in master pixels.
    """

    section_id: int
    mask: np.ndarray
    scale: float
    rotation_rad: float
    tx: float
    ty: float


@dataclass(frozen=True)
class ConnectorRaster:
    """One floor connector as an open polyline in master-pixel coordinates.

    Attributes:
        points_px: ``(M, 2)`` int32 master-pixel vertices of an OPEN polyline
            (no implicit closing segment from the last vertex back to the first).
        thickness_px: wall-band thickness in master pixels. MUST be ``>= 1``; the
            caller (service) rounds up, because OpenCV treats
            ``thickness=0`` as a 1px hairline rather than "nothing".
    """

    points_px: np.ndarray
    thickness_px: int


@dataclass(frozen=True)
class CutoutRaster:
    """One cutout zone as a CLOSED polygon in master-pixel coordinates.

    A cutout ERASES walls: its interior is filled with ``0`` (free) so the zone
    becomes passable for the nav graph AND un-extruded in the 3D mesh. It is the
    subtractive mirror of ``ConnectorRaster`` (which adds wall bands).

    Attributes:
        points_px: ``(M, 2)`` int32 master-pixel vertices, ``M >= 3``. The polygon
            is FILLED (``cv2.fillPoly``), not stroked — the whole interior is
            erased. Out-of-canvas vertices are safe (``fillPoly`` clips).
    """

    points_px: np.ndarray


def assemble_floor_mask(
    sections: list[SectionWarpInput],
    canvas_size: tuple[int, int],
    connectors: list[ConnectorRaster],
    default_wall_thickness_px: int,
    cutouts: list[CutoutRaster] | None = None,
) -> np.ndarray:
    """Warp + OR-composite section masks, rasterise connectors, erase cutouts.

    Pure assembly per pipeline spec: each section mask is warped by its
    ``(scale, rotation_rad, tx, ty)`` into the master-pixel canvas with
    ``INTER_NEAREST`` (keeps the result strictly binary) and ``borderValue=0``
    (out-of-canvas pixels contribute nothing); the warped masks are unioned with
    ``cv2.max`` so seam overlaps stay ``255`` (never sum to ``510``); connectors
    are drawn as OPEN polyline wall bands (no fill, no closing segment); finally
    each cutout zone is FILLED with ``0`` (free), drawn LAST so it erases section
    walls AND any overlapping connector inside its polygon. Because BOTH the 3D
    mesh build and the nav build call this one function, a saved cutout reaches
    both outputs from a single edit.

    Args:
        sections: section masks plus their solved transforms. Input masks are
            never mutated.
        canvas_size: ``(Wm, Hm)`` master-pixel dims (width, height) of the floor
            canvas — the master-schema crop dims (already capped by the service).
            NOTE the axis order: a numpy array is ``(rows, cols) = (Hm, Wm)``.
        connectors: open-polyline connectors in master-pixel int coordinates.
        default_wall_thickness_px: fallback wall-band thickness (master pixels)
            used when a connector's own ``thickness_px`` is falsy; expected
            ``>= 1``.
        cutouts: closed-polygon zones to erase (fill with ``0``) AFTER walls and
            connectors. ``None``/empty leaves the mask exactly as before this
            param existed (defaulted so existing callers stay valid).

    Returns:
        ``(Hm, Wm)`` uint8 binary mask with values strictly in ``{0, 255}``.

    Notes:
        Normalisation of inputs to strictly binary is the SERVICE's job,
        not this function's: the pure function trusts that section masks are
        already ``{0, 255}``.
    """
    cutouts = cutouts or []
    # Step 1 — allocate the canvas. canvas_size is (Wm, Hm) but a numpy array is
    # (rows, cols) = (Hm, Wm); mixing these would transpose the whole floor.
    width_m, height_m = canvas_size
    canvas = np.zeros((height_m, width_m), dtype=np.uint8)

    # Step 2 — warp each section and OR-composite it into the canvas. The input
    # mask is never mutated: warpAffine writes into a fresh output array, and the
    # canvas is itself a fresh array.
    for section in sections:
        # scale * R(rotation_rad): rotation_rad == 0 gives cos=scale, sin=0, i.e.
        # the plain [[scale, 0, tx], [0, scale, ty]] warp (exact prior behaviour).
        cos = section.scale * np.cos(section.rotation_rad)
        sin = section.scale * np.sin(section.rotation_rad)
        affine = np.array(
            [[cos, -sin, section.tx], [sin, cos, section.ty]],
            dtype=np.float64,
        )
        warped = cv2.warpAffine(
            section.mask,
            affine,
            (width_m, height_m),  # dsize is (cols, rows) = (Wm, Hm)
            flags=cv2.INTER_NEAREST,  # preserves binary {0, 255}, no edge bleed
            borderValue=0,  # out-of-canvas pixels contribute nothing
        )
        # Pixel-wise OR for binary masks: overlaps stay 255 (no 510 overflow).
        canvas = cv2.max(canvas, warped)

    # Step 3 — rasterise each connector as an OPEN polyline wall band. No fill and
    # no closing segment (corridor mouths stay passable). max(1, ...) guards
    # against a rounded-down 0 silently degrading to a 1px hairline.
    for connector in connectors:
        thickness = connector.thickness_px or default_wall_thickness_px
        cv2.polylines(
            canvas,
            [connector.points_px],
            isClosed=False,
            color=255,
            thickness=max(1, thickness),
        )

    # Step 4 — erase cutout zones (free space). Drawn LAST so a cutout wins over
    # section walls AND any overlapping connector inside its polygon
    # ("definitely a passage"). fillPoly clips out-of-canvas vertices; the canvas
    # stays strictly binary because color=0 cannot introduce other values.
    for cutout in cutouts:
        cv2.fillPoly(canvas, [cutout.points_px], color=0)

    # Step 5 — return the assembled binary canvas.
    return canvas


def compute_canvas_factor(
    sections: list[tuple[float, float]],
    long_side_px: int,
    ppm: float,
    max_canvas_px: int,
    trust_residual_m: float,
) -> float:
    """Memory-guard scale factor ``k`` for the assembled floor canvas.

    ``k`` upscales so the most-detailed section (the smallest solved scale)
    rasterises at ~native resolution — ``k = 1 / min(scale)`` — clamped to
    ``[1, max_canvas_px / long_side_px]``. A MIS-REGISTERED section has a
    least-squares scale spuriously shrunk toward 0 (its points fit no single
    similarity); left in, it would inflate ``k`` and over-upscale the whole floor.
    Such sections — registration residual above ``trust_residual_m`` metres
    (``residual_px / ppm``) — are excluded from the ``min``-scale estimate. If
    every section is untrusted (or ``ppm`` is non-positive) all are used, so the
    result is never worse than the un-guarded ``min``.

    Pure: ``math`` only. The SERVICE owns this call so the mesh and nav builds
    derive ``k`` IDENTICALLY — both pass the same arguments here.

    Args:
        sections: ``(scale, residual_rms_px)`` per buildable section (master px).
        long_side_px: longer master-canvas dimension in pixels.
        ppm: master pixels per metre (``ppm_floor``); metricises the residuals.
        max_canvas_px: long-side cap for the assembled canvas (memory guard).
        trust_residual_m: residual (metres) above which a section is excluded
            from the min-scale estimate.

    Returns:
        The scale factor ``k >= 1.0`` (``1.0`` when no section has a positive
        finite scale).
    """
    scales = [sc for sc, _ in sections if math.isfinite(sc) and sc > 0]
    if not scales:
        return 1.0
    trusted = [
        sc
        for sc, residual_px in sections
        if math.isfinite(sc)
        and sc > 0
        and ppm > 0
        and residual_px / ppm <= trust_residual_m
    ]
    min_scale = min(trusted) if trusted else min(scales)
    upscale = max(1.0, 1.0 / min_scale)
    if long_side_px <= 0:
        return upscale
    return min(upscale, max_canvas_px / long_side_px)
