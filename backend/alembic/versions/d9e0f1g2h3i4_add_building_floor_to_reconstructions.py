"""add building_id and floor_number to reconstructions

Revision ID: d9e0f1g2h3i4
Revises: c8d9e0f1g2h3
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e0f1g2h3i4'
down_revision: Union[str, None] = 'c8d9e0f1g2h3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add building_id column (nullable for existing records)
    op.add_column('reconstructions', sa.Column('building_id', sa.String(length=50), nullable=True))

    # Add floor_number column (nullable for existing records)
    op.add_column('reconstructions', sa.Column('floor_number', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('reconstructions', 'floor_number')
    op.drop_column('reconstructions', 'building_id')
