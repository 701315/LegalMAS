"""add primary layout refs to document_versions

Revision ID: 0c899c657e94
Revises: fb200f5804b1
Create Date: 2026-04-01 07:31:08.390409

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c899c657e94'
down_revision: Union[str, None] = 'fb200f5804b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "document_versions",
        sa.Column(
            "layout_primary_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to primary-language-only layout JSON. "
                "Формируется после определения языков документа и выбора основного "
                "языка сделки."
            ),
        ),
    )

    op.add_column(
        "document_versions",
        sa.Column(
            "layout_primary_sanitized_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to primary-language-only PII-sanitized layout JSON. "
                "Это основной layout для downstream-анализа."
            ),
        ),
    )


def downgrade():
    op.drop_column("document_versions", "layout_primary_sanitized_ref")
    op.drop_column("document_versions", "layout_primary_ref")
    