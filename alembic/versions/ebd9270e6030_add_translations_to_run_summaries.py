"""add translations to run_summaries

Revision ID: ebd9270e6030
Revises: 41a3ed58d450
Create Date: 2026-09-09 03:58:17.779910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ebd9270e6030'
down_revision: Union[str, None] = '41a3ed58d450'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_summaries",
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='{"en": {"text": "...", "claims": {...}, "fallback": {...}}}',
        ),
    )
    op.add_column(
        "run_summaries",
        sa.Column(
            "translation_status",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='{"en": "pending"|"ready"|"failed"}',
        ),
    )


def downgrade() -> None:
    op.drop_column("run_summaries", "translation_status")
    op.drop_column("run_summaries", "translations")

    