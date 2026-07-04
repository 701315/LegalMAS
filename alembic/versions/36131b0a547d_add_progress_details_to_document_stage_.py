"""add progress_details to document_stage_executions

Revision ID: 36131b0a547d
Revises: 7a5d6f4c2b31
Create Date: 2026-07-04 16:20:52.844242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '36131b0a547d'
down_revision: Union[str, None] = '7a5d6f4c2b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_stage_executions",
        sa.Column(
            "progress_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Live progress snapshot for long-running stages.",
        ),
    )


def downgrade() -> None:
    op.drop_column("document_stage_executions", "progress_details")

    