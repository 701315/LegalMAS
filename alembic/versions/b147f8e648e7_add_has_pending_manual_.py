"""add has_pending_manual_reclassifications to deals

Revision ID: b147f8e648e7
Revises: 6ca569b3d911
Create Date: 2026-03-23 17:56:49.984791

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b147f8e648e7'
down_revision: Union[str, None] = '6ca569b3d911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем булевый флаг незакрытых ручных переклассификаций в deals.
    op.add_column(
        "deals",
        sa.Column(
            "has_pending_manual_reclassifications",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "True — есть документы, переклассифицированные вручную, "
                "и анализ по сделке ещё не был перезапущен после этого"
            ),
        ),
    )

    # После добавления можно убрать server_default, чтобы схема была чище,
    # но это не обязательно. Если хочешь — раскомментируй:
    # op.alter_column(
    #     "deals",
    #     "has_pending_manual_reclassifications",
    #     server_default=None,
    # )


def downgrade() -> None:
    # При откате просто удаляем колонку.
    op.drop_column("deals", "has_pending_manual_reclassifications")