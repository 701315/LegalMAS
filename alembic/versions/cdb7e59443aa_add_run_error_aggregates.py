"""add run error aggregates

Revision ID: cdb7e59443aa
Revises: c50a85d25f80
Create Date: 2026-03-13 15:20:52.232128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdb7e59443aa'
down_revision: Union[str, None] = 'c50a85d25f80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "has_errors",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "failed_docs_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "quarantine_docs_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # опционально можно убрать server_default после заполнения,
    # но для простоты можно оставить как есть


def downgrade() -> None:
    op.drop_column("runs", "quarantine_docs_count")
    op.drop_column("runs", "failed_docs_count")
    op.drop_column("runs", "has_errors")