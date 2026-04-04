"""add primary_source_ref to document_versions

Revision ID: a43e6cd43e8d
Revises: 0c899c657e94
Create Date: 2026-04-03 17:01:09.504576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a43e6cd43e8d'
down_revision: Union[str, None] = '0c899c657e94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column(
            "primary_source_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to primary-language-only source file (usually PDF). "
                "Built before extract; extract_worker should prefer this ref."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "primary_source_ref")