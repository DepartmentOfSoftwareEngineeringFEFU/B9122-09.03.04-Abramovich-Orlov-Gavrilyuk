"""Unit tests for the pure similarity-chain composition (subfeature A).


processing.floor_stack". ``floor_stack`` is the PURE composition layer: math
only, no DB/HTTP/IO. The unequal-mask-dims test wires it to the real
``solve_similarity`` solver to prove the composition handles per-pair transforms
derived from differently-sized synthetic masks ("не перепутать размеры").
"""

import inspect
import math

import numpy as np

from app.processing.floor_stack import (
    SimilarityT,
    compose,
    compose_chain_transforms,
    identity,
)
from app.processing.registration import solve_similarity

LENIENT_BASELINE_PX = 1e-6


def _assert_t_close(a: SimilarityT, b: SimilarityT, tol: float = 1e-9) -> None:
    """Assert two ``SimilarityT`` are equal within ``tol`` on every field."""
    assert math.isclose(a.scale, b.scale, abs_tol=tol), f"scale {a.scale} vs {b.scale}"
    assert math.isclose(
        a.rotation_rad, b.rotation_rad, abs_tol=tol
    ), f"rot {a.rotation_rad} vs {b.rotation_rad}"
    assert math.isclose(a.tx, b.tx, abs_tol=tol), f"tx {a.tx} vs {b.tx}"
    assert math.isclose(a.ty, b.ty, abs_tol=tol), f"ty {a.ty} vs {b.ty}"


def test_compose_reference_floor_is_identity():
    """Floor 0 (the reference) always maps to the identity transform."""
    pair = SimilarityT(scale=0.9, rotation_rad=0.1, tx=5.0, ty=-3.0)
    result = compose_chain_transforms([pair], n_floors=2)

    assert result[0] == identity()
    assert result[0].scale == 1.0
    assert result[0].rotation_rad == 0.0
    assert result[0].tx == 0.0
    assert result[0].ty == 0.0


def test_compose_single_pair_equals_pair_transform():
    """With one pair, floor 1's building transform IS that pair transform.

    ``T[1] = compose(identity, pair) == pair`` because the reference is identity.
    """
    pair = SimilarityT(scale=0.98, rotation_rad=0.0123, tx=14.2, ty=-7.5)
    result = compose_chain_transforms([pair], n_floors=2)

    assert result[1] is not None
    _assert_t_close(result[1], pair)


def test_compose_three_floor_chain_accumulates():
    """A 3-floor chain round-trips a known point up to the reference frame.

    ``pair_transforms = [T(1->0), T(2->1)]``. The composed ``T[2]`` must equal
    ``compose(T(1->0), T(2->1))`` and map a floor-2 point to the same place as
    applying the two pair transforms in sequence (floor 2 → floor 1 → floor 0).
    """
    t10 = SimilarityT(scale=1.1, rotation_rad=0.2, tx=3.0, ty=4.0)
    t21 = SimilarityT(scale=0.9, rotation_rad=-0.05, tx=-2.0, ty=1.5)

    result = compose_chain_transforms([t10, t21], n_floors=3)

    assert result[0] == identity()
    _assert_t_close(result[1], t10)
    expected_t2 = compose(t10, t21)
    _assert_t_close(result[2], expected_t2)

    # Behavioural check: a floor-2 point mapped by T[2] equals manually chaining.
    px, py = 17.0, -9.0
    via_chain = t10.apply(*t21.apply(px, py))
    via_composed = result[2].apply(px, py)
    assert math.isclose(via_composed[0], via_chain[0], abs_tol=1e-9)
    assert math.isclose(via_composed[1], via_chain[1], abs_tol=1e-9)


