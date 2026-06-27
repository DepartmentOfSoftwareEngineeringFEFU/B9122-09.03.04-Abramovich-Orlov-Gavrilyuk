"""buildings: add transition_overrides column

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-08

Adds one nullable JSON column to ``buildings`` for the multifloor-routing feature
(subfeature D):

- ``transition_overrides`` — operator edits on top of the auto-matched cross-floor
  links. Format: ``[{lower_floor_id, lower_node, upper_floor_id, upper_node,
  action: "disable"|"force"}]``. null/[] = pure auto-match.

Chain order is A → D: ``down_revision`` is A's vertical-floor-stitching migration
(``f1a2b3c4d5e6``). The column lives on ``buildings`` (schema-independent of A's
``floors`` columns), but D consumes A's ``building_transform`` at runtime so the
chain stays A-first.

Plain ``op.add_column`` (not batch): adding a NULLABLE column is the one ALTER
SQLite supports natively. Existing rows read as ``NULL`` → the service treats
``None`` as "no overrides" (pure auto-match).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'buildings',
        sa.Column('transition_overrides', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('buildings', 'transition_overrides')
