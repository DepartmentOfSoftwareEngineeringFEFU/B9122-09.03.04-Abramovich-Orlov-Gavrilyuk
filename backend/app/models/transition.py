"""
Transition API and domain models.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TransitionType = Literal["passage", "stairs", "elevator"]
RouteStatus = Literal["success", "no_path", "error"]


class TransitionGroupCreate(BaseModel):
    building_id: str | None = None
    type: TransitionType = "passage"
    label: str | None = None
    target_hint_building_id: str | None = None
    target_hint_floor_number: int | None = None


class TransitionGroupUpdate(BaseModel):
    type: TransitionType | None = None
    label: str | None = None
    target_hint_building_id: str | None = None
    target_hint_floor_number: int | None = None


class TransitionGroupResponse(BaseModel):
    id: int
    building_id: str | None
    type: TransitionType
    label: str | None
    target_hint_building_id: str | None = None
    target_hint_floor_number: int | None = None
    point_ids: list[int] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransitionPointCreate(BaseModel):
    reconstruction_id: int
    group_id: int
    position_x: float = Field(ge=0.0, le=1.0)
    position_y: float = Field(ge=0.0, le=1.0)
    geometry: list[list[float]] | None = None
    label: str | None = None


class TransitionPointUpdate(BaseModel):
    position_x: float | None = Field(default=None, ge=0.0, le=1.0)
    position_y: float | None = Field(default=None, ge=0.0, le=1.0)
    geometry: list[list[float]] | None = None
    label: str | None = None


class TransitionPointResponse(BaseModel):
    id: int
    reconstruction_id: int
    group_id: int
    position_x: float
    position_y: float
    geometry: list[list[float]] | None = None
    label: str | None
    snapped_node_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RouteSegment(BaseModel):
    reconstruction_id: int
    reconstruction_name: str | None = None
    floor_label: str | None = None
    coordinates: list[list[float]] = Field(default_factory=list)
    transition_out_point_id: int | None = None


class MultiPlanRouteRequest(BaseModel):
    from_reconstruction_id: int
    from_room_id: str
    to_reconstruction_id: int
    to_room_id: str


class MultiPlanRouteResponse(BaseModel):
    status: RouteStatus
    message: str | None = None
    total_distance_meters: float | None = None
    segments: list[RouteSegment] = Field(default_factory=list)
