"""make document_families created_at not null

Revision ID: cb4537a60695
Revises: 87fd971b1eb4
Create Date: 2026-02-27 23:33:39.055142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb4537a60695'
down_revision: Union[str, None] = '87fd971b1eb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE document_families SET created_at = now() WHERE created_at IS NULL;"
    )
    op.alter_column(
        "document_families",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

def downgrade() -> None:
    op.alter_column(
        "document_families",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
