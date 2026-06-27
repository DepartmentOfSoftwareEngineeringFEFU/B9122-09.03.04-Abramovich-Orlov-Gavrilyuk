"""
Database models for transitions between reconstructions.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TransitionGroup(Base):
    """Logical connector across multiple reconstructions."""

    __tablename__ = "transition_groups"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    building_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="passage")
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_hint_building_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_hint_floor_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    points = relationship(
        "TransitionPoint",
        back_populates="group",
        cascade="all, delete-orphan",
    )


class TransitionPoint(Base):
    """Point on a reconstruction that belongs to a transition group."""

    __tablename__ = "transition_points"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    reconstruction_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reconstructions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("transition_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    geometry: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    position_x: Mapped[float] = mapped_column(Float, nullable=False)
    position_y: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_hint_building_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_hint_floor_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    group = relationship("TransitionGroup", back_populates="points")
    reconstruction = relationship("Reconstruction")
