"""add published_at to playbook_versions

Revision ID: cdb948125d37
Revises: 7e0ae6e2810d
Create Date: 2026-07-20 16:35:39.373502

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdb948125d37'
down_revision: Union[str, None] = '7e0ae6e2810d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "playbook_versions",
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this version was published (immutable).",
        ),
    )

def downgrade() -> None:
    op.drop_column("playbook_versions", "published_at")