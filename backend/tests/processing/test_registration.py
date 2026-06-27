"""Unit tests for the pure uniform-similarity solver.


plus the non-displacement
maths tests that are assertable directly on the transform (AC4).
"""

import numpy as np
import pytest

from app.processing.registration import (
    DegenerateControlPointsError,
    SimilarityResult,
    solve_similarity,
)

# A permissive baseline for happy-path tests: the synthetic point sets below are
# well-spread (spread >> 1 px), so any small threshold lets them through. The
# coincident-guard tests pass their own large threshold explicitly.
LENIENT_BASELINE_PX = 1e-6


def make_points(
    n: int,
    scale: float,
    shift: tuple[float, float],
    noise: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic ``(src, dst)`` pair with a known uniform similarity.

    The destination is ``dst = scale * src + shift`` (+ optional Gaussian noise).
    Source points are deterministic, non-collinear and well-spread so the
    baseline guard never trips spuriously.

    Args:
        n: number of point pairs (``>= 1``).
        scale: isotropic scale applied to ``src`` to form ``dst``.
        shift: ``(tx, ty)`` translation applied after scaling.
        noise: standard deviation of optional Gaussian noise added to ``dst``.

    Returns:
        ``(src, dst)`` as ``(n, 2)`` float64 arrays.
    """
    rng = np.random.default_rng(seed=42)
    # Deterministic spread on a circle so points are distinct and non-collinear.
    angles = np.linspace(0.0, 2.0 * np.pi, num=n, endpoint=False)
    radius = 100.0
    src = np.stack(
        [50.0 + radius * np.cos(angles), 60.0 + radius * np.sin(angles)],
        axis=1,
    ).astype(np.float64)
    dst = scale * src + np.array(shift, dtype=np.float64)
    if noise > 0.0:
        dst = dst + rng.normal(0.0, noise, size=dst.shape)
    return src, dst


def make_points_rot(
    n: int,
    scale: float,
    deg: float,
    shift: tuple[float, float],
    noise: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic ``(src, dst)`` pair with a known similarity INCLUDING rotation.

    The destination is ``dst = scale * (R(deg) @ src) + shift`` (+ optional
    Gaussian noise), where ``R(deg)`` is a proper rotation by ``deg`` degrees.
    Source points are the same well-spread circle as ``make_points``.

    Args:
        n: number of point pairs (``>= 1``).
        scale: isotropic scale applied to ``src`` before rotation.
        deg: rotation angle in degrees (section->master).
        shift: ``(tx, ty)`` translation applied after scale+rotation.
        noise: standard deviation of optional Gaussian noise added to ``dst``.

    Returns:
        ``(src, dst)`` as ``(n, 2)`` float64 arrays.
    """
    rng = np.random.default_rng(seed=7)
    angles = np.linspace(0.0, 2.0 * np.pi, num=n, endpoint=False)
    radius = 100.0
    src = np.stack(
        [50.0 + radius * np.cos(angles), 60.0 + radius * np.sin(angles)],
        axis=1,
    ).astype(np.float64)
    theta = np.deg2rad(deg)
    rot = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
        dtype=np.float64,
    )
    dst = (scale * (rot @ src.T)).T + np.array(shift, dtype=np.float64)
    if noise > 0.0:
        dst = dst + rng.normal(0.0, noise, size=dst.shape)
    return src, dst


def _signed_area(tri: np.ndarray) -> float:
    """Signed area of a triangle ``(3, 2)``; its sign encodes the winding."""
    return 0.5 * (
        (tri[1, 0] - tri[0, 0]) * (tri[2, 1] - tri[0, 1])
        - (tri[2, 0] - tri[0, 0]) * (tri[1, 1] - tri[0, 1])
    )


