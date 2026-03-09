"""add updated_at to deal_members

Revision ID: 30190b117152
Revises: 5ff0e8b359b9
Create Date: 2026-03-09 22:43:20.196627

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30190b117152'
down_revision: Union[str, None] = '5ff0e8b359b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deal_members",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("deal_members", "updated_at")