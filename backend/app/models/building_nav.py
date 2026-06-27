"""Pydantic IO models for cross-floor routing + link review (subfeature D).

 (the
frontend ``types/buildingNav.ts`` depends on these field names/types). These are
Floor-keyed and DISTINCT from the legacy recon-keyed ``models/floor_transition.py``
(whose ``PathSegment3D`` carries ``reconstruction_id``); the legacy models stay for
the public ``/navigation/multifloor-route`` endpoint.

Note: ``TransitionLink`` here is the API model (carries floor numbers + ``enabled``)
— not the pure ``processing.multifloor_graph.TransitionLink`` dataclass.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class MultifloorRouteRequest(BaseModel):
    """Route request — endpoints on (possibly) different floors."""

    from_floor_id: int
    from_room: str
    to_floor_id: int
    to_room: str


class FloorPathSegment3D(BaseModel):
    """One floor's slice of the route as a 3D polyline (building-frame world)."""

    floor_id: int
    floor_number: int
    coordinates_3d: List[List[float]] = Field(default_factory=list)


class TransitionUsed3D(BaseModel):
    """A stair/elevator hop the route traverses (vertical riser in the world)."""

    type: str  # ``staircase`` | ``elevator``
    from_3d: List[float]
    to_3d: List[float]
    from_floor_id: int
    to_floor_id: int
    # Bare room node ids of the two shaft ends (e.g. ``room_<uuid>``) so the client
    # can highlight the matching stair/lift icon + label its target floor. Default
    # "" keeps older payloads / the same-floor (no-transition) case valid.
    from_node: str = ""
    to_node: str = ""


class MultifloorRouteResponse(BaseModel):
    """Route result. ``status`` ∈ ``success`` | ``no_path`` | ``not_aligned`` (all 200)."""

    status: str
    total_distance_meters: Optional[float] = None
    estimated_time_seconds: Optional[int] = None
    path_segments: List[FloorPathSegment3D] = Field(default_factory=list)
    transitions_used: List[TransitionUsed3D] = Field(default_factory=list)
    message: Optional[str] = None


class TransitionLink(BaseModel):
    """An auto-matched (or forced) cross-floor link, with overrides applied."""

    lower_floor_id: int
    lower_floor_number: int
    lower_node: str
    upper_floor_id: int
    upper_floor_number: int
    upper_node: str
    type: str  # ``staircase`` | ``elevator``
    source: str  # ``auto`` | ``forced``
    enabled: bool
    distance_m: float


class UnmatchedTransition(BaseModel):
    """A transition node the matcher could not pair (operator awareness)."""

    floor_id: int
    floor_number: int
    node: str
    type: str
    reason: str


class TransitionLinksResponse(BaseModel):
    """The link-review payload: links + unmatched, optionally ``not_aligned``."""

    building_id: int
    links: List[TransitionLink] = Field(default_factory=list)
    unmatched: List[UnmatchedTransition] = Field(default_factory=list)
    status: Optional[str] = None


class TransitionOverride(BaseModel):
    """One operator override applied on top of the auto-match."""

    lower_floor_id: int
    lower_node: str
    upper_floor_id: int
    upper_node: str
    action: str  # ``disable`` | ``force``

    @field_validator("action")
    @classmethod
    def _validate_action(cls, value: str) -> str:
        if value not in ("disable", "force"):
            raise ValueError("action must be 'disable' or 'force'")
        return value


class SaveTransitionLinksRequest(BaseModel):
    """Full-replace override set for a building."""

    overrides: List[TransitionOverride] = Field(default_factory=list)


class SaveTransitionLinksResponse(BaseModel):
    """Acknowledge a persisted override set."""

    building_id: int
    overrides_count: int
