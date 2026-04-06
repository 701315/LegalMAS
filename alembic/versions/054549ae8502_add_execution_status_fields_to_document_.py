"""add execution status fields to document_versions

Revision ID: 054549ae8502
Revises: 57b6be7c014f
Create Date: 2026-04-05 21:14:51.941989

"""
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '054549ae8502'
down_revision: Union[str, None] = '57b6be7c014f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. execution_status - статус выполнения
    op.add_column(
        "document_versions",
        sa.Column(
            "execution_status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
            comment="Execution status of this check: PENDING, RUNNING, SUCCESS, FAILED, TIMEOUT",
        ),
    )

    # 2. started_at - время начала выполнения
    op.add_column(
        "document_versions",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this check execution started",
        ),
    )

    # 3. finished_at - время завершения выполнения
    op.add_column(
        "document_versions",
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this check execution finished (any terminal state)",
        ),
    )

    # 4. error_details - детали ошибок (JSONB)
    op.add_column(
        "document_versions",
        sa.Column(
            "error_details",
            JSONB,
            nullable=True,
            comment="Error/timeout details for FAILED/TIMEOUT executions",
        ),
    )

    # 5. (Опционально) Индекс для быстрого поиска по статусу
    op.create_index(
        "ix_document_versions_execution_status",
        "document_versions",
        ["execution_status"],
    )


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index("ix_document_versions_execution_status", table_name="document_versions")

    # Удаляем колонки в обратном порядке
    op.drop_column("document_versions", "error_details")
    op.drop_column("document_versions", "finished_at")
    op.drop_column("document_versions", "started_at")
    op.drop_column("document_versions", "execution_status")
