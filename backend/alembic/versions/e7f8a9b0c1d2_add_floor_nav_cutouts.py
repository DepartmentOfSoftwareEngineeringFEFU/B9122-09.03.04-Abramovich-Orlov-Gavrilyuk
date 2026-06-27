"""floors: add nav_cutouts JSON column

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-06-06

Adds ``floors.nav_cutouts`` — a single nullable JSON column holding the wizard
step-8 cutout zones (``[{"points": [[x,y], ...]}, ...]`` normalised [0,1] over
the master canvas). Cutouts ERASE walls (fill ``0`` in ``assemble_floor_mask``)
for BOTH the nav graph and the 3D mesh. No new table / repository is needed —
both build paths already load the ``Floor`` row.

Plain ``op.add_column`` (not batch): adding a NULLABLE column is the one ALTER
SQLite supports natively, so no table-copy / FK-recreation is needed. Existing
rows read as ``NULL`` → the service treats ``None`` as "no cutouts".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'floors',
        sa.Column('nav_cutouts', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('floors', 'nav_cutouts')
