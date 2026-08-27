"""add_retry_fields_to_run_summaries

Revision ID: 8f0b10ab5056
Revises: f6e80b2d3d99
Create Date: 2026-08-27 09:03:43.639715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f0b10ab5056'
down_revision: Union[str, None] = 'f6e80b2d3d99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'run_summaries',
        sa.Column(
            'retry_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'run_summaries',
        sa.Column(
            'next_retry_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('run_summaries', 'next_retry_at')
    op.drop_column('run_summaries', 'retry_count')

    