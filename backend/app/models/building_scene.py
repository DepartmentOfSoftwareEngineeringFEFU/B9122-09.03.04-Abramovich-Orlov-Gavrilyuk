"""Pydantic models for the stacked 3D building viewer (subfeature B).

These models ARE the contract — the ``GET /buildings/{id}/scene-3d`` response
serialises through them. Pure declarations only; no business logic.

``ScenePlacement`` is the metric, Three.js-ready transform the frontend applies as
``group.scale`` / ``group.rotation.y`` / ``group.position``. It is derived from
subfeature A's ``building_transform`` by the PURE ``processing.building_stack.floor_placement`` —
these models never recompute it.
"""

from typing import Optional

from pydantic import BaseModel


class ScenePlacement(BaseModel):
    """A floor GLB's placement in the building (reference-floor) metric world frame.

    Applied frontend-side as ``group.scale = scale``;
    ``group.rotation.y = rotation_y_rad``; ``group.position = (tx, ty, tz)``. Metres,
    Three.js Y-up with the ground in the X-Z plane. ``ty`` equals the floor's
    ``elevation_m``.
    """

    scale: float
    rotation_y_rad: float
    tx: float
    ty: float
    tz: float


class SceneFloor(BaseModel):
    """One floor in the 3D scene.

    ``has_mesh`` / ``mesh_url`` reflect ``Floor.mesh_file_glb`` (the assembled floor GLB);
    ``placement`` is ``None`` for an unsolved/unlinked floor (skipped in the scene, labelled
    in the side list). The reference (lowest) floor always gets an identity placement.
    """

    floor_id: int
    number: int
    elevation_m: float
    has_mesh: bool
    mesh_url: Optional[str] = None
    placement: Optional[ScenePlacement] = None


class BuildingScene3DResponse(BaseModel):
    """GET /buildings/{building_id}/scene-3d — the stacked 3D scene payload.

    ``reference_floor_id`` is the lowest floor (the world-frame origin), ``None`` when the
    building has no floors. ``floor_height_m`` echoes ``FLOOR_HEIGHT`` so the frontend never
    hardcodes it. ``floors`` is ordered by ``number`` ASC.
    """

    building_id: int
    reference_floor_id: Optional[int] = None
    floor_height_m: float
    floors: list[SceneFloor]
