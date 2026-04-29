"""add_processing_status_and_error_message_to_exports

Revision ID: ea852ac0f3e2
Revises: 94d2f6910558
Create Date: 2026-04-28 16:07:22.523995

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea852ac0f3e2'
down_revision: Union[str, None] = '94d2f6910558'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем error_message, если его ещё нет
    op.add_column(
        "exports",
        sa.Column(
            "error_message",
            sa.String(length=2000),
            nullable=True,
            comment="Last export error message, populated when status=failed",
        ),
    )

    # 2. Расширяем комментарий к status, чтобы отразить новое значение 'processing'.
    #    Сам тип — String(50), никакого enum нет, поэтому ddl не меняем.
    #    Документируем через comment.
    op.alter_column(
        "exports",
        "status",
        existing_type=sa.String(length=50),
        comment="pending, processing, completed, failed",
        existing_nullable=False,
    )

    # 3. Добавляем индекс на run_id, если его нет
    #    (нужен для ExportListResponse по run)
    op.create_index(
        "ix_exports_run_id",
        "exports",
        ["run_id"],
        unique=False,
        if_not_exists=True,
    )

    # 4. Добавляем индекс на status для быстрой фильтрации pending-задач
    op.create_index(
        "ix_exports_status",
        "exports",
        ["status"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_exports_status", table_name="exports")
    op.drop_index("ix_exports_run_id", table_name="exports")
    op.drop_column("exports", "error_message")
    
