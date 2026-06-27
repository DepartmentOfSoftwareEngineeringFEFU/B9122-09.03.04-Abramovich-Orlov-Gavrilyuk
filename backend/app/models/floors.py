"""
Pydantic models for Floor API.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Embedded brief models


class BuildingBrief(BaseModel):
    """Minimal building info for embedding inside floor responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


# Sub-models


class CropBboxModel(BaseModel):
    """Crop/rotation parameters applied to a floor schema image.

    All spatial values are normalised to [0, 1].
    rotation is one of 0 / 90 / 180 / 270 degrees.
    """

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., gt=0.0, le=1.0)
    height: float = Field(..., gt=0.0, le=1.0)
    rotation: int = Field(default=0)

    @field_validator("rotation")
    @classmethod
    def _valid_rotation(cls, v: int) -> int:
        if v not in (0, 90, 180, 270):
            raise ValueError("rotation must be one of 0, 90, 180, 270")
        return v


# Request models


class FloorCreateRequest(BaseModel):
    """POST /api/v1/buildings/{building_id}/floors — create a floor."""

    number: int = Field(..., ge=0, le=50)


class FloorSchemaUpdateRequest(BaseModel):
    """PUT /api/v1/floors/{id}/schema — set schema image + optional crop bbox."""

    schema_image_id: str = Field(..., min_length=1)
    schema_crop_bbox: Optional[CropBboxModel] = None


class FloorWallsUpdateRequest(BaseModel):
    """PUT /api/v1/floors/{id}/walls — save manually edited wall polygons."""

    wall_polygons: list[list[list[float]]]

    @field_validator("wall_polygons")
    @classmethod
    def _validate_polygons(cls, v: list) -> list:
        for poly_idx, poly in enumerate(v):
            if len(poly) < 2:
                raise ValueError(
                    f"polygon[{poly_idx}] must have at least 2 points, got {len(poly)}"
                )
            for pt_idx, pt in enumerate(poly):
                if len(pt) != 2:
                    raise ValueError(
                        f"polygon[{poly_idx}][{pt_idx}] must be [x, y], got {pt}"
                    )
                x, y = pt[0], pt[1]
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise ValueError(
                        f"polygon[{poly_idx}][{pt_idx}] coords must be in [0, 1], got [{x}, {y}]"
                    )
        return v


class FloorMaskUpdateRequest(BaseModel):
    """PUT /api/v1/floors/{id}/mask — link the persisted user-edited wall mask."""

    mask_file_id: str = Field(..., min_length=1)


# Response models


class FloorResponse(BaseModel):
    """Standard floor response used in list and create endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    building_id: int
    number: int
    sections_count: int = 0
    reconstructions_unbound_count: int = 0
    created_at: datetime


class FloorBriefFromFloors(BaseModel):
    """Minimal floor info — used internally for lists embedded in building responses.

    Named separately from buildings.FloorBrief to avoid circular imports.
    Consumers should import directly from this module.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int


class FloorWithBuildingResponse(FloorResponse):
    """GET /api/v1/floors/{id} — floor detail with nested building info + schema fields."""

    building: BuildingBrief
    schema_image_id: Optional[str] = None
    schema_image_url: Optional[str] = None
    schema_crop_bbox: Optional[CropBboxModel] = None
    # [polygons[points[x,y]]] normalised [0,1]
    wall_polygons: Optional[list[list[list[float]]]] = None
    # Persisted user-edited wall mask (wizard step 3) — survives reload
    mask_file_id: Optional[str] = None
    mask_file_url: Optional[str] = None
