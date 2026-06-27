"""add floor transitions table

Revision ID: e0f1g2h3i4j5
Revises: 09898073b61c
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0f1g2h3i4j5'
down_revision: Union[str, None] = '09898073b61c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "floor_transitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("building_id", sa.String(50), nullable=True),
        sa.Column("from_reconstruction_id", sa.Integer(), nullable=False),
        sa.Column("from_x", sa.Float(), nullable=False),
        sa.Column("from_y", sa.Float(), nullable=False),
        sa.Column("to_reconstruction_id", sa.Integer(), nullable=False),
        sa.Column("to_x", sa.Float(), nullable=False),
        sa.Column("to_y", sa.Float(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["from_reconstruction_id"], ["reconstructions.id"]),
        sa.ForeignKeyConstraint(["to_reconstruction_id"], ["reconstructions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_floor_transitions_id", "floor_transitions", ["id"])
    op.create_index(
        "ix_floor_transitions_building_id", "floor_transitions", ["building_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_floor_transitions_building_id", table_name="floor_transitions")
    op.drop_index("ix_floor_transitions_id", table_name="floor_transitions")
    op.drop_table("floor_transitions")
