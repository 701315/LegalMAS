"""sync_deal_tenant_fk

Revision ID: e1a857f8e292
Revises: 5a9f9524447c
Create Date: 2026-07-16 21:37:08.733933
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e1a857f8e292"
down_revision: Union[str, None] = "5a9f9524447c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ❌ УДАЛЕНО: drop_table('outbox_messages')
    # Outbox используется системой — удалять нельзя.

    op.alter_column(
        "deals",
        "tenant_id",
        existing_type=sa.UUID(),
        comment="Owner of the deal. Cannot be changed after creation.",
        existing_nullable=False,
    )

    # Обновляем FK на deals → tenants
    op.drop_constraint("fk_deals_tenant_id", "deals", type_="foreignkey")
    op.create_foreign_key(
        "fk_deals_tenant_id",
        "deals",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",  # безопасное поведение
    )

    # Остальные изменения — только комментарии
    op.alter_column(
        "tenants",
        "name",
        existing_type=sa.VARCHAR(length=500),
        comment="Отображаемое название клиента",
        existing_nullable=False,
    )

    op.alter_column(
        "tenants",
        "slug",
        existing_type=sa.VARCHAR(length=100),
        comment="Короткий уникальный идентификатор клиента",
        existing_nullable=False,
    )


def downgrade() -> None:
    # Возвращаем предыдущий FK
    op.drop_constraint("fk_deals_tenant_id", "deals", type_="foreignkey")
    op.create_foreign_key(
        "fk_deals_tenant_id",
        "deals",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )


    