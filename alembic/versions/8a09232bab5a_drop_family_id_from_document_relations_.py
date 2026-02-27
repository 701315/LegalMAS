"""drop family_id from document_relations and legacy families link

Revision ID: 8a09232bab5a
Revises: cb4537a60695
Create Date: 2026-02-28 00:11:27.480508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a09232bab5a'
down_revision: Union[str, None] = 'cb4537a60695'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Удаляем внешний ключ document_relations.family_id -> families.id
    op.drop_constraint(
        "document_relations_family_id_fkey",
        "document_relations",
        type_="foreignkey",
    )

    # 2) Удаляем индекс по family_id, если он есть
    op.drop_index(
        "idx_relations_family",
        table_name="document_relations",
    )

    # 3) Удаляем сам столбец family_id из document_relations
    op.drop_column("document_relations", "family_id")


def downgrade() -> None:
    # 1) Добавляем колонку family_id обратно
    op.add_column(
        "document_relations",
        sa.Column("family_id", sa.dialects.postgresql.UUID(), nullable=True),
    )

    # 2) Восстанавливаем индекс
    op.create_index(
        "idx_relations_family",
        "document_relations",
        ["family_id"],
        unique=False,
        postgresql_where=sa.text("family_id IS NOT NULL"),
    )

    # 3) Восстанавливаем внешний ключ на families.id
    op.create_foreign_key(
        "document_relations_family_id_fkey",
        "document_relations",
        "families",
        ["family_id"],
        ["id"],
        ondelete="SET NULL",
    )