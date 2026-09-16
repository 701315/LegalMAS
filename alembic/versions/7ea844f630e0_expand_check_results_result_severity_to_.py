"""expand_check_results_result_severity_to_varchar50

Revision ID: 7ea844f630e0
Revises: ebd9270e6030
Create Date: 2026-09-16 07:09:09.205614

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ea844f630e0'
down_revision: Union[str, None] = 'ebd9270e6030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Расширяем колонки result и severity с VARCHAR(20) до VARCHAR(50)
    # для поддержки длинных кодов результатов (например, missing_required_clause).
    op.alter_column(
        'check_results',
        'result',
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )
    op.alter_column(
        'check_results',
        'severity',
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Откат: возвращаем VARCHAR(20).
    # ВНИМАНИЕ: если в БД уже есть значения длиннее 20 символов,
    # downgrade завершится ошибкой. В этом случае нужно сначала
    # усечь данные вручную.
    op.alter_column(
        'check_results',
        'severity',
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        'check_results',
        'result',
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )