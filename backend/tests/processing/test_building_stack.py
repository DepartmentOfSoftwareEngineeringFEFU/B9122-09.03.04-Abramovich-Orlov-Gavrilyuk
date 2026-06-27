"""Unit tests for the pure floor-placement math (subfeature B).

 ``building_stack``
is the PURE layer: math only, no DB/HTTP/IO/cv2.

The behavioural tests derive GROUND TRUTH independently from the documented coordinate
conventions: a floor-GLB ground point ``(X_s, Z_s)`` → mask px
(``u = X·ppm``, ``v = Z·ppm + H`` — the GLB uses ``Z = (v − H)/ppm`` after trimesh's
Y-up export) → ``building_transform`` (px→px) → reference metre (apply the same map on
the ref). They then assert the ``Placement3D`` (applied the way Three.js applies
``group.scale``/``rotation.y``/``position`` to a child) reproduces that ground truth — so
the rotation sign and the translation terms are actually checked, not echoed.
"""

import ast
import inspect
import math

import pytest

from app.processing.building_stack import Placement3D, floor_placement


# Helpers


def _place(bt, ppm_self=10.0, ppm_ref=10.0, h_self=200, h_ref=200, elev=0.0):
    """Call ``floor_placement`` with readable defaults (keeps lines < 100)."""
    return floor_placement(
        bt,
        ppm_self=ppm_self,
        ppm_ref=ppm_ref,
        mask_h_self=h_self,
        mask_h_ref=h_ref,
        elevation_m=elev,
    )


