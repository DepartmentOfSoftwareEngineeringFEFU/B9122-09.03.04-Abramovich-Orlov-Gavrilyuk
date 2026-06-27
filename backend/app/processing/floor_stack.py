"""Pure similarity-chain composition for vertical floor stitching (subfeature A).

Given per-pair similarity transforms (upper floor → lower floor) ordered
bottom-up, accumulate the chain into each floor's transform to the BUILDING
FRAME (the lowest floor = identity). This is exact similarity algebra — no DB,
no HTTP, no IO, no OpenCV, no numpy. The SERVICE de-normalises each
pair's control points by THAT floor's own wall-mask pixel dims and runs
``processing.registration.solve_similarity`` to obtain the per-pair transforms;
this module only composes them.

NOTE: ``processing/`` is the PURE layer. This module imports ONLY ``math``,
``dataclasses`` and ``typing`` — there is a purity test that asserts no
``cv2`` / ``app.db`` / ``app.api`` / ``app.services`` / ``fastapi`` import.

A similarity maps a point ``p = (x, y)`` as::

    T(p) = scale * R(rotation_rad) @ p + (tx, ty)

with ``R(theta) = [[cos, -sin], [sin, cos]]`` — the SAME convention as
``processing.registration.SimilarityResult`` (so a pair transform produced by
the solver drops straight in here).
"""

import math
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SimilarityT:
    """A 2D similarity transform ``T(p) = scale * R(rotation_rad) @ p + (tx, ty)``.

    Immutable value object (the unit of composition). ``rotation_rad`` follows the
    standard CCW convention ``R = [[cos, -sin], [sin, cos]]``; the same convention
    ``processing.registration`` produces, so a solved pair transform composes
    here without any axis flip.

    Attributes:
        scale: isotropic scale factor (same on both axes).
        rotation_rad: rotation angle in radians.
        tx: translation in x.
        ty: translation in y.
    """

    scale: float
    rotation_rad: float
    tx: float
    ty: float

    def apply(self, x: float, y: float) -> tuple[float, float]:
        """Map a single point ``(x, y)`` through this similarity.

        Pure helper used by tests to verify the composed chain round-trips a
        known point onto the reference frame.
        """
        cos_t = math.cos(self.rotation_rad)
        sin_t = math.sin(self.rotation_rad)
        rx = cos_t * x - sin_t * y
        ry = sin_t * x + cos_t * y
        return (self.scale * rx + self.tx, self.scale * ry + self.ty)


def identity() -> SimilarityT:
    """The identity similarity (``scale=1, rotation_rad=0, tx=0, ty=0``)."""
    return SimilarityT(scale=1.0, rotation_rad=0.0, tx=0.0, ty=0.0)


def compose(a: SimilarityT, b: SimilarityT) -> SimilarityT:
    """Compose two similarities so the result applies ``b`` THEN ``a``.

    The returned transform ``c`` satisfies ``c(p) == a(b(p))`` for every point
    ``p`` (matrix product of the two similarities). Concretely::

        scale = a.scale * b.scale
        rotation_rad = a.rotation_rad + b.rotation_rad
        (tx, ty) = a.scale * R(a.rotation_rad) @ (b.tx, b.ty) + (a.tx, a.ty)

    Args:
        a: the OUTER transform (applied second).
        b: the INNER transform (applied first).

    Returns:
        A new ``SimilarityT`` equal to ``a ∘ b``.
    """
    cos_a = math.cos(a.rotation_rad)
    sin_a = math.sin(a.rotation_rad)
    # a.scale * R(a.rot) @ (b.tx, b.ty)
    rotated_tx = cos_a * b.tx - sin_a * b.ty
    rotated_ty = sin_a * b.tx + cos_a * b.ty
    tx = a.scale * rotated_tx + a.tx
    ty = a.scale * rotated_ty + a.ty
    return SimilarityT(
        scale=a.scale * b.scale,
        rotation_rad=a.rotation_rad + b.rotation_rad,
        tx=tx,
        ty=ty,
    )


def compose_chain_transforms(
    pair_transforms: List[Optional[SimilarityT]],
    n_floors: int,
) -> List[Optional[SimilarityT]]:
    """Accumulate per-pair transforms into per-floor building-frame transforms.

    ``pair_transforms[i]`` is the similarity mapping **floor ``i+1``'s pixels →
    floor ``i``'s pixels** (the upper→lower transform for the adjacent pair
    ``(i, i+1)``), or ``None`` when that pair is unlinked. Floors are ordered
    bottom-up, so ``len(pair_transforms) == n_floors - 1``.

    Returns a list of length ``n_floors`` where entry ``k`` is floor ``k``'s
    transform to the BUILDING FRAME (the lowest floor = the reference):

    - ``T[0] = identity()`` (reference frame).
    - ``T[k] = compose(T[k-1], pair_transforms[k-1])`` — chains the point up the
      stack: floor ``k`` → floor ``k-1`` → ... → floor ``0``.
    - On the FIRST ``None`` pair the chain BREAKS: that floor and every floor
      above it get ``None`` (they cannot be expressed in the reference frame).

    Args:
        pair_transforms: per-adjacent-pair upper→lower transforms (or ``None``),
            ordered bottom-up. Length must be ``n_floors - 1``.
        n_floors: number of floors in the building (>= 1).

    Returns:
        A list of ``Optional[SimilarityT]`` of length ``n_floors``; index ``k``
        maps floor ``k``'s pixels to the reference floor's pixels (or ``None`` if
        unreachable from the reference through a contiguous linked run).

    Raises:
        ValueError: if ``n_floors < 1`` or ``len(pair_transforms) != n_floors - 1``.
    """
    if n_floors < 1:
        raise ValueError(f"n_floors must be >= 1, got {n_floors}")
    if len(pair_transforms) != n_floors - 1:
        raise ValueError(
            f"expected {n_floors - 1} pair transforms for {n_floors} floors, "
            f"got {len(pair_transforms)}"
        )

    result: List[Optional[SimilarityT]] = [None] * n_floors
    result[0] = identity()

    for k in range(1, n_floors):
        prev = result[k - 1]
        pair = pair_transforms[k - 1]
        # Chain break: a missing pair (or a floor already cut off below) leaves
        # this floor — and, since ``prev`` stays ``None``, every floor above —
        # without a building-frame transform.
        if prev is None or pair is None:
            result[k] = None
            continue
        result[k] = compose(prev, pair)

    return result
