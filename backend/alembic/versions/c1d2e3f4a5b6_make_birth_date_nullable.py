"""make birth_date nullable

Revision ID: c1d2e3f4a5b6
Revises: a7b8c9d0e1f2
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'birth_date',
            existing_type=sa.Date(),
            nullable=True,
        )


def downgrade() -> None:
    op.execute("UPDATE users SET birth_date = '2000-01-01' WHERE birth_date IS NULL")
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'birth_date',
            existing_type=sa.Date(),
            nullable=False,
        )
