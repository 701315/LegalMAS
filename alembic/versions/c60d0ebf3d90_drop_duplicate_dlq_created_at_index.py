"""drop duplicate dlq created_at index

Revision ID: c60d0ebf3d90
Revises: a65580b211a0
Create Date: 2026-05-18 14:13:29.984573

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c60d0ebf3d90'
down_revision: Union[str, None] = 'a65580b211a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("dlq_records_created_at_idx", table_name="dlq_records")


def downgrade() -> None:
    op.create_index(
        "dlq_records_created_at_idx",
        "dlq_records",
        ["created_at"],
        unique=False,
    )