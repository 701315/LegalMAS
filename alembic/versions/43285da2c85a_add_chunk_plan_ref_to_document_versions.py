"""add chunk_plan_ref to document_versions

Revision ID: 43285da2c85a
Revises: a4f64f13e4cc
Create Date: 2026-06-02 14:34:37.892827

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43285da2c85a'
down_revision: Union[str, None] = 'a4f64f13e4cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column(
            "chunk_plan_ref",
            sa.String(length=1000),
            nullable=True,
            comment="S3 URI to chunk_plan.json — Phase 10 Chunk Planner output.",
        ),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "chunk_plan_ref")
    