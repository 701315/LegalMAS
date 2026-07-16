"""add_tenant_id_to_dlq

Revision ID: 04a49a9094d0
Revises: e1a857f8e292
Create Date: 2026-07-16
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "04a49a9094d0"
down_revision: Union[str, None] = "e1a857f8e292"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ 1. Удаляем старые DLQ записи (мы не знаем их tenant)
    op.execute("DELETE FROM dlq_records")

    # ✅ 2. Добавляем колонку
    op.add_column(
        "dlq_records",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
    )

    # ✅ 3. Создаем индекс
    op.create_index(
        op.f("ix_dlq_records_tenant_id"),
        "dlq_records",
        ["tenant_id"],
        unique=False,
    )

    # ✅ 4. Добавляем FK
    op.create_foreign_key(
        "fk_dlq_records_tenant_id",
        "dlq_records",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_dlq_records_tenant_id", "dlq_records", type_="foreignkey")
    op.drop_index(op.f("ix_dlq_records_tenant_id"), table_name="dlq_records")
    op.drop_column("dlq_records", "tenant_id")


    