"""add language discovery fields to deals and documents

Revision ID: 6960a5a69d79
Revises: 48052f95895c
Create Date: 2026-05-11 15:34:06.299222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6960a5a69d79'
down_revision: Union[str, None] = '48052f95895c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # documents.detected_languages
    op.add_column(
        "documents",
        sa.Column(
            "detected_languages",
            postgresql.ARRAY(sa.String(length=10)),
            nullable=True,
            comment="All languages detected in this document, e.g. ['ru', 'en'].",
        ),
    )

    # documents.language_detection_status
    op.add_column(
        "documents",
        sa.Column(
            "language_detection_status",
            sa.String(length=50),
            nullable=True,
            comment=(
                "Status of pre-run language discovery for this document: "
                "pending / processing / completed / failed"
            ),
        ),
    )

    # deals.language_discovery_status
    op.add_column(
        "deals",
        sa.Column(
            "language_discovery_status",
            sa.String(length=50),
            nullable=True,
            comment=(
                "Status of pre-run language discovery for this deal: "
                "pending / processing / completed / partial / failed"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("deals", "language_discovery_status")
    op.drop_column("documents", "language_detection_status")
    op.drop_column("documents", "detected_languages")