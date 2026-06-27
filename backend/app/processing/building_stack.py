"""Pure floor-placement math for the stacked 3D building viewer (subfeature B).

Turns subfeature A's per-floor ``building_transform`` — a 2D similarity in WALL-MASK
PIXELS mapping THIS floor's mask px → the REFERENCE (lowest) floor's mask px — into a
3D ``Placement3D`` that positions the floor's GLB in the building (reference-floor)
METRIC world frame. The frontend applies it directly as ``group.scale`` /
``group.rotation.y`` / ``group.position``.

Derivation + worked identity check:

NOTE: ``processing/`` is the PURE layer. This module imports ONLY ``math``,
``dataclasses`` and ``typing`` — a purity test asserts no ``cv2`` / ``numpy`` /
``app.*`` / ``fastapi`` / ``sqlalchemy`` / ``pydantic`` import.

Coordinate conventions (see 06):

- ``building_transform`` (A): ``p_ref = s·R(θ)·p_self + (tx_px, ty_px)`` with
  ``R(θ) = [[cosθ, -sinθ], [sinθ, cosθ]]``, in wall-mask pixels; lowest floor =
  identity; ``None`` = unsolved.
- GLB ground frame (MEASURED from the exported floor GLBs): a mask pixel ``(u, v)``
  maps to metric ground ``X = u/ppm``, ``Z = (v - H)/ppm`` — trimesh's Y-up export
  NEGATES the OpenCV row axis, so ``Z`` carries ``(v - H)``, NOT ``(H - v)``. Height
  is Three's Y axis. World frame = the reference floor's GLB frame.
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Placement3D:
    """A floor GLB's placement in the building (reference-floor) metric world frame.

    Applied frontend-side as ``group.scale = scale``;
    ``group.rotation.y = rotation_y_rad``; ``group.position = (tx, ty, tz)``.
    Three.js is Y-up with the ground in the X-Z plane; all values are metres
    (``scale`` is dimensionless).

    Attributes:
        scale: uniform scale (combined transform scale × ppm ratio).
        rotation_y_rad: rotation about the vertical (Y) axis, radians.
        tx: world X translation (metres).
        ty: world Y translation (metres) — the floor's elevation.
        tz: world Z translation (metres).
    """

    scale: float
    rotation_y_rad: float
    tx: float
    ty: float
    tz: float


def floor_placement(
    building_transform: Optional[dict],
    ppm_self: float,
    ppm_ref: float,
    mask_h_self: int,
    mask_h_ref: int,
    elevation_m: float,
) -> Optional[Placement3D]:
    """Convert a floor's ``building_transform`` (px) into a 3D ``Placement3D`` (m).

    Closed form, with ``s = building_transform["scale"]`` (the RAW
    pixel→pixel scale, NOT the combined output ``σ``), ``θ = rotation_rad``::

        σ              = s · ppm_self / ppm_ref          # output .scale
        rotation_y_rad = −θ
        tx             = (tx_px − s·sinθ·H_self) / ppm_ref
        tz             = (s·cosθ·H_self + ty_px − H_ref) / ppm_ref
        ty             = elevation_m

    The floor GLB's ground maps mask px ``(u, v)`` → ``(X, Z) = (u/ppm, (v − H)/ppm)``:
    trimesh's Y-up export negates the OpenCV row axis, so ``Z`` is ``(v − H)``, NOT
    ``(H − v)``. That negated row axis is why the building-frame rotation is
    ``group.rotation.y = −θ`` (Three's Y rotation acts as ``[[cosφ, sinφ], [−sinφ,
    cosφ]]`` on ``(x, z)``; with ``φ = −θ`` it reproduces A's ``R(θ)`` after the flip).

    Args:
        building_transform: A's persisted transform dict
            (``{scale, rotation_rad, tx, ty, ...}``) in mask pixels, or ``None``
            for an unsolved/unlinked floor.
        ppm_self: this floor's pixels-per-metre.
        ppm_ref: the reference floor's pixels-per-metre.
        mask_h_self: this floor's wall-mask height in pixels (``H_self``).
        mask_h_ref: the reference floor's wall-mask height in pixels (``H_ref``).
        elevation_m: ``(number − min_number) × FLOOR_HEIGHT`` — the floor's height.

    Returns:
        A ``Placement3D`` in the reference-floor metric world frame, or ``None`` when
        the floor is unsolved (``building_transform is None``) or the metric scales
        are unusable (``ppm_self``/``ppm_ref`` non-finite or ``<= 0``) so the px→m
        conversion cannot be done.
    """
    if building_transform is None:
        return None
    if not (math.isfinite(ppm_self) and math.isfinite(ppm_ref)):
        return None
    if ppm_self <= 0.0 or ppm_ref <= 0.0:
        return None

    s = float(building_transform["scale"])
    theta = float(building_transform.get("rotation_rad", 0.0))
    tx_px = float(building_transform["tx"])
    ty_px = float(building_transform["ty"])

    sin_t = math.sin(theta)
    cos_t = math.cos(theta)

    scale = s * ppm_self / ppm_ref
    tx = (tx_px - s * sin_t * mask_h_self) / ppm_ref
    tz = (s * cos_t * mask_h_self + ty_px - mask_h_ref) / ppm_ref

    return Placement3D(
        scale=scale,
        rotation_y_rad=-theta,
        tx=tx,
        ty=elevation_m,
        tz=tz,
    )
