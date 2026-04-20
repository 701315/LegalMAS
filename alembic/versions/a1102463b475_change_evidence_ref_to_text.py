"""change evidence_ref to text

Revision ID: a1102463b475
Revises: 45bb66b1d8e5
Create Date: 2026-04-20 15:10:52.898692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1102463b475'
down_revision: Union[str, None] = '45bb66b1d8e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # В PostgreSQL переход VARCHAR → TEXT безопасен:
    # типы имеют совместимое хранилище, данных не теряем.
    op.alter_column(
        "check_results",
        "evidence_ref",
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=True,
        comment="S3 URI or inline evidence snippet; may be long text",
    )


def downgrade() -> None:
    # Обратный переход TEXT → VARCHAR(1000) потенциально может обрезать
    # длинные значения. Выполняем его только если точно понимаем последствия.
    op.alter_column(
        "check_results",
        "evidence_ref",
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=True,
        comment="S3 URI or inline evidence snippet",
    )