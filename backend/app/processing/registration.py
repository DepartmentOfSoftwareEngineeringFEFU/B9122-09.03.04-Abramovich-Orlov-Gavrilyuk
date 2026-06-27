"""Uniform similarity least-squares solver (Umeyama) — PURE layer.

Fits a single isotropic scale ``s``, a proper rotation ``R(theta)`` and a
translation ``(tx, ty)`` mapping section-pixel control points onto their
master-pixel counterparts::

    [X, Y] = s * R(theta) @ [x, y] + [tx, ty]

This is the closed-form least-squares similarity (Umeyama 1991), reflection-
prevented so ``scale >= 0`` always: a mirrored target maps to the NEAREST proper
rotation (``det(R) = +1``), surfacing as a large residual rather than a negative
scale. A single scalar ``s`` is applied to both axes (no shear, no per-axis
scale), so a square cabinet stays square (design AC4); no rotation (``theta ~ 0``)
is the strict sub-case reproducing the prior scale+translation fit.

NOTE: ``processing/`` is the PURE layer. This module imports ONLY ``numpy`` and
``dataclasses`` — no core config, no DB/IO/Pydantic/ORM, no OpenCV. The solver
receives ``min_baseline_px`` as an argument (the service computes it from
``R_MIN_BASELINE_FRAC``). ``DegenerateControlPointsError`` is DEFINED here: this
module is its home, and the service imports it from here.
"""

from dataclasses import dataclass

import numpy as np

# The minimum control-point count is the ONE intentional duplication of
# MIN_CONTROL_POINTS (defined in the core constants module). It is inlined as a
# literal here so the PURE layer stays free of any core-config dependency. Keep
# this value in sync with MIN_CONTROL_POINTS (= 3).
_MIN_POINTS = 3

# Guard threshold for the centred source variance (denominator of the scale
# estimate). Anything at or below this is treated as a coincident point set.
_DENOM_EPS = 1e-12


