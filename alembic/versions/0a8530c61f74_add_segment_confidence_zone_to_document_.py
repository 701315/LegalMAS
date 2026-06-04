"""add segment_confidence_zone to document_segments

Revision ID: 0a8530c61f74
Revises: 2df8d541f09d
Create Date: 2026-06-03 20:00:50.706455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a8530c61f74'
down_revision: Union[str, None] = '2df8d541f09d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_segments",
        sa.Column(
            "segment_confidence_zone",
            sa.String(length=20),
            nullable=True,
            comment="Confidence zone for segment classification result: high / medium / low / very_low",
        ),
    )


def downgrade() -> None:
    op.drop_column("document_segments", "segment_confidence_zone")