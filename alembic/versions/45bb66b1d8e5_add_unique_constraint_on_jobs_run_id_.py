"""add unique constraint on jobs run_id task_type

Revision ID: 45bb66b1d8e5
Revises: 1b1b282d6dc3
Create Date: 2026-04-17 11:40:16.789859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45bb66b1d8e5'
down_revision: Union[str, None] = '1b1b282d6dc3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Уникальное ограничение на пару (run_id, task_type) в jobs.
    # Гарантирует, что для одного Run каждая task_type (в т.ч. run_deal_checks)
    # может быть создана не более одного раза.
    op.create_unique_constraint(
        "uq_jobs_run_id_task_type",
        "jobs",
        ["run_id", "task_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_jobs_run_id_task_type",
        "jobs",
        type_="unique",
    )
    