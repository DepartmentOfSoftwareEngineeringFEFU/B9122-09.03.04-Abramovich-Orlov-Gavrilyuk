"""
Pydantic models for Building API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Forward-declared brief models


class FloorBrief(BaseModel):
    """Minimal floor info for embedding inside BuildingDetailResponse."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int


class SectionPublic(BaseModel):
    """Public section info for published building response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    geometry: Optional[dict] = None
    reconstruction_id: Optional[int] = None
    mesh_url_glb: Optional[str] = None
    section_type: int = 1


class FloorPublic(BaseModel):
    """Public floor info for published building response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    # Normalised [0,1] wall polygons of the floor schema (used by minimap backdrop)
    wall_polygons: Optional[list[list[list[float]]]] = None
    sections: list[SectionPublic] = []


# Request models


class BuildingCreateRequest(BaseModel):
    """POST /api/v1/buildings — create a new building."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=5,
        pattern=r"^[A-Za-z]+$",
        description="Short unique code, e.g. 'D'. Normalised to uppercase.",
    )
    name: str = Field(..., min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=512)

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class BuildingUpdateRequest(BaseModel):
    """PATCH /api/v1/buildings/{id} — update mutable fields only (code is immutable)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = Field(default=None, max_length=512)


# Response models


class BuildingResponse(BaseModel):
    """Standard admin building response (list + detail base)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: Optional[str] = None
    created_at: datetime
    floors_count: int = 0
    published: bool = False


class BuildingDetailResponse(BuildingResponse):
    """GET /api/v1/buildings/{id} — building with floors list."""

    floors: list[FloorBrief] = []


class BuildingPublicResponse(BaseModel):
    """GET /api/v1/buildings?published=true — denormalised public payload."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    floors: list[FloorPublic] = []
