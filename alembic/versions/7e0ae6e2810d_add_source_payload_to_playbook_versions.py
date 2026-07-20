"""add source_payload to playbook_versions

Revision ID: 7e0ae6e2810d
Revises: 8049a53a083a
Create Date: 2026-07-20 16:10:42.046406

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '7e0ae6e2810d'
down_revision: Union[str, None] = '8049a53a083a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "playbook_versions"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "source_payload",
            JSONB,
            nullable=True,
            comment=(
                "Canonical source spec used to build this version. "
                "NULL for legacy versions."
            ),
        ),
    )

    op.add_column(
        TABLE,
        sa.Column(
            "source_payload_sha256",
            sa.String(64),
            nullable=True,
            comment="SHA256 of canonical JSON serialization of source_payload.",
        ),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "source_payload_sha256")
    op.drop_column(TABLE, "source_payload")