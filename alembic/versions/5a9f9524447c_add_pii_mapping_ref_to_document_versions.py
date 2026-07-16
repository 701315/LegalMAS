"""add pii_mapping_ref to document_versions

Revision ID: 5a9f9524447c
Revises: 36131b0a547d
Create Date: 2026-07-16 18:50:34.417903

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a9f9524447c'
down_revision: Union[str, None] = '36131b0a547d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column(
            "pii_mapping_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to encrypted PII mapping artifact (.enc). "
                "Written by pii_sanitizer after successful sanitization. "
                "Required for PII reveal/restore operations. "
                "Path: ArtifactPath.pii_mapping(tenant_id, deal_id, document_id)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "pii_mapping_ref")