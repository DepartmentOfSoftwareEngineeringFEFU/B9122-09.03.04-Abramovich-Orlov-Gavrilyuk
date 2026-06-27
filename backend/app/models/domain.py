from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Tuple


class Point2D(BaseModel):
    """Точка в нормализованных координатах [0, 1]."""
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)


class Wall(BaseModel):
    """Стена как полилиния точек."""
    id: str
    points: List[Point2D]
    thickness: float = 0.2


class TextBlock(BaseModel):
    """Распознанный текстовый блок (OCR)."""
    text: str
    center: Point2D
    confidence: float = Field(0.0, ge=0.0, le=100.0)
    is_room_number: bool = False


class Room(BaseModel):
    """Комната — замкнутый полигон с метаданными."""
    id: str
    name: str = ""
    polygon: List[Point2D]
    center: Point2D
    room_type: str = "room"  # "room" | "corridor" | "staircase" | "elevator"
    area_normalized: float = Field(0.0, ge=0.0)
    # Inter-floor link data for elevators (см. floor-transition-tools).
    # Room/corridor/staircase leave these at defaults.
    floor_from: Optional[int] = None
    floor_to: Optional[int] = None
    floors_excluded: List[int] = Field(default_factory=list)
    # Stair directional gates (multifloor-routing, subfeature D). Only meaningful
    # for ``room_type == "staircase"``; harmless True defaults elsewhere. A stair
    # links N↔N+1 only when the lower stair ``connects_up`` AND the upper stair
    # ``connects_down`` (so a stair that tops out at a floor can be marked).
    connects_up: bool = True
    connects_down: bool = True

    @model_validator(mode="after")
    def _validate_floor_range(self) -> "Room":
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


class Door(BaseModel):
    """Дверь — точка между двумя комнатами."""
    id: str
    position: Point2D
    width: float = Field(0.0, ge=0.0)
    connects: List[str] = Field(default_factory=list)  # room IDs


class FloorPlan(BaseModel):
    """Доменная модель плана этажа (не ORM, не API response)."""
    id: str
    walls: List[Wall] = []
    image_width: int
    image_height: int


class VectorizationResult(BaseModel):
    """Полный структурированный результат векторизации."""
    # Структурные элементы
    walls: List[Wall] = Field(default_factory=list)
    rooms: List[Room] = Field(default_factory=list)
    doors: List[Door] = Field(default_factory=list)
    text_blocks: List[TextBlock] = Field(default_factory=list)

    # Метаданные изображения
    image_size_original: Tuple[int, int]  # (width, height) до кропа
    image_size_cropped: Tuple[int, int]   # (width, height) после кропа
    crop_rect: Optional[dict] = None      # {x, y, width, height} [0,1]
    crop_applied: bool = False
    rotation_angle: int = 0               # 0/90/180/270

    # Масштаб и геометрия
    wall_thickness_px: float = 0.0
    estimated_pixels_per_meter: float = 50.0

    # Статистика
    rooms_with_names: int = 0
    corridors_count: int = 0
    doors_count: int = 0
