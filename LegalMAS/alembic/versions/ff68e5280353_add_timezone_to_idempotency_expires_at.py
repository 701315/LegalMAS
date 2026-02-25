"""add_timezone_to_idempotency_expires_at

Revision ID: ff68e5280353
Revises: 56c6d7ac61fd
Create Date: 2026-02-24 15:16:41.370392

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ff68e5280353'  # замените на реальный ID из имени файла
down_revision: Union[str, None] = '56c6d7ac61fd'  # замените на реальный ID из down_revision в файле
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Изменяем тип колонки с сохранением данных (считаем, что были в UTC)
    op.execute(
        "ALTER TABLE idempotency_keys "
        "ALTER COLUMN expires_at "
        "TYPE TIMESTAMP WITH TIME ZONE "
        "USING expires_at AT TIME ZONE 'UTC'"
    )


def downgrade() -> None:
    # Обратно к naive UTC
    op.execute(
        "ALTER TABLE idempotency_keys "
        "ALTER COLUMN expires_at "
        "TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING expires_at AT TIME ZONE 'UTC'"
    )