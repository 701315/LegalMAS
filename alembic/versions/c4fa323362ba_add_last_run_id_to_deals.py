"""add last_run_id to deals

Revision ID: c4fa323362ba
Revises: ea01f9cffd39
Create Date: 2026-03-05 13:34:30.041039

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4fa323362ba'
down_revision: Union[str, None] = 'ea01f9cffd39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deals",
        sa.Column("last_run_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_deals_last_run_id_runs",
        "deals",
        "runs",
        ["last_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_deals_last_run_id_runs", "deals", type_="foreignkey")
    op.drop_column("deals", "last_run_id")