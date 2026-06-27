"""Typed vector payloads for edit-plan restore/save."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class VectorPoint(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class VectorRoom(BaseModel):
    id: str
    name: str = ""
    room_type: str = "room"
    center: VectorPoint
    polygon: list[VectorPoint]
    area_normalized: float = Field(..., ge=0.0)
    # Inter-floor link data for elevators (см. floor-transition-tools).
    # Old documents without these keys load with defaults (None / []).
    floor_from: Optional[int] = None
    floor_to: Optional[int] = None
    floors_excluded: list[int] = Field(default_factory=list)
    # Stair directional gates (multifloor-routing, subfeature D). Round-trip with
    # ``Room``; old documents without these keys load with True defaults.
    connects_up: bool = True
    connects_down: bool = True

    @model_validator(mode="after")
    def _validate_floor_range(self) -> "VectorRoom":
        if self.floor_from is None and self.floor_to is None:
            return self
        if self.floor_from is None or self.floor_to is None:
            raise ValueError(
                "elevator floor range invalid: both floor_from and "
                "floor_to must be set"
            )
        if self.floor_from < 1 or self.floor_to < 1:
            raise ValueError(
                "elevator floor range invalid: floors must be >= 1"
            )
        if self.floor_from > self.floor_to:
            raise ValueError(
                "elevator floor range invalid: floor_from "
                f"({self.floor_from}) > floor_to ({self.floor_to})"
            )
        for v in self.floors_excluded:
            if v < self.floor_from or v > self.floor_to:
                raise ValueError(
                    "elevator floor range invalid: excluded floor "
                    f"{v} outside [{self.floor_from}, {self.floor_to}]"
                )
        return self


class VectorDoor(BaseModel):
    id: str
    position: VectorPoint
    width: float = Field(..., ge=0.0)
    connects: list[str] = Field(default_factory=list)


class VectorizationResult(BaseModel):
    walls: list[dict] = Field(default_factory=list)
    rooms: list[VectorRoom] = Field(default_factory=list)
    doors: list[VectorDoor] = Field(default_factory=list)
    text_blocks: list[dict] = Field(default_factory=list)
    image_size_original: tuple[int, int] = (0, 0)
    image_size_cropped: tuple[int, int] = (0, 0)
    crop_rect: Optional[dict] = None
    crop_applied: bool = False
    rotation_angle: int = 0
    wall_thickness_px: float = 0.0
    estimated_pixels_per_meter: float = 0.0
    rooms_with_names: int = 0
    corridors_count: int = 0
    doors_count: int = 0
    model_config = {"extra": "ignore"}
