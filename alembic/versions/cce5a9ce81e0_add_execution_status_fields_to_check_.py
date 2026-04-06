"""add execution status fields to check_results

Revision ID: cce5a9ce81e0
Revises: 054549ae8502
Create Date: 2026-04-06 07:24:32.608110

"""
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cce5a9ce81e0'
down_revision: Union[str, None] = '054549ae8502'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_results",
        sa.Column(
            "execution_status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
            comment="Execution status of this check: PENDING, RUNNING, SUCCESS, FAILED, TIMEOUT",
        ),
    )
    op.add_column(
        "check_results",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this check execution started",
        ),
    )
    op.add_column(
        "check_results",
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this check execution finished (any terminal state)",
        ),
    )
    op.add_column(
        "check_results",
        sa.Column(
            "error_details",
            JSONB,
            nullable=True,
            comment="Error/timeout details for FAILED/TIMEOUT executions",
        ),
    )

    op.create_index(
        "uq_results_run_doc_check",
        "check_results",
        ["run_id", "document_id", "check_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_results_run_doc_check", table_name="check_results")
    op.drop_column("check_results", "error_details")
    op.drop_column("check_results", "finished_at")
    op.drop_column("check_results", "started_at")
    op.drop_column("check_results", "execution_status")

