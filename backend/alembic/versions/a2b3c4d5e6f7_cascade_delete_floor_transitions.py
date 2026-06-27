"""cascade delete on floor_transitions and rooms FKs to reconstructions

Revision ID: a2b3c4d5e6f7
Revises: f1g2h3i4j5k6
Create Date: 2026-05-25

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f1g2h3i4j5k6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # floor_transitions: drop plain FKs, recreate with CASCADE
    op.drop_constraint(
        'floor_transitions_from_reconstruction_id_fkey',
        'floor_transitions',
        type_='foreignkey',
    )
    op.drop_constraint(
        'floor_transitions_to_reconstruction_id_fkey',
        'floor_transitions',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'floor_transitions_from_reconstruction_id_fkey',
        'floor_transitions', 'reconstructions',
        ['from_reconstruction_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'floor_transitions_to_reconstruction_id_fkey',
        'floor_transitions', 'reconstructions',
        ['to_reconstruction_id'], ['id'],
        ondelete='CASCADE',
    )

    # rooms: drop plain FK, recreate with CASCADE
    op.drop_constraint(
        'rooms_reconstruction_id_fkey',
        'rooms',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'rooms_reconstruction_id_fkey',
        'rooms', 'reconstructions',
        ['reconstruction_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'rooms_reconstruction_id_fkey', 'rooms', type_='foreignkey'
    )
    op.create_foreign_key(
        'rooms_reconstruction_id_fkey',
        'rooms', 'reconstructions',
        ['reconstruction_id'], ['id'],
    )

    op.drop_constraint(
        'floor_transitions_to_reconstruction_id_fkey',
        'floor_transitions',
        type_='foreignkey',
    )
    op.drop_constraint(
        'floor_transitions_from_reconstruction_id_fkey',
        'floor_transitions',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'floor_transitions_to_reconstruction_id_fkey',
        'floor_transitions', 'reconstructions',
        ['to_reconstruction_id'], ['id'],
    )
    op.create_foreign_key(
        'floor_transitions_from_reconstruction_id_fkey',
        'floor_transitions', 'reconstructions',
        ['from_reconstruction_id'], ['id'],
    )
