"""floor: persisted user-edited wall-mask file id

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # floors: persisted user-edited wall mask. The FK is declared on the ORM
    # model (for create_all / tests); the column is added plain here for SQLite
    # safety, mirroring how schema_image_id was added in f1g2h3i4j5k6.
    with op.batch_alter_table('floors') as batch_op:
        batch_op.add_column(
            sa.Column('mask_file_id', sa.String(length=36), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('floors') as batch_op:
        batch_op.drop_column('mask_file_id')
