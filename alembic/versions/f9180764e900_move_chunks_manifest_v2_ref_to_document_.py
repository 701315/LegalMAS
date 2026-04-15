"""move chunks_manifest_v2_ref to document_versions

Revision ID: f9180764e900
Revises: c1bb50b2f02b
Create Date: 2026-04-15 19:40:06.349878

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9180764e900'
down_revision: Union[str, None] = 'c1bb50b2f02b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # только chunks_manifest_v2_ref в document_versions
    op.add_column(
        "document_versions",
        sa.Column(
            "chunks_manifest_v2_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to chunks_manifest_v2.json — version-level file manifest "
                "for CHUNKS v2."
            ),
        ),
    )

    # и дроп лишней колонки из documents
    op.drop_column("documents", "chunks_manifest_v2_ref")


def downgrade() -> None:
    # при откате возвращаем колонку в documents
    op.add_column(
        "documents",
        sa.Column(
            "chunks_manifest_v2_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to chunks_manifest_v2.json — file-level manifest (legacy location)."
            ),
        ),
    )

    # и убираем из document_versions
    op.drop_column("document_versions", "chunks_manifest_v2_ref")