"""add run_summaries table

Revision ID: e59483da6a25
Revises: 68f22a25ed87
Create Date: 2026-08-14 05:52:31.860166

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e59483da6a25'
down_revision: Union[str, None] = '68f22a25ed87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "claims",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "fallback",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("run_id", name="uq_run_summaries_run_id"),
    )

    op.create_index("idx_run_summaries_run_id", "run_summaries", ["run_id"])
    op.create_index("idx_run_summaries_tenant_id", "run_summaries", ["tenant_id"])
    op.create_index("idx_run_summaries_status", "run_summaries", ["status"])


def downgrade() -> None:
    op.drop_index("idx_run_summaries_status", table_name="run_summaries")
    op.drop_index("idx_run_summaries_tenant_id", table_name="run_summaries")
    op.drop_index("idx_run_summaries_run_id", table_name="run_summaries")
    op.drop_table("run_summaries")


    
