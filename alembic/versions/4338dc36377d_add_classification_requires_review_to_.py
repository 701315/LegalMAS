"""add classification_requires_review to documents

Revision ID: 4338dc36377d
Revises: 3c74d85e249d
Create Date: 2026-03-31 16:12:21.352345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4338dc36377d'
down_revision: Union[str, None] = '3c74d85e249d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Для непрофессионального программиста:
    # - добавляем новое булево поле в таблицу documents;
    # - nullable=True, чтобы не ломать старые записи.
    op.add_column(
        "documents",
        sa.Column(
            "classification_requires_review",
            sa.Boolean(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "classification_requires_review")