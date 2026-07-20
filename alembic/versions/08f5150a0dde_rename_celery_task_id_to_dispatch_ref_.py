"""rename celery_task_id to dispatch_ref in run_check_plan_items

Revision ID: 08f5150a0dde
Revises: bc56177ec084
Create Date: 2026-07-20 09:33:24.507951

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08f5150a0dde'
down_revision: Union[str, None] = 'bc56177ec084'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "run_check_plan_items",
        "celery_task_id",
        new_column_name="dispatch_ref",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "run_check_plan_items",
        "dispatch_ref",
        new_column_name="celery_task_id",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )

    