"""
Database models for Building and Floor.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.db.models.floor_connector import FloorConnector
    from app.db.models.reconstruction import UploadedFile
    from app.db.models.section import Section


class Building(Base):
    """Building DB Model"""

    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Short unique code displayed in the section selector (e.g. "S", "D", "B")
    code: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Operator overrides on top of the auto-matched cross-floor links
    # (multifloor-routing, subfeature D). Format: [{lower_floor_id, lower_node,
    # upper_floor_id, upper_node, action: "disable"|"force"}]. null/[] = pure
    # auto-match. Mirrors the Floor.nav_cutouts JSON-column style.
    transition_overrides: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    floors: Mapped[List["Floor"]] = relationship(
        "Floor",
        back_populates="building",
        cascade="all, delete-orphan",
        order_by="Floor.number",
    )


class Floor(Base):
    """Floor DB Model"""

    __tablename__ = "floors"

    __table_args__ = (
        UniqueConstraint('building_id', 'number', name='uq_floor_building_number'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    building_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Photo-scheme of the floor (uploaded on wizard step 1)
    schema_image_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Crop/rotation parameters applied to schema_image (wizard step 2)
    # Format: {x, y, width, height, rotation}
    schema_crop_bbox: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Wall polygons extracted from the schema image (wizard step 3)
    # Format: [[[x,y], ...], ...] normalised [0,1]
    wall_polygons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Persisted user-edited wall mask PNG (wizard step 3). Display source that
    # survives reload — mirrors Reconstruction.mask_file.
    mask_file_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Floor metric scale — master schema pixels per metre (set at assembly time)
    pixels_per_meter: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Path to the assembled (stitched) floor GLB mesh
    mesh_file_glb: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Cutout zones (wizard step 8) — polygons that ERASE walls for nav + 3D.
    # Format: [{"points": [[x,y], ...]}, ...] normalised [0,1] over the master canvas.
    nav_cutouts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Vertical floor stitching (subfeature A)
    # Anchor points placed on THIS floor's wall mask for the pair (this floor ↔
    # the floor BELOW). The pair is stored on the UPPER floor's row; the lowest
    # floor stores nothing (it is the reference). Format: [{"id","x","y"}, ...]
    # normalised [0,1] over this floor's wall mask.
    stitch_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Matching reference points on the floor BELOW's wall mask, paired with
    # ``stitch_points`` by id. Format: [{"id","x","y"}, ...] normalised [0,1]
    # over the lower floor's wall mask.
    stitch_ref_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # SHARED B/D CONTRACT (do NOT change semantics — see plan/README):
    # a similarity mapping THIS floor's wall-mask pixels → the REFERENCE (lowest)
    # floor's wall-mask pixels. Lowest floor = identity. ``None`` = unsolved /
    # unlinked. Format: {scale, rotation_rad, tx, ty, residual_rms_px, n_points}.
    building_transform: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    building: Mapped["Building"] = relationship("Building", back_populates="floors")
    sections: Mapped[List["Section"]] = relationship(
        "Section",
        back_populates="floor",
        cascade="all, delete-orphan",
        order_by="Section.number",
    )
    connectors: Mapped[List["FloorConnector"]] = relationship(
        "FloorConnector",
        back_populates="floor",
        cascade="all, delete-orphan",
        order_by="FloorConnector.id",
    )
    schema_image: Mapped[Optional["UploadedFile"]] = relationship(
        "UploadedFile",
        foreign_keys=[schema_image_id],
    )
    mask_file: Mapped[Optional["UploadedFile"]] = relationship(
        "UploadedFile",
        foreign_keys=[mask_file_id],
    )