def test_compose_handles_unequal_mask_dims():
    """Pair transforms solved from differently-sized masks compose correctly.

    Build three synthetic floors with DIFFERENT wall-mask pixel dims and known
    per-floor transforms to the reference (building) frame. Project a shared set
    of building-frame anchor points onto each floor's OWN pixel grid, recover the
    adjacent-pair upper→lower transforms with ``solve_similarity`` (exactly what
    the service does), compose, and assert a floor-2 point maps onto the reference
    floor's pixels — never assuming equal mask sizes.
    """
    # Per-floor transform to the reference (floor 0) pixel frame. Floor 0 is
    # identity by construction. These are the GROUND TRUTH the chain must recover.
    f0 = identity()
    f1 = SimilarityT(scale=1.2, rotation_rad=math.radians(8.0), tx=40.0, ty=-25.0)
    f2 = SimilarityT(scale=0.85, rotation_rad=math.radians(-12.0), tx=-18.0, ty=33.0)
    floor_to_ref = [f0, f1, f2]

    # Shared anchor points expressed in the REFERENCE pixel frame.
    ref_pts = np.array(
        [[100.0, 120.0], [400.0, 150.0], [250.0, 500.0], [120.0, 460.0]],
        dtype=np.float64,
    )

    # Each floor's own pixel coords = inverse(floor_to_ref) applied to ref_pts.
    def _ref_to_floor(t: SimilarityT, pts: np.ndarray) -> np.ndarray:
        cos_t = math.cos(t.rotation_rad)
        sin_t = math.sin(t.rotation_rad)
        rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]], dtype=np.float64)
        # p_ref = s R p_floor + ttt  =>  p_floor = (1/s) R^-1 (p_ref - tt)
        shifted = pts - np.array([t.tx, t.ty])
        return (shifted @ rot) / t.scale  # rot.T == inverse rotation

    floor_pts = [_ref_to_floor(t, ref_pts) for t in floor_to_ref]

    # Recover each ADJACENT pair's upper->lower transform from its OWN points.
    # pair (0,1): src = floor1 px, dst = floor0 px  -> T(1->0)
    # pair (1,2): src = floor2 px, dst = floor1 px  -> T(2->1)
    res_10 = solve_similarity(floor_pts[1], floor_pts[0], LENIENT_BASELINE_PX)
    res_21 = solve_similarity(floor_pts[2], floor_pts[1], LENIENT_BASELINE_PX)
    pair_10 = SimilarityT(
        scale=res_10.scale,
        rotation_rad=res_10.rotation_rad,
        tx=res_10.tx,
        ty=res_10.ty,
    )
    pair_21 = SimilarityT(
        scale=res_21.scale,
        rotation_rad=res_21.rotation_rad,
        tx=res_21.tx,
        ty=res_21.ty,
    )

    composed = compose_chain_transforms([pair_10, pair_21], n_floors=3)

    # Floor 2's composed transform must map its own pixels onto the reference px.
    assert composed[2] is not None
    for i in range(len(ref_pts)):
        fx, fy = floor_pts[2][i]
        mapped = composed[2].apply(fx, fy)
        assert math.isclose(mapped[0], ref_pts[i][0], abs_tol=1e-4)
        assert math.isclose(mapped[1], ref_pts[i][1], abs_tol=1e-4)

    # Sanity: the recovered transforms match the ground truth too.
    _assert_t_close(composed[1], f1, tol=1e-4)
    _assert_t_close(composed[2], f2, tol=1e-4)


def test_compose_stops_at_chain_break():
    """A middle ``None`` pair leaves that floor AND every floor above it ``None``.

    Floors: [0, 1, 2, 3]. pair_transforms = [T(1->0), None, T(3->2)]. The break at
    pair (1,2) means floors 2 and 3 cannot reach the reference → both ``None``.
    """
    t10 = SimilarityT(scale=1.0, rotation_rad=0.0, tx=2.0, ty=2.0)
    t32 = SimilarityT(scale=1.0, rotation_rad=0.0, tx=9.0, ty=9.0)

    result = compose_chain_transforms([t10, None, t32], n_floors=4)

    assert result[0] == identity()
    assert result[1] is not None
    _assert_t_close(result[1], t10)
    assert result[2] is None, "floor at the break has no building transform"
    assert result[3] is None, "floor above the break is also unreachable"


def test_compose_single_floor_identity_only():
    """A 1-floor building has no pairs; floor 0 is identity, nothing else."""
    result = compose_chain_transforms([], n_floors=1)

    assert len(result) == 1
    assert result[0] == identity()


def test_compose_is_associative_on_three_links():
    """``compose`` is associative: (a∘b)∘c == a∘(b∘c) on a 3-link chain."""
    a = SimilarityT(scale=1.3, rotation_rad=0.3, tx=1.0, ty=2.0)
    b = SimilarityT(scale=0.7, rotation_rad=-0.4, tx=3.0, ty=-1.0)
    c = SimilarityT(scale=1.1, rotation_rad=0.15, tx=-2.0, ty=5.0)

    left = compose(compose(a, b), c)
    right = compose(a, compose(b, c))
    _assert_t_close(left, right)


def test_floor_stack_module_is_pure():
    """``floor_stack`` imports only math/dataclasses/typing — no DB/HTTP/cv2.

    Parse the module's AST for its IMPORT statements (not raw source — the
    docstring legitimately mentions "no DB / app.db" in prose). The pure
    ``processing`` layer must never import the DB, API, services, FastAPI, OpenCV,
    numpy, SQLAlchemy or Pydantic.
    """
    import ast

    import app.processing.floor_stack as floor_stack

    tree = ast.parse(inspect.getsource(floor_stack))
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
    assert not leaked, f"floor_stack must not import {leaked}; imports = {imported}"
    # Positive check: only the three allowed stdlib modules.
    assert imported <= {"math", "dataclasses", "typing"}, (
        f"floor_stack imports beyond math/dataclasses/typing: {imported}"
    )
