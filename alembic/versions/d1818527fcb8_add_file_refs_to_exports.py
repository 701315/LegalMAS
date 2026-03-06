"""add file_refs to exports

Revision ID: d1818527fcb8
Revises: 8141c4bc9d86
Create Date: 2026-03-05 19:01:40.630658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd1818527fcb8'
down_revision: Union[str, None] = '8141c4bc9d86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "exports",
        sa.Column(
            "file_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

def downgrade():
    op.drop_column("exports", "file_refs")