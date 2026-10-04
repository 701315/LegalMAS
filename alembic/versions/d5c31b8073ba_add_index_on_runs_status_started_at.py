"""add index on runs status started_at

Revision ID: d5c31b8073ba
Revises: 7ea844f630e0
Create Date: 2026-09-16 16:44:04.875292

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5c31b8073ba'
down_revision: str | None = 'e8f9c1a4b2d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_runs_status_started_at",
        "runs",
        ["status", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_runs_status_started_at", table_name="runs")
