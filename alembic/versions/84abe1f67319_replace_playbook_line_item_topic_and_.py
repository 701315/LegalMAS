"""replace playbook line item topic and check codes with instruction_code

Revision ID: 84abe1f67319
Revises: fc3f437b74d7
Create Date: 2026-07-21 21:21:25.320862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84abe1f67319'
down_revision: Union[str, None] = 'fc3f437b74d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем новую колонку instruction_code как nullable=True.
    # Сначала колонка должна быть nullable, иначе PostgreSQL упадёт на существующих строках.
    op.add_column(
        "playbook_line_items",
        sa.Column(
            "instruction_code",
            sa.String(length=200),
            nullable=True,
            comment="Canonical instruction code from global instruction catalog.",
        ),
    )

    # 2. Переносим данные из legacy check_code в instruction_code.
    op.execute(
        """
        UPDATE playbook_line_items
        SET instruction_code = check_code
        WHERE check_code IS NOT NULL
        """
    )

    # 3. Fail-fast проверка: после переноса не должно остаться NULL.
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM playbook_line_items
            WHERE instruction_code IS NULL
            """
        )
    )
    missing_count = int(result.scalar() or 0)

    if missing_count > 0:
        raise RuntimeError(
            f"Migration aborted: {missing_count} playbook_line_items rows "
            "have no check_code to migrate into instruction_code."
        )

    # 4. Делаем instruction_code обязательным.
    op.alter_column(
        "playbook_line_items",
        "instruction_code",
        existing_type=sa.String(length=200),
        nullable=False,
    )

    # 5. Удаляем legacy-колонки.
    op.drop_column("playbook_line_items", "topic_code")
    op.drop_column("playbook_line_items", "check_code")


def downgrade() -> None:
    # 1. Возвращаем legacy-колонки.
    op.add_column(
        "playbook_line_items",
        sa.Column(
            "check_code",
            sa.String(length=100),
            nullable=True,
            comment="Legacy check code, restored on downgrade.",
        ),
    )
    op.add_column(
        "playbook_line_items",
        sa.Column(
            "topic_code",
            sa.String(length=100),
            nullable=True,
            comment="Legacy topic code, restored on downgrade.",
        ),
    )

    # 2. Возвращаем instruction_code обратно в check_code.
    op.execute(
        """
        UPDATE playbook_line_items
        SET check_code = instruction_code
        WHERE instruction_code IS NOT NULL
        """
    )

    # 3. Удаляем новую колонку.
    op.drop_column("playbook_line_items", "instruction_code")


    