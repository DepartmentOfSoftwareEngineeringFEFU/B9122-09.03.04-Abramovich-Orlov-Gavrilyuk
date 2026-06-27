"""
Pydantic models for floor transitions CRUD and multifloor route API.
"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class FloorTransitionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    from_reconstruction_id: int
    from_geometry: list[list[float]] | None = None
    from_x: float = Field(ge=0.0, le=1.0)
    from_y: float = Field(ge=0.0, le=1.0)
    to_reconstruction_id: int
    to_geometry: list[list[float]] | None = None
    to_x: float = Field(ge=0.0, le=1.0)
    to_y: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_different_reconstructions(self) -> "FloorTransitionRequest":
        if self.from_reconstruction_id == self.to_reconstruction_id:
            raise ValueError("Cannot create transition within same reconstruction")
        return self


class FloorTransitionResponse(BaseModel):
    id: int
    name: str
    building_id: str | None
    from_reconstruction_id: int
    from_geometry: list[list[float]] | None = None
    from_x: float
    from_y: float
    to_reconstruction_id: int
    to_geometry: list[list[float]] | None = None
    to_x: float
    to_y: float
    created_at: datetime

    model_config = {"from_attributes": True}


class PathSegment3D(BaseModel):
    reconstruction_id: int
    floor_number: int
    floor_name: str
    coordinates_3d: list[list[float]]  # [[x, y, z], ...]


class TransitionUsed3D(BaseModel):
    name: str
    from_3d: list[float]  # [x, y, z]
    to_3d: list[float]    # [x, y, z]


class Room3DInfo(BaseModel):
    position: list[float]  # [x, y, z]
    size: list[float]      # [w, h, d]


class MultifloorRouteRequest(BaseModel):
    building_id: str
    from_reconstruction_id: int
    from_room_id: str
    to_reconstruction_id: int
    to_room_id: str


class MultifloorRouteResponse(BaseModel):
    status: str  # "success" | "no_path" | "error"
    total_distance_meters: float | None = None
    estimated_time_seconds: int | None = None
    path_segments: list[PathSegment3D] = []
    transitions_used: list[TransitionUsed3D] = []
    from_room_3d: Room3DInfo | None = None
    to_room_3d: Room3DInfo | None = None
    message: str | None = None
