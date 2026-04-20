"""add check_result_persist_errors table

Revision ID: 1da1ebbdbfce
Revises: a1102463b475
Create Date: 2026-04-20 16:04:41.303303

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1da1ebbdbfce'
down_revision: Union[str, None] = 'a1102463b475'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "check_result_persist_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("check_id", sa.String(length=100), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("sqlstate", sa.String(length=10), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "retryable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolution_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("resolution_comment", sa.Text(), nullable=True),
    )

    op.create_index(
        "idx_cr_persist_errors_run",
        "check_result_persist_errors",
        ["run_id"],
    )
    op.create_index(
        "idx_cr_persist_errors_doc",
        "check_result_persist_errors",
        ["document_id"],
    )
    op.create_index(
        "idx_cr_persist_errors_status_retry",
        "check_result_persist_errors",
        ["resolution_status", "retryable"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_cr_persist_errors_status_retry",
        table_name="check_result_persist_errors",
    )
    op.drop_index(
        "idx_cr_persist_errors_doc",
        table_name="check_result_persist_errors",
    )
    op.drop_index(
        "idx_cr_persist_errors_run",
        table_name="check_result_persist_errors",
    )
    op.drop_table("check_result_persist_errors")
