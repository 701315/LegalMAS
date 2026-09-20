"""add_canonical_lifecycle_fields_to_check_results

Revision ID: 7c8ee3a8242c
Revises: 73923c7b37a3
Create Date: 2026-09-07 04:34:04.271045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c8ee3a8242c'
down_revision: Union[str, None] = '73923c7b37a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_results",
        sa.Column(
            "canonical_locale",
            sa.String(35),
            nullable=True,
            comment=(
                "Target language in which the canonical legal analysis was conducted. "
                "Frozen snapshot of Run.analysis_language."
            ),
        ),
    )
    op.add_column(
        "check_results",
        sa.Column(
            "content_revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment=(
                "Monotonic revision counter of display-facing canonical content. "
                "Increments whenever canonical_content_hash changes."
            ),
        ),
    )
    op.add_column(
        "check_results",
        sa.Column(
            "canonical_content_hash",
            sa.String(64),
            nullable=True,
            comment=(
                "Deterministic SHA-256 fingerprint of human-facing canonical fields "
                "(check_name, display_text, review_message) used to detect content drift."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("check_results", "canonical_content_hash")
    op.drop_column("check_results", "content_revision")
    op.drop_column("check_results", "canonical_locale")

    