"""add_user_ui_locale

Revision ID: 9317c6d16767
Revises: 8f0b10ab5056
Create Date: 2026-09-02 13:23:13.882109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9317c6d16767'
down_revision: Union[str, None] = '8f0b10ab5056'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем колонку ui_locale в таблицу users
    op.add_column(
        "users",
        sa.Column(
            "ui_locale",
            sa.String(length=35),
            nullable=True,
        ),
    )
    # 2. Backfill: устанавливаем язык 'ru' всем существующим пользователям
    op.execute("UPDATE users SET ui_locale = 'ru' WHERE ui_locale IS NULL")


def downgrade() -> None:
    # Удаляем колонку ui_locale при откате миграции
    op.drop_column("users", "ui_locale")

    