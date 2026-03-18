"""add playbook_version_id to check_results

Revision ID: e65bbfe5dbff
Revises: bc12d8951360
Create Date: 2026-03-18 09:49:25.430295

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e65bbfe5dbff'
down_revision: Union[str, None] = 'bc12d8951360'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "check_results",
        sa.Column("playbook_version_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_check_results_playbook_version",
        "check_results",
        "playbook_versions",
        ["playbook_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_check_results_playbook_version",
        "check_results",
        type_="foreignkey",
    )
    op.drop_column("check_results", "playbook_version_id")