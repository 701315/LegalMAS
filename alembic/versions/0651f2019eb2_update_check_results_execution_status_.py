"""update check_results execution_status comments

Revision ID: 0651f2019eb2
Revises: 1da1ebbdbfce
Create Date: 2026-04-20 16:41:28.874694

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0651f2019eb2'
down_revision: Union[str, None] = '1da1ebbdbfce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Обновляем комментарий у execution_status
    op.execute(
        """
        COMMENT ON COLUMN check_results.execution_status IS
        'Technical execution status of this check: PENDING, RUNNING, SUCCESS, COMPUTE_FAILED, PERSIST_FAILED, TIMEOUT, FAILED(legacy)';
        """
    )

    # 2. Обновляем комментарий у finished_at
    op.execute(
        """
        COMMENT ON COLUMN check_results.finished_at IS
        'When this check execution reached a terminal state';
        """
    )

    # 3. Обновляем комментарий у error_details
    op.execute(
        """
        COMMENT ON COLUMN check_results.error_details IS
        'Error/timeout details for COMPUTE_FAILED, PERSIST_FAILED, TIMEOUT and legacy FAILED executions';
        """
    )


def downgrade() -> None:
    # Откатываем комментарии к прошлым версиям (если они были),
    # либо очищаем — зависит от твоего желания.
    # В качестве простого варианта можно вернуть более общий текст.

    op.execute(
        """
        COMMENT ON COLUMN check_results.execution_status IS
        'Execution status of this check';
        """
    )

    op.execute(
        """
        COMMENT ON COLUMN check_results.finished_at IS
        'When this check execution finished (any terminal state)';
        """
    )

    op.execute(
        """
        COMMENT ON COLUMN check_results.error_details IS
        'Error/timeout details for FAILED/TIMEOUT executions';
        """
    )