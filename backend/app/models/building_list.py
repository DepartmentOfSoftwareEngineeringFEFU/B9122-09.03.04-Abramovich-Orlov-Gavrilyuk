"""
Pydantic models for building listing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FloorListItem(BaseModel):
    number: int
    reconstruction_id: int
    reconstruction_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class BuildingListItem(BaseModel):
    id: str
    name: str
    floors: list[FloorListItem] = []

    model_config = ConfigDict(from_attributes=True)
