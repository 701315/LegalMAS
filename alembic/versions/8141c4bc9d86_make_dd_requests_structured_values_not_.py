"""make dd_requests.structured_values not null

Revision ID: 8141c4bc9d86
Revises: 7e912021cadd
Create Date: 2026-03-05 15:59:28.888206

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8141c4bc9d86'
down_revision: Union[str, None] = '7e912021cadd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1) Нормализуем NULL -> []
    op.execute(
        "UPDATE dd_requests SET structured_values = '[]'::json WHERE structured_values IS NULL;"
    )

    # 2) Меняем тип json -> jsonb (если хочешь унифицировать под JSONB)
    op.alter_column(
        "dd_requests",
        "structured_values",
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="structured_values::jsonb",
        existing_type=postgresql.JSON(astext_type=sa.Text()),
    )

    # 3) Ставим NOT NULL и дефолт []::jsonb
    op.alter_column(
        "dd_requests",
        "structured_values",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.execute(
        "ALTER TABLE dd_requests ALTER COLUMN structured_values SET DEFAULT '[]'::jsonb;"
    )


def downgrade():
    # 1) Снимаем NOT NULL
    op.alter_column(
        "dd_requests",
        "structured_values",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )

    # 2) Убираем дефолт
    op.execute(
        "ALTER TABLE dd_requests ALTER COLUMN structured_values DROP DEFAULT;"
    )

    # 3) Возвращаем тип json
    op.alter_column(
        "dd_requests",
        "structured_values",
        type_=postgresql.JSON(astext_type=sa.Text()),
        postgresql_using="structured_values::json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
    )
