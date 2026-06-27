"""
Pydantic models for Section API.

geometry is a 4-point quad (rotated rectangle), no discriminated union.
no description, no color fields on Section.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Geometry


class SectionGeometry(BaseModel):
    """Polygon [[x,y]×N] in normalised [0,1] coordinates.

    Historically fixed this to a 4-point rotated rectangle. The Floor
    Editor's polygon tool needs richer shapes, so the constraint is relaxed
    to 3–32 vertices. 4-point quads remain valid and the common case.
    All coordinate values must be in [0.0, 1.0].
    """

    points: list[list[float]] = Field(..., min_length=3, max_length=32)

    @field_validator("points")
    @classmethod
    def _bounds(cls, v: list) -> list:
        for pt in v:
            if len(pt) != 2:
                raise ValueError(f"each point must be [x, y], got {pt!r}")
            x, y = pt[0], pt[1]
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(
                    f"each point must have 0 <= x,y <= 1, got [{x}, {y}]"
                )
        return v


# Brief models for embedding


class ReconstructionBrief(BaseModel):
    """Minimal reconstruction info for embedding inside SectionResponse."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    status: int
    preview_url: Optional[str] = None


class SectionBrief(BaseModel):
    """Minimal section info for embedding in reconstruction responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int


# Request models


class SectionPayloadItem(BaseModel):
    """One section item inside a ReplaceSectionsRequest."""

    number: int = Field(..., ge=1)
    geometry: SectionGeometry
    section_type: int = Field(default=1, ge=1, le=10)
    reconstruction_id: Optional[int] = None


class ReplaceSectionsRequest(BaseModel):
    """PUT /api/v1/floors/{floor_id}/sections — atomic replace of all sections."""

    sections: list[SectionPayloadItem] = Field(..., max_length=50)


# Response models


class SectionResponse(BaseModel):
    """Section detail response (GET list + PUT response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    floor_id: int
    number: int
    geometry: Optional[SectionGeometry] = None
    section_type: int = 1
    reconstruction: Optional[ReconstructionBrief] = None
    created_at: datetime
    updated_at: datetime
