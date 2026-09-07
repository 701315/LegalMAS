"""add_default_output_locale_to_users

Revision ID: 818879bb7d5e
Revises: 7c8ee3a8242c
Create Date: 2026-09-07 07:24:27.394188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '818879bb7d5e'
down_revision: Union[str, None] = '7c8ee3a8242c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'default_output_locale',
            sa.String(length=10),
            nullable=True,
            comment=(
                "Preferred output locale for result presentations (BCP 47: 'en', 'ru'). "
                "Separate axis from ui_locale (Invariant #5). "
                "Used as level-2 fallback in locale resolution chain when "
                "no explicit presentation_locale is requested. "
                "Validated against result_locales.json at write/update time."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'default_output_locale')


    