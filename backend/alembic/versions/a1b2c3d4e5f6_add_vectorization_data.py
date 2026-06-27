"""add vectorization_data column

Revision ID: a1b2c3d4e5f6
Revises: 5e18b384dd02
Create Date: 2026-03-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5e18b384dd02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reconstructions', sa.Column('vectorization_data', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('reconstructions', 'vectorization_data')
