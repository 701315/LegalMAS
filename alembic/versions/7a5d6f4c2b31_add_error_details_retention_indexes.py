"""add error_details retention partial indexes

Revision ID: 7a5d6f4c2b31
Revises: d53629bc872c
Create Date: 2026-07-02 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a5d6f4c2b31"
down_revision: Union[str, None] = "d53629bc872c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY нельзя выполнять внутри transaction block,
    # поэтому используем autocommit_block().
    with op.get_context().autocommit_block():
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_documents_error_details_retention
            ON documents (updated_at)
            WHERE processing_error_details IS NOT NULL
        """)

        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_runs_error_details_retention
            ON runs (created_at)
            WHERE error_details IS NOT NULL
        """)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("""
            DROP INDEX CONCURRENTLY IF EXISTS idx_documents_error_details_retention
        """)
        op.execute("""
            DROP INDEX CONCURRENTLY IF EXISTS idx_runs_error_details_retention
        """)


        