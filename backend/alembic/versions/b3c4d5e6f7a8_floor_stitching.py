"""floor stitching: control points, transforms, floor scale + GLB, connectors table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('reconstructions') as batch_op:
        batch_op.add_column(
            sa.Column('control_points', sa.JSON(), nullable=True)
        )

    with op.batch_alter_table('sections') as batch_op:
        batch_op.add_column(
            sa.Column('control_points', sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('transform', sa.JSON(), nullable=True)
        )

    with op.batch_alter_table('floors') as batch_op:
        batch_op.add_column(
            sa.Column('pixels_per_meter', sa.Float(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('mesh_file_glb', sa.String(length=512), nullable=True)
        )

    op.create_table(
        'floor_connectors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('floor_id', sa.Integer(), nullable=False),
        sa.Column('points', sa.JSON(), nullable=False),
        sa.Column('height_m', sa.Float(), nullable=True),
        sa.Column('thickness_m', sa.Float(), nullable=True),
        sa.Column('connects', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['floor_id'], ['floors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_floor_connectors_id'), 'floor_connectors', ['id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_floor_connectors_id'), table_name='floor_connectors')
    op.drop_table('floor_connectors')

    with op.batch_alter_table('floors') as batch_op:
        batch_op.drop_column('mesh_file_glb')
        batch_op.drop_column('pixels_per_meter')

    with op.batch_alter_table('sections') as batch_op:
        batch_op.drop_column('transform')
        batch_op.drop_column('control_points')

    with op.batch_alter_table('reconstructions') as batch_op:
        batch_op.drop_column('control_points')
