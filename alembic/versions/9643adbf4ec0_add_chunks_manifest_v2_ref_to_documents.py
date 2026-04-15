"""add chunks_manifest_v2_ref to documents

Revision ID: 9643adbf4ec0
Revises: f9070b8a76b8
Create Date: 2026-04-15 13:04:44.293309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9643adbf4ec0'
down_revision: Union[str, None] = 'f9070b8a76b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "chunks_manifest_v2_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to chunks_manifest_v2.json — file-level манифест чанков.\n"
                "\n"
                "Для непрофессионального программиста:\n"
                "- Это один JSON-файл, который описывает весь набор чанков по файлу,\n"
                "  но сами тексты чанков лежат по ссылкам segment_chunks_ref "
                "в таблице DocumentSegment.\n"
                "- retrieval/checks/LLM должны начинать чтение именно с этого файла,\n"
                "  а не с legacy chunks_ref.\n"
                "\n"
                "NULL означает, что CHUNKS v2 ещё не отработали для этой версии."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "chunks_manifest_v2_ref")
    