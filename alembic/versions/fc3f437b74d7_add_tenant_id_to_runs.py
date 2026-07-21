"""add_tenant_id_to_runs

Revision ID: fc3f437b74d7
Revises: 63ae307cde4e
Create Date: 2026-07-21 14:52:35.065402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fc3f437b74d7'
down_revision: Union[str, None] = '63ae307cde4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем nullable — без этого PostgreSQL заблокирует таблицу
    #    на время UPDATE при большом количестве строк.
    op.add_column(
        "runs",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "Owner tenant of this Run. "
                "Frozen copy of Deal.tenant_id at run creation time."
            ),
        ),
    )

    # 2. Backfill: заполнить tenant_id из deals по runs.deal_id.
    #    Deal.tenant_id NOT NULL гарантирует, что после этого UPDATE
    #    ни одна строка не останется NULL.
    op.execute("""
        UPDATE runs
        SET tenant_id = deals.tenant_id
        FROM deals
        WHERE runs.deal_id = deals.id
    """)

    # 3. Делаем NOT NULL после backfill.
    op.alter_column("runs", "tenant_id", nullable=False)

    # 4. FK на tenants.
    #    RESTRICT: нельзя удалить tenant, пока есть Run'ы.
    op.create_foreign_key(
        "fk_runs_tenant_id_tenants",
        "runs",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 5. Индекс для tenant-scoped queries.
    op.create_index("idx_runs_tenant_id", "runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_runs_tenant_id", table_name="runs")
    op.drop_constraint("fk_runs_tenant_id_tenants", "runs", type_="foreignkey")
    op.drop_column("runs", "tenant_id")


    