"""add context_trace to check_results

Revision ID: 84986185f7eb
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18 08:44:15.088679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '84986185f7eb'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_results",
        sa.Column(
            "context_trace",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Compact retrieval/extraction provenance trace. "
                "List of the top-ranked contexts/chunks used to build LLM context."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("check_results", "context_trace")