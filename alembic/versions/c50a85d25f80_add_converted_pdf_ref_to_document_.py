from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c50a85d25f80"
down_revision: Union[str, None] = "c302e260857c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляем колонку converted_pdf_ref в document_versions.

    Эта колонка хранит ссылку на PDF, который получен после конвертации
    офисного файла (DOCX, DOC и т.п.) в PDF.
    """
    op.add_column(
        "document_versions",
        sa.Column(
            "converted_pdf_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to PDF converted from original office format (DOCX, DOC, etc.). "
                "Если заполнено — extract_worker использует его вместо original_ref. "
                "Для исходных PDF всегда NULL."
            ),
        ),
    )


def downgrade() -> None:
    """
    Откатываем изменения: убираем колонку converted_pdf_ref.
    """
    op.drop_column("document_versions", "converted_pdf_ref")
