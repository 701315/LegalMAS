"""strengthen dlq records schema

Revision ID: a65580b211a0
Revises: 322467766bc8
Create Date: 2026-05-18 12:36:38.848300

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a65580b211a0'
down_revision: Union[str, None] = '322467766bc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Новые nullable колонки сначала добавляем мягко.
    op.add_column(
        "dlq_records",
        sa.Column(
            "source_task_id",
            sa.String(length=255),
            nullable=True,
            comment="Original Celery task_id that produced this DLQ record",
        ),
    )
    op.add_column(
        "dlq_records",
        sa.Column(
            "dedupe_key",
            sa.String(length=255),
            nullable=True,
            comment="Optional stable fingerprint for deduplication/grouping of repeated failures",
        ),
    )

    # 2. Проставляем server defaults для существующих и будущих строк.
    op.alter_column(
        "dlq_records",
        "error_details",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=sa.text("'{}'::jsonb"),
    )
    op.alter_column(
        "dlq_records",
        "artifact_refs",
        existing_type=postgresql.ARRAY(sa.String(length=1000)),
        nullable=True,
        server_default=sa.text("'{}'"),
    )
    op.alter_column(
        "dlq_records",
        "retry_count",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    )
    op.alter_column(
        "dlq_records",
        "next_action",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=sa.text("'retry_manual'"),
    )

    # 3. Нормализуем старые NULL-данные перед NOT NULL.
    op.execute(
        "UPDATE dlq_records SET error_details = '{}'::jsonb WHERE error_details IS NULL"
    )
    op.execute(
        "UPDATE dlq_records SET artifact_refs = '{}' WHERE artifact_refs IS NULL"
    )

    # 4. После backfill можно сделать колонки обязательными.
    op.alter_column(
        "dlq_records",
        "error_details",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )
    op.alter_column(
        "dlq_records",
        "artifact_refs",
        existing_type=postgresql.ARRAY(sa.String(length=1000)),
        nullable=False,
        server_default=sa.text("'{}'"),
    )

    # 5. Индексы.
    op.create_index("ix_dlq_records_job_id", "dlq_records", ["job_id"], unique=False)
    op.create_index("idx_dlq_created_at", "dlq_records", ["created_at"], unique=False)
    op.create_index(
        "idx_dlq_task_failure_created",
        "dlq_records",
        ["task_type", "failure_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_dlq_next_action_created",
        "dlq_records",
        ["next_action", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_dlq_source_task_id",
        "dlq_records",
        ["source_task_id"],
        unique=False,
    )
    op.create_index(
        "idx_dlq_dedupe_key",
        "dlq_records",
        ["dedupe_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_dlq_dedupe_key", table_name="dlq_records")
    op.drop_index("idx_dlq_source_task_id", table_name="dlq_records")
    op.drop_index("idx_dlq_next_action_created", table_name="dlq_records")
    op.drop_index("idx_dlq_task_failure_created", table_name="dlq_records")
    op.drop_index("idx_dlq_created_at", table_name="dlq_records")
    op.drop_index("ix_dlq_records_job_id", table_name="dlq_records")

    op.alter_column(
        "dlq_records",
        "artifact_refs",
        existing_type=postgresql.ARRAY(sa.String(length=1000)),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "dlq_records",
        "error_details",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "dlq_records",
        "next_action",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "dlq_records",
        "retry_count",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=None,
    )

    op.drop_column("dlq_records", "dedupe_key")
    op.drop_column("dlq_records", "source_task_id")

    