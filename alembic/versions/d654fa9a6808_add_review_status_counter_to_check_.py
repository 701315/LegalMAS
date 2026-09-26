"""add review_status_counter to check_results

Revision ID: d654fa9a6808
Revises: b63a43153958
Create Date: 2026-09-26 19:32:59.620936

Counter "N/M" для clause_partially_defined (см. commit 35571dc).
Null для всех остальных review_status.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd654fa9a6808'
down_revision: Union[str, None] = 'b63a43153958'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_results",
        sa.Column(
            "review_status_counter",
            sa.String(length=20),
            nullable=True,
            comment=(
                'Counter "N/M" для clause_partially_defined. '
                "Null для всех остальных review_status."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("check_results", "review_status_counter")