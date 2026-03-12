"""add playbook_version_id to documents

Revision ID: c302e260857c
Revises: 9b254f5dc127
Create Date: 2026-03-12 20:36:15.520498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c302e260857c'
down_revision: Union[str, None] = '9b254f5dc127'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("playbook_version_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_playbook_version",
        "documents",
        "playbook_versions",
        ["playbook_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_documents_playbook_version",
        "documents",
        type_="foreignkey",
    )
    op.drop_column("documents", "playbook_version_id")