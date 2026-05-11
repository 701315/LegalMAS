"""add outbox_messages table

Revision ID: 5a65d6dfd5d5
Revises: 6960a5a69d79
Create Date: 2026-05-11 20:30:22.376675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5a65d6dfd5d5'
down_revision: Union[str, None] = '6960a5a69d79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbox_messages",
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("task_name", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_key", name="uq_outbox_messages_dedup_key"),
    )

    op.create_index(
        "ix_outbox_messages_status_available_at",
        "outbox_messages",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_messages_aggregate",
        "outbox_messages",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_aggregate", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_status_available_at", table_name="outbox_messages")
    op.drop_constraint(
        "uq_outbox_messages_dedup_key",
        "outbox_messages",
        type_="unique",
    )
    op.drop_table("outbox_messages")
