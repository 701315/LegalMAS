"""add result_details to document_stage_executions

Revision ID: a8dade36df13
Revises: 55252b969781
Create Date: 2026-06-03 13:41:18.035305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'a8dade36df13'
down_revision: Union[str, None] = '55252b969781'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_stage_executions",
        sa.Column(
            "result_details",
            JSONB,
            nullable=True,
            comment=(
                "Structured terminal result metadata for successfully completed stages. "
                "Used for semantic enrichment stage outcomes: "
                "{terminal_outcome, segments_enriched, segments_timed_out, "
                "segments_failed, segments_skipped_budget, budget_exhausted, ...}"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_stage_executions", "result_details")

    