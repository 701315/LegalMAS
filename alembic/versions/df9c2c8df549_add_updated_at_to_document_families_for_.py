"""add updated_at to document_families for real

Revision ID: df9c2c8df549
Revises: d58a5baaaa7a
Create Date: 2026-07-24 18:32:49.861845

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df9c2c8df549'
down_revision: Union[str, None] = 'd58a5baaaa7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_families",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("document_families", "updated_at")


    