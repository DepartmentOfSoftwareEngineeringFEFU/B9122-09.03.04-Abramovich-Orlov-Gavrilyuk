"""floors: add vertical-stitching columns

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-06-07

Adds three nullable JSON columns to ``floors`` for the vertical floor-stitching
feature (subfeature A):

- ``stitch_points``      — anchor points on THIS floor's wall mask (the pair is
                           stored on the UPPER floor's row).
- ``stitch_ref_points``  — matching points on the floor BELOW's wall mask.
- ``building_transform`` — SHARED B/D CONTRACT: similarity mapping this floor's
                           wall-mask px → the reference (lowest) floor's
                           wall-mask px. Lowest floor = identity. NULL =
                           unsolved/unlinked.

Plain ``op.add_column`` (not batch): adding NULLABLE columns is the one ALTER
SQLite supports natively, so no table-copy / FK-recreation is needed. Existing
rows read as ``NULL`` → the service treats ``None`` as "no points / unsolved".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'floors',
        sa.Column('stitch_points', sa.JSON(), nullable=True),
    )
    op.add_column(
        'floors',
        sa.Column('stitch_ref_points', sa.JSON(), nullable=True),
    )
    op.add_column(
        'floors',
        sa.Column('building_transform', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('floors', 'building_transform')
    op.drop_column('floors', 'stitch_ref_points')
    op.drop_column('floors', 'stitch_points')