def test_solve_identity_returns_unit_scale_zero_shift():
    # Arrange
    src, dst = make_points(3, scale=1.0, shift=(0.0, 0.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert
    assert result.scale == pytest.approx(1.0, abs=1e-9)
    assert result.tx == pytest.approx(0.0, abs=1e-9)
    assert result.ty == pytest.approx(0.0, abs=1e-9)
    assert result.residual_rms == pytest.approx(0.0, abs=1e-9)


def test_solve_pure_translation_recovers_shift():
    # Arrange
    src, dst = make_points(4, scale=1.0, shift=(10.0, 20.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert
    assert result.scale == pytest.approx(1.0, abs=1e-9)
    assert result.tx == pytest.approx(10.0, abs=1e-6)
    assert result.ty == pytest.approx(20.0, abs=1e-6)


def test_solve_pure_scale_recovers_scale():
    # Arrange — dst = 2 * src, shift consistent with the centring.
    src, dst = make_points(4, scale=2.0, shift=(0.0, 0.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert
    assert result.scale == pytest.approx(2.0, abs=1e-9)
    # With dst = 2*src and no shift, tx = q̄ - s*p̄ = 2*p̄ - 2*p̄ = 0.
    assert result.tx == pytest.approx(0.0, abs=1e-6)
    assert result.ty == pytest.approx(0.0, abs=1e-6)


def test_solve_scale_and_shift_recovers_both():
    # Arrange — dst = 1.5 * src + (30, -5).
    src, dst = make_points(5, scale=1.5, shift=(30.0, -5.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — all three within 1e-6.
    assert result.scale == pytest.approx(1.5, abs=1e-6)
    assert result.tx == pytest.approx(30.0, abs=1e-6)
    assert result.ty == pytest.approx(-5.0, abs=1e-6)


def test_solve_is_isotropic_ignores_anisotropic_target():
    # Arrange — dst = diag(2, 3) * src (different x/y scale on centred points).
    src, _ = make_points(6, scale=1.0, shift=(0.0, 0.0))
    src_centred = src - src.mean(axis=0)
    dst = src_centred @ np.array([[2.0, 0.0], [0.0, 3.0]], dtype=np.float64)

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — exactly ONE scale (the dataclass has no sx/sy), a best fit
    # between 2 and 3, and a non-zero residual because no single isotropic
    # scale can satisfy an anisotropic target.
    assert isinstance(result, SimilarityResult)
    assert not hasattr(result, "sx")
    assert not hasattr(result, "sy")
    assert 2.0 < result.scale < 3.0
    assert result.residual_rms > 0.0


def test_solve_three_points_is_sufficient():
    # Arrange — exactly 3 distinct points.
    src, dst = make_points(3, scale=1.2, shift=(5.0, 7.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert
    assert result.n_points == 3
    assert result.scale == pytest.approx(1.2, abs=1e-6)


def test_solve_collinear_wellspread_is_accepted():
    # Arrange — 3 collinear points along a long baseline (pure scale is fine for
    # collinear sets; only a short baseline is rejected).
    src = np.array([[0.0, 0.0], [100.0, 0.0], [200.0, 0.0]], dtype=np.float64)
    dst = 1.5 * src + np.array([10.0, 4.0], dtype=np.float64)

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — solves cleanly despite collinearity.
    assert result.scale == pytest.approx(1.5, abs=1e-6)
    assert result.tx == pytest.approx(10.0, abs=1e-6)
    assert result.ty == pytest.approx(4.0, abs=1e-6)
    assert result.residual_rms == pytest.approx(0.0, abs=1e-6)


def test_solve_reports_residual_rms():
    # Arrange — a deliberately noisy dst; compute the expected RMS by hand from
    # the SAME solver output (the contract is: residual_rms == RMS of the
    # per-point residuals under the returned transform).
    src, dst = make_points(6, scale=1.3, shift=(12.0, -8.0), noise=2.5)

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — hand-computed RMS of residuals (full similarity) matches the value.
    theta = result.rotation_rad
    rot = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
        dtype=np.float64,
    )
    pred = (result.scale * (rot @ src.T)).T + np.array([result.tx, result.ty])
    expected_rms = np.sqrt(np.mean(((dst - pred) ** 2).sum(axis=1)))
    assert result.residual_rms == pytest.approx(expected_rms, abs=1e-9)
    assert result.residual_rms > 0.0


def test_solve_isolates_single_misclick_in_residual():
    # Arrange — clean fit vs the same set with one point nudged far off.
    src, dst_clean = make_points(5, scale=1.0, shift=(0.0, 0.0))
    dst_bad = dst_clean.copy()
    dst_bad[2] = dst_bad[2] + np.array([40.0, 25.0])  # one mis-click

    # Act
    clean = solve_similarity(src, dst_clean, LENIENT_BASELINE_PX)
    bad = solve_similarity(src, dst_bad, LENIENT_BASELINE_PX)

    # Assert — the misclick raises the residual noticeably (the >=3 policy).
    assert clean.residual_rms == pytest.approx(0.0, abs=1e-9)
    assert bad.residual_rms > 1.0


@pytest.mark.parametrize("n", [1, 2])
def test_solve_fewer_than_three_points_raises(n: int):
    # Arrange
    src, dst = make_points(n, scale=1.0, shift=(0.0, 0.0))

    # Act / Assert
    with pytest.raises(DegenerateControlPointsError) as exc:
        solve_similarity(src, dst, LENIENT_BASELINE_PX)
    assert exc.value.reason == "too few points"


def test_solve_coincident_points_raises():
    # Arrange — all points within a tiny radius; pass a baseline larger than the
    # cluster spread so the coincident guard must reject it.
    src = np.array([[10.0, 10.0], [10.5, 10.2], [9.8, 10.4]], dtype=np.float64)
    dst = src + np.array([3.0, 3.0], dtype=np.float64)
    min_baseline_px = 50.0  # >> max pairwise distance (~0.6 px)

    # Act / Assert
    with pytest.raises(DegenerateControlPointsError) as exc:
        solve_similarity(src, dst, min_baseline_px)
    assert exc.value.reason == "baseline too short"


def test_solve_does_not_mutate_inputs():
    # Arrange — keep byte-exact copies of the inputs.
    src, dst = make_points(5, scale=1.7, shift=(11.0, -3.0))
    src_copy = src.copy()
    dst_copy = dst.copy()

    # Act
    solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — inputs are unchanged (centring must create new arrays).
    np.testing.assert_array_equal(src, src_copy)
    np.testing.assert_array_equal(dst, dst_copy)


# --- Non-displacement maths (AC4), assertable directly on the transform ------


def test_uniform_warp_preserves_cabinet_aspect_ratio():
    # Arrange — a known unit square and a recovered transform WITH rotation, to
    # prove a square stays square under a rotated similarity too (AC4).
    src, dst = make_points_rot(4, scale=2.5, deg=50.0, shift=(7.0, -4.0))
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)
    square = np.array(
        [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
        dtype=np.float64,
    )
    theta = result.rotation_rad
    rot = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
        dtype=np.float64,
    )

    # Act — apply the FULL similarity y = s*R*x + t to the square corners.
    warped = (result.scale * (rot @ square.T)).T + np.array(
        [result.tx, result.ty]
    )

    # Assert — the warped quad is still a square: equal adjacent side lengths.
    width = np.hypot(*(warped[1] - warped[0]))
    height = np.hypot(*(warped[2] - warped[1]))
    assert width == pytest.approx(height, rel=1e-9)
    # And it is scaled by exactly s relative to the original (square stays square).
    assert width == pytest.approx(result.scale * 10.0, rel=1e-9)


def test_uniform_warp_rotates_relative_positions():
    # Arrange — a recovered transform WITH rotation (35°), scale and shift.
    src, dst = make_points_rot(5, scale=1.8, deg=35.0, shift=(15.0, 22.0))
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)
    a = np.array([20.0, 30.0], dtype=np.float64)
    b = np.array([60.0, 90.0], dtype=np.float64)
    theta = result.rotation_rad
    rot = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
        dtype=np.float64,
    )
    t = np.array([result.tx, result.ty])

    # Act — warp both centres with the FULL similarity (s*R*x + t).
    wa = result.scale * (rot @ a) + t
    wb = result.scale * (rot @ b) + t

    # Assert — centre-to-centre distance scales by exactly s; the direction angle
    # ROTATES by exactly result.rotation_rad (isotropic scale + proper rotation).
    orig_vec = b - a
    warped_vec = wb - wa
    assert np.hypot(*warped_vec) == pytest.approx(
        result.scale * np.hypot(*orig_vec), rel=1e-9
    )
    orig_angle = np.arctan2(orig_vec[1], orig_vec[0])
    warped_angle = np.arctan2(warped_vec[1], warped_vec[0])
    expected_angle = orig_angle + result.rotation_rad
    # cos of the difference == 1 handles angle wrap robustly.
    assert np.cos(warped_angle - expected_angle) == pytest.approx(1.0, abs=1e-12)


def test_solve_pure_rotation_recovers_angle():
    # Arrange — pure 30° rotation, unit scale, no shift.
    src, dst = make_points_rot(5, scale=1.0, deg=30.0, shift=(0.0, 0.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert
    assert result.scale == pytest.approx(1.0, abs=1e-6)
    assert result.rotation_rad == pytest.approx(np.deg2rad(30.0), abs=1e-6)
    assert result.residual_rms == pytest.approx(0.0, abs=1e-6)


def test_solve_rotation_scale_shift_recovers_all():
    # Arrange — 40° rotation + 1.7 scale + shift, all at once.
    src, dst = make_points_rot(6, scale=1.7, deg=40.0, shift=(25.0, -12.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — every component recovered.
    assert result.scale == pytest.approx(1.7, abs=1e-6)
    assert result.rotation_rad == pytest.approx(np.deg2rad(40.0), abs=1e-6)
    assert result.tx == pytest.approx(25.0, abs=1e-4)
    assert result.ty == pytest.approx(-12.0, abs=1e-4)
    assert result.residual_rms == pytest.approx(0.0, abs=1e-6)


def test_solve_rotation_over_90_keeps_positive_scale():
    # Arrange — 135° rotation: the case that yielded a NEGATIVE scale with the
    # old rotation-free solver (mirrored/tiny section).
    src, dst = make_points_rot(5, scale=0.8, deg=135.0, shift=(10.0, 5.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — scale stays positive; the angle is recovered.
    assert result.scale > 0.0
    assert result.scale == pytest.approx(0.8, abs=1e-6)
    assert result.rotation_rad == pytest.approx(np.deg2rad(135.0), abs=1e-6)


def test_solve_rotation_180_recovers_angle():
    # Arrange — 180° rotation.
    src, dst = make_points_rot(6, scale=1.0, deg=180.0, shift=(0.0, 0.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — angle is ±π (atan2 wraps); scale positive.
    assert result.scale == pytest.approx(1.0, abs=1e-6)
    assert abs(result.rotation_rad) == pytest.approx(np.pi, abs=1e-6)
    assert result.scale > 0.0


def test_solve_mirrored_points_prevents_reflection():
    # Arrange — dst is a genuine REFLECTION of an ASYMMETRIC src (flip across the
    # x-axis about the centroid). A reflection has det = -1 and, unguarded, would
    # corrupt the fit; the solver must return the NEAREST PROPER rotation instead.
    src = np.array(
        [[0.0, 0.0], [120.0, 10.0], [140.0, 80.0], [40.0, 110.0], [-10.0, 50.0]],
        dtype=np.float64,
    )
    centroid = src.mean(axis=0)
    reflect = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.float64)
    dst = (reflect @ (src - centroid).T).T + centroid

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert — scale never goes negative; the recovered transform is a PROPER
    # rotation (det = +1), so warping a triangle preserves its winding (no flip).
    assert result.scale > 0.0
    theta = result.rotation_rad
    rot = np.array(
        [[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]],
        dtype=np.float64,
    )
    tri = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 5.0]], dtype=np.float64)
    warped = (result.scale * (rot @ tri.T)).T
    assert np.sign(_signed_area(warped)) == np.sign(_signed_area(tri)), (
        "reflection must be prevented (triangle winding preserved)"
    )
    assert result.residual_rms > 0.0


def test_solve_result_has_rotation_field():
    # Arrange — an unrotated fit still exposes the field (≈ 0).
    src, dst = make_points(3, scale=1.0, shift=(0.0, 0.0))

    # Act
    result = solve_similarity(src, dst, LENIENT_BASELINE_PX)

    # Assert
    assert hasattr(result, "rotation_rad")
    assert result.rotation_rad == pytest.approx(0.0, abs=1e-9)
