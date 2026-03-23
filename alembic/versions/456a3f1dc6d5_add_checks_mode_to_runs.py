"""add checks_mode to runs

Revision ID: 456a3f1dc6d5
Revises: 9b4e4d1eae41
Create Date: 2026-03-23 11:07:13.991581

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '456a3f1dc6d5'
down_revision: Union[str, None] = '9b4e4d1eae41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем колонку checks_mode в таблицу runs.
    # Храним строку с режимом проверок:
    #   - 'global_only'
    #   - 'doc_type_only'
    #   - 'global_and_doc_type' (значение по умолчанию).
    op.add_column(
        "runs",
        sa.Column(
            "checks_mode",
            sa.String(length=50),
            nullable=False,
            server_default="global_and_doc_type",
            comment=(
                "Режим проверок для этого Run: "
                "global_only / doc_type_only / global_and_doc_type"
            ),
        ),
    )

    # После того как колонка создана и старые строки получили default,
    # можно убрать server_default, чтобы в дальнейшем писать значение из приложения.
    op.alter_column(
        "runs",
        "checks_mode",
        server_default=None,
    )


def downgrade() -> None:
    # При откате просто удаляем колонку checks_mode из runs.
    op.drop_column("runs", "checks_mode")
    