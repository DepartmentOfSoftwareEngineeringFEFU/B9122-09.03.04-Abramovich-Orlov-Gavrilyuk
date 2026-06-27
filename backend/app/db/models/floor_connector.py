"""
Database model for FloorConnector (соединительная линия между отсеками этажа).

A FloorConnector is an open polyline on the master schema that bridges section
masks during floor assembly (rasterised as a wall band). Points are stored in
master-normalised [0,1] coordinates; a connector has >= 2 points.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.db.models.building import Floor


class FloorConnector(Base):
    """FloorConnector DB Model — an open polyline that connects sections on a floor."""

    __tablename__ = "floor_connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    floor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("floors.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Open polyline [[x,y], ...] in master-normalised [0,1] coords, >= 2 points
    points: Mapped[list] = mapped_column(JSON, nullable=False)
    # Wall band height in metres (nullable → default floor_height at assembly time)
    height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Wall band thickness in metres (nullable → default wall thickness at assembly time)
    thickness_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # [section_id, ...] linked sections — reserved for future routing
    connects: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    floor: Mapped["Floor"] = relationship("Floor", back_populates="connectors")
