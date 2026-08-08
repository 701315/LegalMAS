"""add_llm_usage_events

Revision ID: 68f22a25ed87
Revises: df9c2c8df549
Create Date: 2026-08-02 06:29:12.212227

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '68f22a25ed87'
down_revision: Union[str, None] = 'df9c2c8df549'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("check_id", sa.String(100), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("llm_attempts", sa.Integer(), nullable=True),
        sa.Column("parse_success", sa.Boolean(), nullable=True),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("request_uid", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "uq_llm_usage_events_request_uid",
        "llm_usage_events",
        ["request_uid"],
        unique=True,
    )
    op.create_index(
        "idx_llm_usage_deal_stage",
        "llm_usage_events",
        ["deal_id", "stage"],
    )
    op.create_index(
        "idx_llm_usage_deal_created",
        "llm_usage_events",
        ["deal_id", "created_at"],
    )
    op.create_index(
        "idx_llm_usage_run",
        "llm_usage_events",
        ["run_id"],
    )
    op.create_index(
        "idx_llm_usage_tenant_created",
        "llm_usage_events",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_llm_usage_tenant_created", table_name="llm_usage_events")
    op.drop_index("idx_llm_usage_run", table_name="llm_usage_events")
    op.drop_index("idx_llm_usage_deal_created", table_name="llm_usage_events")
    op.drop_index("idx_llm_usage_deal_stage", table_name="llm_usage_events")
    op.drop_index(
        "uq_llm_usage_events_request_uid", table_name="llm_usage_events"
    )
    op.drop_table("llm_usage_events")

    