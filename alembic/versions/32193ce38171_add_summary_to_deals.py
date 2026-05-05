"""add summary to deals

Revision ID: 32193ce38171
Revises: ea852ac0f3e2
Create Date: 2026-05-05 09:53:49.452836

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32193ce38171'
down_revision: Union[str, None] = 'ea852ac0f3e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deals",
        sa.Column(
            "summary",
            sa.Text(),
            nullable=True,
            comment="User-facing project summary maintained by project team",
        ),
    )


def downgrade() -> None:
    op.drop_column("deals", "summary")

    