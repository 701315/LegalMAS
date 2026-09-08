"""add_localized_structured_data_to_presentations

Revision ID: 41a3ed58d450
Revises: 2b76dda7061a
Create Date: 2026-09-08 13:36:34.354770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '41a3ed58d450'
down_revision: Union[str, None] = '2b76dda7061a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_result_presentations",
        sa.Column(
            "localized_structured_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Locale-specific translated structured_data field values. "
                "Maps field_name -> translated free-text value for Matrix cells."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("check_result_presentations", "localized_structured_data")