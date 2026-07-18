"""add instruction_versions to runs

Revision ID: 2798a8a88dfb
Revises: 04a49a9094d0
Create Date: 2026-07-17 23:02:15.939102

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2798a8a88dfb'
down_revision: Union[str, None] = '04a49a9094d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "instruction_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Фиксированные версии инструкций для этого Run: {doc_type: version_id}",
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "instruction_versions")

    