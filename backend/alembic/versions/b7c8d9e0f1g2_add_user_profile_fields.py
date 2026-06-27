"""add user profile fields

Revision ID: b7c8d9e0f1g2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1g2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:


    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('full_name', sa.String(length=255), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('birth_date', sa.Date(), nullable=False, server_default='2000-01-01'))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('birth_date')
        batch_op.drop_column('full_name')
