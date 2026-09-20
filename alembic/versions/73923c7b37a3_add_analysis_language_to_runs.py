"""add_analysis_language_to_runs

Revision ID: 73923c7b37a3
Revises: cb035f999620
Create Date: 2026-09-07 04:11:40.000218

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '73923c7b37a3'
down_revision: Union[str, None] = 'cb035f999620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "analysis_language",
            sa.String(10),
            nullable=True,
            comment=(
                "Frozen copy of Deal.primary_language at run creation time. "
                "Represents the language in which legal analysis was performed. "
                "Never changes after creation."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "analysis_language")