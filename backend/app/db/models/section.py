"""
Database model for Section (отсек этажа).

Section represents a bounded area on a Floor that can be linked to a Reconstruction.
geometry is a 4-point polygon (rotated rectangle) in normalised [0,1] coords.
no description, no color fields.
section_type is an int enum (1=room default, 2=stairs, 3=elevator).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.db.models.building import Floor
    from app.db.models.reconstruction import Reconstruction


class Section(Base):
    """Section DB Model — a marked area on a floor linked to a reconstruction plan."""

    __tablename__ = "sections"

    __table_args__ = (
        UniqueConstraint('floor_id', 'number', name='uq_section_floor_number'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    floor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("floors.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    # 4-point polygon [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] in normalised [0,1] coords
    geometry: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Master-schema control points [{"point_id","x","y"}, ...] normalised [0,1]
    control_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Solved similarity transform (px-space):
    # {"scale","tx","ty","residual_rms_px","n_points","solved_at"}
    transform: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    reconstruction_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("reconstructions.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    # 1=room (default), 2=stairs, 3=elevator — reserved for future use
    section_type: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    floor: Mapped["Floor"] = relationship("Floor", back_populates="sections")
    reconstruction: Mapped[Optional["Reconstruction"]] = relationship(
        "Reconstruction",
        back_populates="section",
        uselist=False,
    )
