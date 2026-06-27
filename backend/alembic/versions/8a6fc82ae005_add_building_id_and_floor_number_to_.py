"""add building_id and floor_number to reconstructions

Revision ID: 8a6fc82ae005
Revises: d9e0f1g2h3i4
Create Date: 2026-03-23 10:24:06.712188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a6fc82ae005'
down_revision: Union[str, Sequence[str], None] = 'd9e0f1g2h3i4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Дубликат d9e0f1g2h3i4, колонки уже добавлены.
    pass


def downgrade() -> None:
    # Колонки удаляются в downgrade ревизии d9e0f1g2h3i4.
    pass
