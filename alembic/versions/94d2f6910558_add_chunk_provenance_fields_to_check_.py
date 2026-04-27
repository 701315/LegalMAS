"""add chunk provenance fields to check_results

Revision ID: 94d2f6910558
Revises: 39923a1c6024
Create Date: 2026-04-27 06:48:01.797324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94d2f6910558'
down_revision: Union[str, None] = '39923a1c6024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_results",
        sa.Column(
            "chunk_id",
            sa.String(length=500),
            nullable=True,
            comment=(
                "Full chunk identifier from retrieval/chunking layer, "
                "e.g. {doc_id}:{segment_id}:{clause_uid}:{sub_idx}"
            ),
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=True,
            comment=(
                "Sub-chunk index within clause or segment. "
                "0 = whole clause/default chunk, 1+ = sized subchunk"
            ),
        ),
    )

    op.create_index(
        "idx_results_chunk_id",
        "check_results",
        ["chunk_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_results_chunk_id", table_name="check_results")
    op.drop_column("check_results", "chunk_index")
    op.drop_column("check_results", "chunk_id")

    