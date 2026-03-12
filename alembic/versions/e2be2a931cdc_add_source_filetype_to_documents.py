"""add source filetype to documents

Revision ID: e2be2a931cdc
Revises: 9cfee2741dc5
Create Date: 2026-03-12 09:03:21.149605

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2be2a931cdc'
down_revision: Union[str, None] = '9cfee2741dc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "source_extension",
            sa.String(length=20),
            nullable=True,
            comment="Original file extension including dot, e.g. '.pdf', '.docx'",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "source_filetype",
            sa.String(length=50),
            nullable=True,
            comment="Internal file type from file_validator: pdf, docx, xlsx, image, etc.",
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "source_filetype")
    op.drop_column("documents", "source_extension")