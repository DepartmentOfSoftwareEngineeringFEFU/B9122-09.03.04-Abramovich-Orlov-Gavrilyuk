"""floor_transitions: add from_geometry / to_geometry JSON columns

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-06

The ``FloorTransition`` ORM model declares ``from_geometry`` and ``to_geometry``
(JSON, nullable), but no migration ever added them, so the live DB's
``floor_transitions`` table lacked both columns. Every SELECT through
``FloorTransitionRepository`` projects all mapped columns, so the query failed
at compile time with ``no such column: floor_transitions.from_geometry`` — which
took down the whole 3D-build pipeline at ``build_mesh`` step 12.5 (transition
markers). This migration adds the two missing columns.

Plain ``op.add_column`` is used (not batch): adding a NULLABLE column is the one
ALTER that SQLite supports natively, so no table-copy / FK-recreation is needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'floor_transitions',
        sa.Column('from_geometry', sa.JSON(), nullable=True),
    )
    op.add_column(
        'floor_transitions',
        sa.Column('to_geometry', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('floor_transitions', 'to_geometry')
    op.drop_column('floor_transitions', 'from_geometry')
