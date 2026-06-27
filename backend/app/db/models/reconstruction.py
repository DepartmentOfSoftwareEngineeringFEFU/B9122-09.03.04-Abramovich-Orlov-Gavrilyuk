"""
Database models for Reconstruction and Files
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, Float, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.db.models.building import Floor
    from app.db.models.section import Section


class UploadedFile(Base):
    """Uploaded File DB Model"""
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)

    file_type: Mapped[int] = mapped_column(Integer, default=1)  # 1=Plan, 2=Mask, 3=Env
    uploaded_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    # user = relationship("User")


class Reconstruction(Base):
    """Reconstruction Project DB Model"""
    __tablename__ = "reconstructions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    plan_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("uploaded_files.id"), nullable=False
    )
    mask_file_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("uploaded_files.id"), nullable=True
    )
    mesh_file_id_obj: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mesh_file_id_glb: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # FK to floors — set when admin assigns building+floor in wizard (step 1)
    # ON DELETE SET NULL: deleting a floor makes this reconstruction "unbound"
    floor_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("floors.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[int] = mapped_column(
        Integer, default=1
    )  # 1=Created, 2=Processing, 3=Done, 4=Error
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vectorization_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON VectorizationResult
    # Section-local control points [{"id","x","y"}, ...] normalised [0,1]
    control_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    plan_file: Mapped["UploadedFile"] = relationship(
        "UploadedFile", foreign_keys=[plan_file_id]
    )
    mask_file: Mapped[Optional["UploadedFile"]] = relationship(
        "UploadedFile", foreign_keys=[mask_file_id]
    )
    # One-way relationship to Floor (no back_populates to avoid circular coupling)
    floor: Mapped[Optional["Floor"]] = relationship("Floor")
    # Back-reference from Section (1:1 via Section.reconstruction_id UNIQUE)
    section: Mapped[Optional["Section"]] = relationship(
        "Section",
        back_populates="reconstruction",
        uselist=False,
    )


class Room(Base):
    """Room Marker DB Model"""
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    reconstruction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reconstructions.id", ondelete="CASCADE"), nullable=False
    )

    number: Mapped[str] = mapped_column(String(20), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)

    # relationship("Reconstruction", back_populates="rooms")
