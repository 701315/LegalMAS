"""drop legacy chunks_ref from document_versions

Revision ID: 1b1b282d6dc3
Revises: 6e0203699b46
Create Date: 2026-04-16 10:39:41.125002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b1b282d6dc3'
down_revision: Union[str, None] = '6e0203699b46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("document_versions", "chunks_ref")


def downgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column(
            "chunks_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "LEGACY: S3 URI to chunk snapshot JSON "
                "(section/clause/subclause) in old schema v1.\n"
                "\n"
                "Это историческое поле старого формата чанков и больше не является\n"
                "рабочим контрактом для retrieval/checks.\n"
                "Текущая архитектура CHUNKS v2 должна использовать:\n"
                "- DocumentSegment.segment_chunks_ref (чанки по сегментам)\n"
                "- chunks_manifest_v2_ref (file-level манифест чанков)\n"
            ),
        ),
    )