class DegenerateControlPointsError(Exception):
    """Raised when control points cannot determine a stable similarity.

    Reasons: fewer than three points, a near-zero baseline (coincident points),
    or a non-finite numerical result. The service maps this to a ``degenerate``
    section status and surfaces ``reason`` to the operator.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SimilarityResult:
    """Result of a uniform-similarity fit, in master-pixel space.

    The mapping is ``y = scale * R(rotation_rad) @ x + (tx, ty)`` with
    ``R(rotation_rad) = [[cos, -sin], [sin, cos]]``.

    Attributes:
        scale: single isotropic scale factor ``s`` (same on both axes), ``>= 0``.
        rotation_rad: section->master rotation in radians,
            ``atan2(R[1, 0], R[0, 0])``; ``~ 0`` for an unrotated section.
        tx: translation in x (master pixels).
        ty: translation in y (master pixels).
        residual_rms: root-mean-square of per-point residuals (master pixels).
        n_points: number of control-point pairs used in the fit.
    """

    scale: float
    rotation_rad: float
    tx: float
    ty: float
    residual_rms: float
    n_points: int


def _max_pairwise_distance(points: np.ndarray) -> float:
    """Return the true maximum pairwise Euclidean distance among points.

    Args:
        points: ``(N, 2)`` float64 array.

    Returns:
        Largest distance between any two points; ``0.0`` for ``N < 2``.

    Notes:
        Uses an explicit O(N^2) loop. Control-point sets are capped at 20 points
        (``MAX_CONTROL_POINTS``), so this is trivially cheap. The bounding-box
        diagonal is deliberately NOT used as a proxy: for collinear / near-
        collinear sets (explicitly accepted for a pure scale) the bbox diagonal
        over-estimates the along-line spread that actually feeds the solver's
        denominator, so it could wrongly accept a set the baseline guard must
        reject.
    """
    n = len(points)
    max_dist = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            diff = points[i] - points[j]
            dist = float(np.hypot(diff[0], diff[1]))
            if dist > max_dist:
                max_dist = dist
    return max_dist


def solve_similarity(
    src: np.ndarray,
    dst: np.ndarray,
    min_baseline_px: float,
) -> SimilarityResult:
    """Fit a similarity ``(scale, rotation_rad, tx, ty)`` of ``src`` onto ``dst``.

    Closed-form Umeyama least-squares similarity: a single isotropic scale, a
    proper rotation and a translation (no shear, no per-axis scale). Reflection
    is prevented (``scale >= 0``). See pipeline spec

    Args:
        src: ``(N, 2)`` float64 section-pixel coordinates, ``N >= 3``.
        dst: ``(N, 2)`` float64 master-pixel coordinates, paired with ``src`` by
            index (``src[i]`` and ``dst[i]`` are the same control-point ID).
        min_baseline_px: minimum acceptable maximum-pairwise-distance among
            ``src`` points (the service derives this from the section image
            diagonal via ``R_MIN_BASELINE_FRAC``).

    Returns:
        SimilarityResult with the fitted ``scale``, ``rotation_rad``, ``tx``,
        ``ty``, the ``residual_rms`` in master pixels, and ``n_points``.

    Raises:
        DegenerateControlPointsError: if there are fewer than three points, the
            point set has a near-zero baseline (coincident), or the solve yields
            a non-finite value.

    Notes:
        The inputs ``src`` and ``dst`` are never mutated — centring creates new
        arrays. A single scalar ``scale`` is applied to both axes (no per-axis
        scale, AC4); a mirrored target is corrected to the nearest proper
        rotation, never raised as an error.
    """
    # Step 1 — validate shapes.
    if src.shape != dst.shape:
        raise DegenerateControlPointsError(
            f"src/dst shape mismatch: {src.shape} vs {dst.shape}"
        )
    if src.ndim != 2 or src.shape[1] != 2:
        raise DegenerateControlPointsError(
            f"expected (N, 2) arrays, got shape {src.shape}"
        )

    # Step 2 — too few points. The literal 3 mirrors MIN_CONTROL_POINTS; the
    # pure module must not import core (see module docstring).
    n = len(src)
    if n < _MIN_POINTS:
        raise DegenerateControlPointsError("too few points")

    # Step 3 — coincident / short-baseline guard using the TRUE max pairwise
    # distance (not the bbox diagonal — see _max_pairwise_distance).
    if _max_pairwise_distance(src) < min_baseline_px:
        raise DegenerateControlPointsError("baseline too short")

    # Step 4 — centre both point sets (new arrays; inputs untouched).
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_centred = src - src_mean
    dst_centred = dst - dst_mean

    # Step 5 — source variance (Umeyama denominator); guards coincident points.
    var_s = float((src_centred * src_centred).sum() / n)
    if var_s <= _DENOM_EPS:
        raise DegenerateControlPointsError("baseline too short")

    # Step 6 — closed-form Umeyama similarity (scale + proper rotation +
    # translation). The cross-covariance SVD gives the rotation; a reflection in
    # the raw fit is corrected to the nearest proper rotation (det = +1) via
    # ``s_corr``, so ``scale`` stays >= 0 (a true mismatch shows as a high
    # residual rather than a negative scale).
    sigma = (dst_centred.T @ src_centred) / n
    u_mat, sing, vt_mat = np.linalg.svd(sigma)
    s_corr = np.eye(2)
    if np.linalg.det(u_mat) * np.linalg.det(vt_mat) < 0.0:
        s_corr[1, 1] = -1.0
    rot = u_mat @ s_corr @ vt_mat
    scale = float((sing * np.diag(s_corr)).sum() / var_s)
    translation = dst_mean - scale * (rot @ src_mean)
    tx = float(translation[0])
    ty = float(translation[1])
    rotation_rad = float(np.arctan2(rot[1, 0], rot[0, 0]))

    # Step 7 — residual RMS in master pixels (full similarity applied).
    pred = (scale * (rot @ src.T)).T + np.array([tx, ty], dtype=np.float64)
    residual_rms = float(np.sqrt(np.mean(((dst - pred) ** 2).sum(axis=1))))

    # Step 8 — non-finite guard (numerical failure).
    if not all(
        np.isfinite(v) for v in (scale, rotation_rad, tx, ty, residual_rms)
    ):
        raise DegenerateControlPointsError("non-finite")

    # Step 9 — return.
    return SimilarityResult(
        scale=scale,
        rotation_rad=rotation_rad,
        tx=tx,
        ty=ty,
        residual_rms=residual_rms,
        n_points=n,
    )
