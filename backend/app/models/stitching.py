"""
Pydantic модели для склейки планов (stitching)
"""

from typing import List, Optional, Tuple, Literal
from pydantic import BaseModel, Field, field_validator


class TransformInput(BaseModel):
    """Affine transformation parameters."""
    translate_x: float
    translate_y: float
    scale_x: float = Field(gt=0, description="Must be > 0")
    scale_y: float = Field(gt=0, description="Must be > 0")
    rotation_deg: float = Field(ge=0, le=360)


class ClipPolygonInput(BaseModel):
    """Polygon for clipping (subtract operation)."""
    type: Literal["subtract"]
    points: List[Tuple[float, float]] = Field(min_length=3)


class RectCropInput(BaseModel):
    """Rectangular crop in image space."""
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class SourcePlanInput(BaseModel):
    """Single source plan with transformations."""
    reconstruction_id: str
    transform: TransformInput
    clip_polygons: List[ClipPolygonInput]
    rect_crop: Optional[RectCropInput] = None
    image_width_px: int = Field(gt=0)
    image_height_px: int = Field(gt=0)
    z_index: int = Field(ge=0)


class StitchingRequest(BaseModel):
    """Request to stitch multiple plans."""
    name: str = Field(min_length=1, max_length=255)
    building_id: str  # UUID validation can be added via validator
    floor_number: int = Field(ge=0)
    source_plans: List[SourcePlanInput] = Field(min_length=2)

    @field_validator('source_plans')
    @classmethod
    def validate_source_plans_count(cls, v: List[SourcePlanInput]) -> List[SourcePlanInput]:
        """Ensure at least 2 source plans are provided."""
        if len(v) < 2:
            raise ValueError('At least 2 source plans are required for stitching')
        return v


class StitchingResponse(BaseModel):
    """Response after stitching."""
    id: int
    name: str
    status: int
    source_reconstruction_ids: List[int]
    building_id: str
    floor_number: int
    rooms_count: int
    walls_count: int
    warnings: Optional[List[str]] = None
