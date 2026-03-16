"""add model_config_id to deals

Revision ID: bc12d8951360
Revises: 56ba2c71cf23
Create Date: 2026-03-16 20:21:15.354389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc12d8951360'
down_revision: Union[str, None] = '56ba2c71cf23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем колонку model_config_id (nullable, чтобы не ломать существующие данные)
    op.add_column(
        "deals",
        sa.Column("model_config_id", sa.UUID(), nullable=True),
    )

    # 2. Создаём внешний ключ на model_configs.id с ondelete SET NULL
    op.create_foreign_key(
        "fk_deals_model_config_id_model_configs",
        "deals",
        "model_configs",
        ["model_config_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Откатываем в обратном порядке: сначала FK, потом колонку
    op.drop_constraint(
        "fk_deals_model_config_id_model_configs",
        "deals",
        type_="foreignkey",
    )
    op.drop_column("deals", "model_config_id")