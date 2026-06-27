"""
Pydantic модели для зданий и этажей
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class BuildingBase(BaseModel):
    """Базовая модель здания"""
    name: str = Field(..., min_length=1, max_length=100)


class BuildingCreate(BuildingBase):
    """Создание здания"""
    pass


class BuildingResponse(BuildingBase):
    """Ответ с данными здания"""
    id: int
    floors: List[int] = []  # Список ID этажей
    created_at: datetime

    class Config:
        from_attributes = True


class FloorBase(BaseModel):
    """Базовая модель этажа"""
    number: int = Field(..., ge=0, le=12)
    building_id: int


class FloorCreate(FloorBase):
    """Создание этажа"""
    pass


class FloorResponse(FloorBase):
    """Ответ с данными этажа"""
    id: int
    vector_model_id: Optional[int] = None
    navigation_graph_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class Coordinate(BaseModel):
    """Координата точки"""
    x: float
    y: float
    z: int = 0  # Номер этажа
