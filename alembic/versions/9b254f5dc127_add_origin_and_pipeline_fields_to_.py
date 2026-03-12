"""add origin and pipeline fields to document_versions

Revision ID: 9b254f5dc127
Revises: e2be2a931cdc
Create Date: 2026-03-12 12:06:15.839433

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b254f5dc127'
down_revision: Union[str, None] = 'e2be2a931cdc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column(
            "origin_filetype",
            sa.String(length=50),
            nullable=True,
            comment=(
                "Internal type of the file this version originates from: "
                "pdf, docx, image, etc."
            ),
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "origin_extension",
            sa.String(length=20),
            nullable=True,
            comment="Original extension of source file, e.g. '.pdf', '.docx', '.png'",
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "pipeline_strategy",
            sa.String(length=64),
            nullable=True,
            comment=(
                "High-level processing route: "
                "pdf_native, pdf_ocr, docx_via_pdf_native, docx_via_pdf_ocr, image_ocr, etc."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "pipeline_strategy")
    op.drop_column("document_versions", "origin_extension")
    op.drop_column("document_versions", "origin_filetype")