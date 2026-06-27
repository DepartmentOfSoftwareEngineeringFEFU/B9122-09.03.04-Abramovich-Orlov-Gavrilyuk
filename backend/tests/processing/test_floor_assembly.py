"""Unit tests for the pure floor mask-assembly module.


plus the non-displacement maths tests
(AC4) that are assertable directly on warp + composite. All tests are pure: only
numpy / cv2, tiny synthetic masks, no DB/IO.
"""

import cv2
import numpy as np
import pytest

from app.processing.floor_assembly import (
    ConnectorRaster,
    CutoutRaster,
    SectionWarpInput,
    assemble_floor_mask,
    compute_canvas_factor,
)
from app.processing.registration import solve_similarity


def tiny_mask(
    shape: tuple[int, int],
    rects: list[tuple[int, int, int, int]],
) -> np.ndarray:
    """Build a small uint8 binary mask with white-filled rectangles.

    Args:
        shape: ``(H, W)`` of the mask (numpy row/col order).
        rects: list of ``(x0, y0, x1, y1)`` inclusive pixel rectangles to fill
            with ``255``. ``x`` is the column, ``y`` is the row.

    Returns:
        ``(H, W)`` uint8 mask with values in ``{0, 255}`` — ``255`` inside any
        rectangle, ``0`` elsewhere.
    """
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    for x0, y0, x1, y1 in rects:
        mask[y0:y1 + 1, x0:x1 + 1] = 255
    return mask


