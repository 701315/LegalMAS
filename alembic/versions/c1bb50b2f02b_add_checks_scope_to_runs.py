"""add checks_scope to runs

Revision ID: c1bb50b2f02b
Revises: 9643adbf4ec0
Create Date: 2026-04-15 13:49:07.979747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1bb50b2f02b'
down_revision: Union[str, None] = '9643adbf4ec0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "checks_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Segment-aware scope for checks execution. "
                "Example: {'scope_preset': 'primary_only'}"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "checks_scope")
    