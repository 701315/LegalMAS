"""add classification_requires_review to documents

Revision ID: fb200f5804b1
Revises: 4338dc36377d
Create Date: 2026-03-31 18:12:10.999504

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb200f5804b1'
down_revision: Union[str, None] = '4338dc36377d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1. Проставить default для уже существующих строк, если вдруг NULL
    op.execute(
        "UPDATE documents SET classification_requires_review = FALSE "
        "WHERE classification_requires_review IS NULL"
    )

    # 2. Запретить NULL и задать server_default
    op.alter_column(
        "documents",
        "classification_requires_review",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default="false",
    )


def downgrade():
    # Откат: снова разрешаем NULL и убираем server_default
    op.alter_column(
        "documents",
        "classification_requires_review",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )