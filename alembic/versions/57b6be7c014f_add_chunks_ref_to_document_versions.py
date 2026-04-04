"""add chunks_ref to document_versions

Revision ID: 57b6be7c014f
Revises: a43e6cd43e8d
Create Date: 2026-04-03 19:19:31.632763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57b6be7c014f'
down_revision: Union[str, None] = 'a43e6cd43e8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column(
            "chunks_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to canonical chunk snapshot JSON "
                "(section/clause/subclause) for this version."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "chunks_ref")