"""add run pipeline strategy

Revision ID: 6df6ab5ae7c7
Revises: cdb7e59443aa
Create Date: 2026-03-13 16:21:52.124612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6df6ab5ae7c7'
down_revision: Union[str, None] = 'cdb7e59443aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "pipeline_strategy",
            sa.String(length=50),
            nullable=False,
            server_default="REUSE_STRUCTURE",
        ),
    )
    # опционально: убрать server_default после применения миграции,
    # если хочешь, чтобы дальше значение всегда задавалось приложением


def downgrade() -> None:
    op.drop_column("runs", "pipeline_strategy")