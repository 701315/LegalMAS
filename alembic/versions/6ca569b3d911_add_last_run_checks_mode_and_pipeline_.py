"""add last_run_checks_mode and pipeline_strategy to deals

Revision ID: 6ca569b3d911
Revises: 456a3f1dc6d5
Create Date: 2026-03-23 13:47:41.258588

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ca569b3d911'
down_revision: Union[str, None] = '456a3f1dc6d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Создаём enum-тип для режима проверок, если его ещё нет.
    # В большинстве случаев Alembic сам создаст тип при первом использовании Enum,
    # но явное создание даёт более предсказуемый результат.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'run_checks_mode') THEN "
        "CREATE TYPE run_checks_mode AS ENUM ('global_only', 'doc_type_only', 'global_and_doc_type'); "
        "END IF; "
        "END $$;"
    )

    # 2. Добавляем колонку last_run_checks_mode в deals
    op.add_column(
        "deals",
        sa.Column(
            "last_run_checks_mode",
            sa.Enum(
                "global_only",
                "doc_type_only",
                "global_and_doc_type",
                name="run_checks_mode",
            ),
            nullable=True,
            comment=(
                "Checks mode of the latest run: "
                "global_only / doc_type_only / global_and_doc_type"
            ),
        ),
    )

    # 3. Добавляем колонку last_run_pipeline_strategy в deals
    op.add_column(
        "deals",
        sa.Column(
            "last_run_pipeline_strategy",
            sa.String(length=100),
            nullable=True,
            comment="Pipeline strategy of the latest run (e.g. REUSE_STRUCTURE, FULL_RERUN)",
        ),
    )


def downgrade() -> None:
    # При откате удаляем колонки.
    op.drop_column("deals", "last_run_pipeline_strategy")
    op.drop_column("deals", "last_run_checks_mode")

    # Тип run_checks_mode можно оставить, если его используют другие таблицы (например, runs).
    # Если он используется только в deals, можно удалить:
    # op.execute("DROP TYPE IF EXISTS run_checks_mode;")