def test_warp_identity_places_mask_at_origin():
    # Arrange — a 4x4 white block in the top-left of a 4x4 mask, identity warp,
    # 8x8 canvas.
    mask = tiny_mask((4, 4), [(0, 0, 3, 3)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )

    # Act
    result = assemble_floor_mask([section], (8, 8), [], default_wall_thickness_px=1)

    # Assert — the block sits at the origin (top-left 4x4), rest is zero.
    assert result.shape == (8, 8)
    assert np.all(result[0:4, 0:4] == 255), "mask must appear top-left"
    assert np.all(result[4:, :] == 0), "rows below the block must be zero"
    assert np.all(result[:, 4:] == 0), "cols right of the block must be zero"


def test_warp_translation_places_mask_offset():
    # Arrange — a 4x4 block, translated by (tx=3, ty=2) on an 8x8 canvas.
    mask = tiny_mask((4, 4), [(0, 0, 3, 3)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.0, tx=3.0, ty=2.0
    )

    # Act
    result = assemble_floor_mask([section], (8, 8), [], default_wall_thickness_px=1)

    # Assert — the white block is shifted by (3, 2): rows 2..5, cols 3..6.
    assert np.all(result[2:6, 3:7] == 255), "block must be shifted by (3, 2)"
    # Everything outside the shifted block is zero.
    outside = result.copy()
    outside[2:6, 3:7] = 0
    assert np.all(outside == 0), "no white outside the shifted block"


def test_warp_uniform_scale_preserves_square():
    # Arrange — a 4x4 square at the origin, scaled by 2 on a 16x16 canvas.
    mask = tiny_mask((4, 4), [(0, 0, 3, 3)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=2.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )

    # Act
    result = assemble_floor_mask([section], (16, 16), [], default_wall_thickness_px=1)

    # Assert — the warped white region is a square (equal width and height).
    ys, xs = np.where(result == 255)
    region_w = xs.max() - xs.min() + 1
    region_h = ys.max() - ys.min() + 1
    assert region_w == region_h, "scaled square must stay square (w == h)"


def test_assemble_composites_two_masks_via_or():
    # Arrange — two overlapping blocks placed on one 10x10 canvas via identity
    # warps. Block A covers cols 0..5, block B cols 3..8; they overlap on 3..5.
    mask_a = tiny_mask((10, 10), [(0, 0, 5, 9)])
    mask_b = tiny_mask((10, 10), [(3, 0, 8, 9)])
    section_a = SectionWarpInput(
        section_id=1, mask=mask_a, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )
    section_b = SectionWarpInput(
        section_id=2, mask=mask_b, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )

    # Act
    result = assemble_floor_mask(
        [section_a, section_b], (10, 10), [], default_wall_thickness_px=1
    )

    # Assert — union of both regions (cols 0..8) is white; the overlap stays 255
    # (binary OR), never doubling to 510.
    assert np.all(result[:, 0:9] == 255), "union of both blocks must be white"
    assert np.all(result[:, 9] == 0), "column outside both blocks stays zero"
    overlap = result[:, 3:6]
    assert np.all(overlap == 255), "overlap stays 255, never sums to 510"
    assert int(result.max()) == 255, "no value exceeds 255 (no overflow)"


def test_assemble_output_is_binary_uint8():
    # Arrange — a scaled section plus a connector; the output must remain binary.
    mask = tiny_mask((6, 6), [(1, 1, 4, 4)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.7, rotation_rad=0.0, tx=2.0, ty=1.0
    )
    connector = ConnectorRaster(
        points_px=np.array([[2, 8], [12, 8]], dtype=np.int32),
        thickness_px=2,
    )

    # Act
    result = assemble_floor_mask(
        [section], (16, 16), [connector], default_wall_thickness_px=2
    )

    # Assert — dtype uint8 and only {0, 255} present (INTER_NEAREST guarantees it).
    assert result.dtype == np.uint8
    assert set(np.unique(result)).issubset({0, 255}), "values must be 0 or 255 only"


def test_assemble_does_not_mutate_input_masks():
    # Arrange — keep byte-exact copies of the inputs (masks and connector points).
    mask_a = tiny_mask((8, 8), [(0, 0, 3, 3)])
    mask_b = tiny_mask((8, 8), [(4, 4, 7, 7)])
    mask_a_copy = mask_a.copy()
    mask_b_copy = mask_b.copy()
    points = np.array([[1, 6], [6, 6]], dtype=np.int32)
    points_copy = points.copy()
    sections = [
        SectionWarpInput(
            section_id=1, mask=mask_a, scale=2.0, rotation_rad=0.0, tx=1.0, ty=1.0
        ),
        SectionWarpInput(
            section_id=2, mask=mask_b, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
        ),
    ]
    connector = ConnectorRaster(points_px=points, thickness_px=2)

    # Act
    assemble_floor_mask(sections, (16, 16), [connector], default_wall_thickness_px=2)

    # Assert — inputs are unchanged (warp writes to fresh arrays; canvas is fresh).
    np.testing.assert_array_equal(mask_a, mask_a_copy)
    np.testing.assert_array_equal(mask_b, mask_b_copy)
    np.testing.assert_array_equal(points, points_copy)


def test_connector_line_drawn_as_wall_band():
    # Arrange — an OPEN L-shaped polyline: (2,2) -> (2,12) -> (12,12). The closing
    # segment (12,12)->(2,2) must NOT be drawn.
    points = np.array([[2, 2], [2, 12], [12, 12]], dtype=np.int32)
    connector = ConnectorRaster(points_px=points, thickness_px=1)

    # Act
    result = assemble_floor_mask([], (16, 16), [connector], default_wall_thickness_px=1)

    # Assert — both drawn segments are present as a white band.
    assert np.any(result == 255), "the connector must draw a wall band"
    # Vertical segment x=2, y in [2,12].
    assert np.all(result[2:13, 2] == 255), "vertical segment must be a band"
    # Horizontal segment y=12, x in [2,12].
    assert np.all(result[12, 2:13] == 255), "horizontal segment must be a band"
    # The diagonal closing segment last->first is NOT drawn: sample an interior
    # point of that diagonal (~(7,7)) and a small neighbourhood around it.
    assert np.all(result[6:9, 6:9] == 0), "no closing segment between last & first"


def test_connector_single_segment_two_points():
    # Arrange — a 2-point connector: a straight horizontal wall band.
    points = np.array([[3, 7], [13, 7]], dtype=np.int32)
    connector = ConnectorRaster(points_px=points, thickness_px=1)

    # Act
    result = assemble_floor_mask([], (16, 16), [connector], default_wall_thickness_px=1)

    # Assert — a straight band between the two endpoints along row 7.
    assert np.all(result[7, 3:14] == 255), "straight band between the two points"
    # No white off the line (rows other than 7 are empty).
    off_line = result.copy()
    off_line[7, :] = 0
    assert np.all(off_line == 0), "no white off the single segment"


def test_canvas_equals_master_crop_dims():
    # Arrange — the pure fn must honour the canvas_size it is handed (fixed
    # sizing, no section-driven upscale). canvas_size is (Wm, Hm).
    master_crop = (24, 13)  # (Wm, Hm)
    mask = tiny_mask((5, 5), [(0, 0, 4, 4)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )

    # Act
    result = assemble_floor_mask(
        [section], master_crop, [], default_wall_thickness_px=1
    )

    # Assert — numpy shape is (Hm, Wm) == (13, 24).
    assert result.shape == (13, 24), "canvas dims must equal the master crop dims"


def test_warp_fully_outside_canvas_contributes_nothing():
    # Arrange — a valid white mask translated far past the canvas border so every
    # warped pixel clips out. borderValue=0 must keep the canvas all-zero. This
    # guards against a future borderValue regression.
    mask = tiny_mask((4, 4), [(0, 0, 3, 3)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.0, tx=100.0, ty=100.0
    )

    # Act
    result = assemble_floor_mask([section], (8, 8), [], default_wall_thickness_px=1)

    # Assert — nothing landed on the canvas.
    assert np.all(result == 0), "fully-out-of-canvas warp must contribute nothing"


def test_assemble_empty_sections_returns_zero_canvas():
    # Arrange — no sections and no connectors.
    # Act
    result = assemble_floor_mask([], (12, 9), [], default_wall_thickness_px=2)

    # Assert — an all-zero canvas of the requested size (numpy (Hm, Wm)).
    assert result.shape == (9, 12)
    assert result.dtype == np.uint8
    assert np.all(result == 0), "empty input must yield an all-zero canvas"


# --- Rotated warp (this feature) ---------------------------------------------


def test_section_warp_input_has_rotation():
    # Arrange / Act — the warp input carries an explicit rotation field.
    mask = tiny_mask((4, 4), [(0, 0, 3, 3)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.5, tx=0.0, ty=0.0
    )

    # Assert
    assert section.rotation_rad == 0.5


def test_assemble_zero_rotation_matches_scale_only():
    # Arrange — an asymmetric mask + a scale+shift transform, rotation_rad=0.
    mask = tiny_mask((8, 8), [(1, 1, 5, 3)])  # asymmetric (wider than tall)
    scale, tx, ty = 1.7, 4.0, 3.0
    canvas_size = (24, 24)  # (Wm, Hm)
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=scale, rotation_rad=0.0, tx=tx, ty=ty
    )

    # Act — the assembler with rotation_rad=0.
    result = assemble_floor_mask(
        [section], canvas_size, [], default_wall_thickness_px=1
    )
    # Expected — the previous scale-only affine, hand-rolled.
    affine = np.array([[scale, 0.0, tx], [0.0, scale, ty]], dtype=np.float64)
    expected = cv2.warpAffine(
        mask, affine, canvas_size, flags=cv2.INTER_NEAREST, borderValue=0
    )

    # Assert — rotation_rad=0 is byte-identical to the old scale-only warp.
    np.testing.assert_array_equal(result, expected)


def test_assemble_rotates_section_mask_90deg():
    # Arrange — a mask wider than tall (occupied bbox 5 wide x 2 tall). After a
    # 90° rotation the occupied bbox must become taller than wide (w/h swap).
    mask = tiny_mask((10, 10), [(1, 1, 5, 2)])  # cols 1..5 (w=5), rows 1..2 (h=2)
    canvas_size = (40, 40)
    # Translate so the rotated mask lands well inside the canvas.
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=np.pi / 2,
        tx=20.0, ty=5.0,
    )

    # Act
    result = assemble_floor_mask(
        [section], canvas_size, [], default_wall_thickness_px=1
    )

    # Assert — something landed, and the occupied bbox is now taller than wide.
    ys, xs = np.where(result == 255)
    assert xs.size > 0, "rotated mask must land on the canvas"
    bbox_w = xs.max() - xs.min() + 1
    bbox_h = ys.max() - ys.min() + 1
    assert bbox_h > bbox_w, "90° rotation must swap the bbox aspect (taller now)"


# --- Non-displacement maths (AC4) --------------------------------------------


def test_uniform_warp_preserves_relative_positions():
    # Arrange — two separate white blocks on one section mask; warp by a uniform
    # (scale, tx, ty) with no rotation. Their centre-to-centre vector must scale
    # by exactly s with the angle unchanged.
    scale, tx, ty = 2.0, 3.0, 5.0
    mask = tiny_mask((20, 20), [(2, 2, 3, 3), (10, 10, 11, 11)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=scale, rotation_rad=0.0, tx=tx, ty=ty
    )
    # Original block centres (x, y): block A ~ (2.5, 2.5), block B ~ (10.5, 10.5).
    centre_a = np.array([2.5, 2.5])
    centre_b = np.array([10.5, 10.5])

    # Act — warp via the assembler; recover the two warped block centres.
    result = assemble_floor_mask([section], (48, 48), [], default_wall_thickness_px=1)
    # Block A region: identify the connected white blob nearest the origin by
    # splitting on a column gap. Simpler: compute warped centres analytically and
    # confirm the mask is white there (the warp is X = s*x + tx, Y = s*y + ty).
    warped_a = scale * centre_a + np.array([tx, ty])
    warped_b = scale * centre_b + np.array([tx, ty])

    # Assert (geometry) — distance scales by s, angle unchanged.
    orig_vec = centre_b - centre_a
    warped_vec = warped_b - warped_a
    assert np.hypot(*warped_vec) == np.hypot(*orig_vec) * scale
    orig_angle = np.arctan2(orig_vec[1], orig_vec[0])
    warped_angle = np.arctan2(warped_vec[1], warped_vec[0])
    assert warped_angle == orig_angle
    # Assert (raster) — the mask is actually white at both warped centres.
    assert result[int(round(warped_a[1])), int(round(warped_a[0]))] == 255
    assert result[int(round(warped_b[1])), int(round(warped_b[0]))] == 255


def test_solve_pixel_space_not_normalized_no_aspect_skew():
    # Arrange — section and master frames with DIFFERENT aspect ratios. Solve the
    # similarity in PIXEL space, then warp a square section mask. If the solve
    # were done in [0,1] normalised space the per-axis factors would differ and
    # the square would shear into a rectangle; pixel-space keeps it square.
    section_w, section_h = 40, 80  # tall section frame
    master_w, master_h = 200, 100  # wide master frame

    # Control points spanning each frame, paired by index. Pure scale+shift maps
    # section-pixel -> master-pixel; we place 3 well-spread, non-coincident pts.
    src = np.array(
        [[5.0, 5.0], [35.0, 5.0], [20.0, 70.0]], dtype=np.float64
    )
    # Apply a KNOWN uniform similarity (scale=2.0, shift=(20, 10)) to build dst,
    # so the recovered transform is exactly isotropic regardless of frame aspect.
    true_scale, true_tx, true_ty = 2.0, 20.0, 10.0
    dst = true_scale * src + np.array([true_tx, true_ty], dtype=np.float64)

    transform = solve_similarity(src, dst, min_baseline_px=1e-6)

    # A square block in the section mask (10x10 px square).
    section_mask = tiny_mask((section_h, section_w), [(5, 5, 14, 14)])
    section = SectionWarpInput(
        section_id=1,
        mask=section_mask,
        scale=transform.scale,
        rotation_rad=transform.rotation_rad,
        tx=transform.tx,
        ty=transform.ty,
    )

    # Act — compose solve -> warp onto the wide master canvas.
    result = assemble_floor_mask(
        [section], (master_w, master_h), [], default_wall_thickness_px=1
    )

    # Assert — the warped block's bounding box is square (w == h). A normalised-
    # space solve would have produced w != h here (aspect skew).
    ys, xs = np.where(result == 255)
    region_w = xs.max() - xs.min() + 1
    region_h = ys.max() - ys.min() + 1
    assert region_w == region_h, "square must stay square in pixel-space solve"
    # Sanity: the recovered scale is the known isotropic value (no skew folded in).
    assert abs(transform.scale - true_scale) < 1e-6


# --- compute_canvas_factor (robust memory-guard k) ---------------------------


def test_compute_canvas_factor_upscales_to_native():
    # A single 0.25× section → k = 1/0.25 = 4 (cap not binding).
    k = compute_canvas_factor(
        [(0.25, 0.0)], long_side_px=500, ppm=10.0,
        max_canvas_px=4000, trust_residual_m=3.0,
    )
    assert k == pytest.approx(4.0)


def test_compute_canvas_factor_excludes_high_residual_section():
    # Good 0.8× (0.5 m residual) + mis-registered 0.18× (36 m) → k from 0.8 only.
    k = compute_canvas_factor(
        [(0.8, 6.0), (0.18, 437.0)], long_side_px=400, ppm=12.0,
        max_canvas_px=4000, trust_residual_m=3.0,
    )
    assert k == pytest.approx(1.25)  # 1/0.8, NOT the bloated 1/0.18 ≈ 5.6


def test_compute_canvas_factor_all_untrusted_uses_all():
    # Every section mis-registered → fall back to all (no worse than un-guarded).
    k = compute_canvas_factor(
        [(0.8, 500.0), (0.18, 600.0)], long_side_px=400, ppm=12.0,
        max_canvas_px=4000, trust_residual_m=3.0,
    )
    assert k == pytest.approx(1.0 / 0.18)  # min(all scales) drives k


def test_compute_canvas_factor_clamped_by_canvas_cap():
    # Upscale 1/0.1 = 10 but the cap 4000/4000 = 1 binds.
    k = compute_canvas_factor(
        [(0.1, 0.0)], long_side_px=4000, ppm=10.0,
        max_canvas_px=4000, trust_residual_m=3.0,
    )
    assert k == pytest.approx(1.0)


def test_compute_canvas_factor_no_sections_returns_one():
    assert compute_canvas_factor([], 500, 10.0, 4000, 3.0) == 1.0


# --- Cutout erase pass (this feature) ----------------------------------------


def test_assemble_cutout_erases_zone_to_zero():
    # A fully-white section; a cutout rectangle erases its interior to 0.
    mask = tiny_mask((10, 10), [(0, 0, 9, 9)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )
    cutout = CutoutRaster(
        points_px=np.array([[2, 2], [6, 2], [6, 6], [2, 6]], dtype=np.int32)
    )
    result = assemble_floor_mask(
        [section], (10, 10), [], default_wall_thickness_px=1, cutouts=[cutout]
    )
    assert np.all(result[3:6, 3:6] == 0), "cutout interior must be erased"
    assert result[0, 0] == 255, "wall outside the cutout remains"


def test_assemble_cutout_overrides_overlapping_connector():
    # A connector wall band crossed by a cutout → the overlapped pixels are 0
    # (the cutout is drawn LAST).
    connector = ConnectorRaster(
        points_px=np.array([[1, 5], [9, 5]], dtype=np.int32), thickness_px=3
    )
    cutout = CutoutRaster(
        points_px=np.array([[3, 3], [7, 3], [7, 7], [3, 7]], dtype=np.int32)
    )
    result = assemble_floor_mask(
        [], (10, 10), [connector], default_wall_thickness_px=3, cutouts=[cutout]
    )
    assert np.all(result[4:7, 4:7] == 0), "cutout erases the overlapping connector"
    assert result[5, 1] == 255, "connector outside the cutout remains a wall"


def test_assemble_no_cutouts_matches_walls_and_connectors():
    # cutouts=None and cutouts=[] are byte-identical to the pre-param behaviour.
    mask = tiny_mask((8, 8), [(1, 1, 5, 5)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.3, rotation_rad=0.0, tx=1.0, ty=1.0
    )
    connector = ConnectorRaster(
        points_px=np.array([[1, 7], [10, 7]], dtype=np.int32), thickness_px=2
    )
    base = assemble_floor_mask(
        [section], (12, 12), [connector], default_wall_thickness_px=2
    )
    none_cut = assemble_floor_mask(
        [section], (12, 12), [connector], default_wall_thickness_px=2, cutouts=None
    )
    empty_cut = assemble_floor_mask(
        [section], (12, 12), [connector], default_wall_thickness_px=2, cutouts=[]
    )
    np.testing.assert_array_equal(base, none_cut)
    np.testing.assert_array_equal(base, empty_cut)


def test_assemble_cutout_clipped_to_canvas():
    # A polygon extending past the canvas fills only the in-bounds part, no error.
    mask = tiny_mask((10, 10), [(0, 0, 9, 9)])
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )
    cutout = CutoutRaster(
        points_px=np.array([[5, 5], [50, 5], [50, 50], [5, 50]], dtype=np.int32)
    )
    result = assemble_floor_mask(
        [section], (10, 10), [], default_wall_thickness_px=1, cutouts=[cutout]
    )
    assert result.shape == (10, 10)
    assert np.all(result[6:10, 6:10] == 0), "in-bounds part of the polygon erased"
    assert result[0, 0] == 255, "outside the polygon stays a wall"


def test_assemble_cutouts_do_not_mutate_inputs():
    # The section mask and the cutout point array are unchanged after the call.
    mask = tiny_mask((8, 8), [(0, 0, 7, 7)])
    mask_copy = mask.copy()
    section = SectionWarpInput(
        section_id=1, mask=mask, scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0
    )
    points = np.array([[1, 1], [5, 1], [5, 5], [1, 5]], dtype=np.int32)
    points_copy = points.copy()
    cutout = CutoutRaster(points_px=points)
    assemble_floor_mask(
        [section], (8, 8), [], default_wall_thickness_px=1, cutouts=[cutout]
    )
    np.testing.assert_array_equal(mask, mask_copy)
    np.testing.assert_array_equal(points, points_copy)
