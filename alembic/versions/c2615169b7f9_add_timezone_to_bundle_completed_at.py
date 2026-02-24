"""add_timezone_to_bundle_completed_at

Revision ID: c2615169b7f9
Revises: ff68e5280353
Create Date: 2026-02-24 21:23:39.744455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2615169b7f9'
down_revision: Union[str, None] = 'ff68e5280353'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bundles',
        sa.Column('completed_at_tz', sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE bundles SET completed_at_tz = completed_at AT TIME ZONE 'UTC' "
        "WHERE completed_at IS NOT NULL"
    )
    op.drop_column('bundles', 'completed_at')
    op.alter_column('bundles', 'completed_at_tz', new_column_name='completed_at')


def downgrade() -> None:
    op.add_column(
        'bundles',
        sa.Column('completed_at_naive', sa.DateTime(timezone=False), nullable=True)
    )
    op.execute(
        "UPDATE bundles SET completed_at_naive = completed_at AT TIME ZONE 'UTC' "
        "WHERE completed_at IS NOT NULL"
    )
    op.drop_column('bundles', 'completed_at')
    op.alter_column('bundles', 'completed_at_naive', new_column_name='completed_at')