def _expected_ref_metre(bt, ppm_self, ppm_ref, h_self, h_ref, xs, zs):
    """Ground-truth ref-metre coords of a floor-GLB ground point, from first principles.

    GLB ground frame: ``X = u/ppm``, ``Z = (v − H)/ppm`` (trimesh Y-up negates the row
    axis), so the inverse is ``u = X·ppm``, ``v = Z·ppm + H``.
    """
    s = bt["scale"]
    theta = bt.get("rotation_rad", 0.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    # floor GLB ground -> floor mask px
    px_x = xs * ppm_self
    px_y = zs * ppm_self + h_self
    # building_transform: p_ref = s R(theta) p_self + (tx, ty)
    pxr_x = s * (cos_t * px_x - sin_t * px_y) + bt["tx"]
    pxr_y = s * (sin_t * px_x + cos_t * px_y) + bt["ty"]
    # ref mask px -> ref metre
    return (pxr_x / ppm_ref, (pxr_y - h_ref) / ppm_ref)


def _apply_horizontal(p: Placement3D, xs: float, zs: float):
    """Apply a Placement3D to a ground point the way Three.js does (scale, rot.y, pos).

    Three's ``group.rotation.y = φ`` acts on ``(x, z)`` as
    ``[[cosφ, sinφ], [−sinφ, cosφ]]``.
    """
    cos_t, sin_t = math.cos(p.rotation_y_rad), math.sin(p.rotation_y_rad)
    xr = p.tx + p.scale * (cos_t * xs + sin_t * zs)
    zr = p.tz + p.scale * (-sin_t * xs + cos_t * zs)
    return (xr, zr)


# Tests


def test_placement_reference_is_identity_at_origin():
    """Identity transform + equal ppm/dims + elevation 0 → identity at the origin."""
    bt = {"scale": 1.0, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0}
    p = _place(bt)

    assert p is not None
    assert p.scale == pytest.approx(1.0)
    assert p.rotation_y_rad == pytest.approx(0.0)
    assert p.tx == pytest.approx(0.0)
    assert p.ty == pytest.approx(0.0)
    assert p.tz == pytest.approx(0.0)


def test_placement_sets_y_to_elevation():
    """``ty`` carries the elevation; the horizontal placement stays identity."""
    bt = {"scale": 1.0, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0}
    p = _place(bt, elev=3.0)

    assert p is not None
    assert p.ty == pytest.approx(3.0)
    assert p.tx == pytest.approx(0.0)
    assert p.tz == pytest.approx(0.0)
    assert p.scale == pytest.approx(1.0)


def test_placement_translation_maps_to_metres():
    """A pure pixel translation becomes a metre translation (÷ ppm), no rotation."""
    bt = {"scale": 1.0, "rotation_rad": 0.0, "tx": 50.0, "ty": 30.0}
    p = _place(bt)

    assert p is not None
    assert p.rotation_y_rad == pytest.approx(0.0)
    # tx = (50 - 0)/10 = 5 ; tz = (1*1*200 + 30 - 200)/10 = 3
    assert p.tx == pytest.approx(5.0)
    assert p.tz == pytest.approx(3.0)
    # cross-check a concrete point against first-principles ground truth
    exp = _expected_ref_metre(bt, 10.0, 10.0, 200, 200, xs=4.0, zs=7.0)
    got = _apply_horizontal(p, 4.0, 7.0)
    assert got[0] == pytest.approx(exp[0], abs=1e-9)
    assert got[1] == pytest.approx(exp[1], abs=1e-9)


def test_placement_rotation_maps_to_y_rotation():
    """``rotation_y_rad == −θ`` and a known ground point round-trips to ref metres."""
    bt = {"scale": 1.0, "rotation_rad": math.radians(30.0), "tx": 0.0, "ty": 0.0}
    p = _place(bt)

    assert p is not None
    assert p.rotation_y_rad == pytest.approx(-math.radians(30.0))
    for xs, zs in [(5.0, 8.0), (-3.0, 12.0), (0.0, 0.0)]:
        exp = _expected_ref_metre(bt, 10.0, 10.0, 200, 200, xs, zs)
        got = _apply_horizontal(p, xs, zs)
        assert got[0] == pytest.approx(exp[0], abs=1e-9)
        assert got[1] == pytest.approx(exp[1], abs=1e-9)


def test_placement_scale_combines_transform_and_ppm_ratio():
    """Output scale = transform scale × (ppm_self / ppm_ref)."""
    bt = {"scale": 1.2, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0}
    p = _place(bt, ppm_self=12.0, ppm_ref=10.0)

    assert p is not None
    assert p.scale == pytest.approx(1.2 * 12.0 / 10.0)  # 1.44


def test_placement_handles_unequal_mask_dims():
    """Different self/ref mask heights still align a known point (each H used correctly)."""
    bt = {"scale": 1.0, "rotation_rad": math.radians(15.0), "tx": 12.0, "ty": -8.0}
    p = _place(bt, h_self=150, h_ref=300, elev=6.0)

    assert p is not None
    assert p.ty == pytest.approx(6.0)
    for xs, zs in [(2.0, 3.0), (9.0, -4.0)]:
        exp = _expected_ref_metre(bt, 10.0, 10.0, 150, 300, xs, zs)
        got = _apply_horizontal(p, xs, zs)
        assert got[0] == pytest.approx(exp[0], abs=1e-9)
        assert got[1] == pytest.approx(exp[1], abs=1e-9)


def test_placement_none_transform_returns_none():
    """An unsolved floor (``building_transform is None``) yields no placement."""
    assert _place(None) is None


def test_placement_invalid_ppm_returns_none():
    """Non-positive / non-finite ppm cannot map to metres → None."""
    bt = {"scale": 1.0, "rotation_rad": 0.0, "tx": 0.0, "ty": 0.0}
    assert _place(bt, ppm_ref=0.0) is None
    assert _place(bt, ppm_self=-5.0) is None
    assert _place(bt, ppm_ref=float("inf")) is None
    assert _place(bt, ppm_self=float("nan")) is None


def test_building_stack_module_is_pure():
    """``building_stack`` imports only math/dataclasses/typing — no DB/HTTP/cv2.

    Parse the module AST for IMPORT statements (not raw source — the docstring
    legitimately mentions cv2/numpy/app in prose).
    """
    import app.processing.building_stack as building_stack

    tree = ast.parse(inspect.getsource(building_stack))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    forbidden = {"cv2", "numpy", "np", "app", "fastapi", "sqlalchemy", "pydantic"}
    leaked = imported & forbidden
    assert not leaked, f"building_stack must not import {leaked}; imports = {imported}"
    assert imported <= {"math", "dataclasses", "typing"}, (
        f"building_stack imports beyond math/dataclasses/typing: {imported}"
    )
