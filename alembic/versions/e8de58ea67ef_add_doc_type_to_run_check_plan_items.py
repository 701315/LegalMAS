"""add doc_type to run_check_plan_items

Revision ID: e8de58ea67ef
Revises: 0e7b30fb1e7a
Create Date: 2026-07-21 07:05:14.239825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8de58ea67ef'
down_revision: Union[str, None] = '0e7b30fb1e7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_check_plan_items",
        sa.Column(
            "doc_type",
            sa.String(length=100),
            nullable=True,
            comment="Resolved document type at planning time for audit/debug/coverage",
        ),
    )


def downgrade() -> None:
    op.drop_column("run_check_plan_items", "doc_type")

    