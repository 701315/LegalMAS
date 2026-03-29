"""add primary_language to deals

Revision ID: 3c74d85e249d
Revises: b147f8e648e7
Create Date: 2026-03-28 19:56:04.730024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c74d85e249d'
down_revision: Union[str, None] = 'b147f8e648e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deals",
        sa.Column(
            "primary_language",
            sa.String(length=10),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("deals", "primary_language")