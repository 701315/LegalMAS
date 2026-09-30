"""add dd_request_addressee to check_result_presentations

Revision ID: e8f9c1a4b2d3
Revises: d654fa9a6808
Create Date: 2026-09-30 18:00:00.000000

Locale-specific addressee for the DD request text.

Before: only dd_request_text (locale-specific body of the request)
was stored in CheckResultPresentation. Explicit YAML dd_request_templates
carry both text and addressee — the addressee also needs LLM translation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8f9c1a4b2d3"
down_revision: Union[str, None] = "d654fa9a6808"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_result_presentations",
        sa.Column(
            "dd_request_addressee",
            sa.String(length=500),
            nullable=True,
            comment="Locale-specific DD request addressee when applicable.",
        ),
    )


def downgrade() -> None:
    op.drop_column("check_result_presentations", "dd_request_addressee")
