"""add can_approve_users field

Revision ID: c8d9e0f1g2h3
Revises: b7c8d9e0f1g2
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1g2h3'
down_revision: Union[str, None] = 'b7c8d9e0f1g2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('can_approve_users', sa.Boolean(), nullable=False, server_default='false'))
    # Remove server default after adding column
    op.alter_column('users', 'can_approve_users', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'can_approve_users')
