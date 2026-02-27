"""add updated_at to document_families

Revision ID: 97dfb4f0db7a
Revises: 5a1bd4eb9ac2
Create Date: 2026-02-27 23:10:59.520031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97dfb4f0db7a'
down_revision: Union[str, None] = '5a1bd4eb9ac2'
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