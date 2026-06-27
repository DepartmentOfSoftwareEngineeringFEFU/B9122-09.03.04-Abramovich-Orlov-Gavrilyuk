"""
Database model for FloorTransition
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FloorTransition(Base):
    """FloorTransition DB Model — link between two floor plans at specific coordinates."""
    __tablename__ = "floor_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    building_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    from_reconstruction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reconstructions.id", ondelete="CASCADE"), nullable=False
    )
    from_geometry: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    from_x: Mapped[float] = mapped_column(Float, nullable=False)
    from_y: Mapped[float] = mapped_column(Float, nullable=False)

    to_reconstruction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reconstructions.id", ondelete="CASCADE"), nullable=False
    )
    to_geometry: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    to_x: Mapped[float] = mapped_column(Float, nullable=False)
    to_y: Mapped[float] = mapped_column(Float, nullable=False)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships intentionally omitted (project convention)
