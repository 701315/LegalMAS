"""drop legacy families table

Revision ID: ea01f9cffd39
Revises: 8a09232bab5a
Create Date: 2026-02-28 00:13:56.734003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea01f9cffd39'
down_revision: Union[str, None] = '8a09232bab5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем legacy-таблицу families
    op.drop_table("families")


def downgrade() -> None:
    # Восстанавливаем families в минимальном исходном виде
    op.create_table(
        "families",
        sa.Column("deal_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("master_doc_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("id", sa.dialects.postgresql.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="families_pkey"),
    )
    op.create_index(
        "ix_families_deal_id",
        "families",
        ["deal_id"],
        unique=False,
    )