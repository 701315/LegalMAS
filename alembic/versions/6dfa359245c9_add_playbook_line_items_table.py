"""add playbook_line_items table


Revision ID: 6dfa359245c9
Revises: 2886255a90c2
Create Date: 2026-03-14 19:09:10.450903


"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6dfa359245c9"
down_revision: Union[str, None] = "2886255a90c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Создаём таблицу playbook_line_items.

    Таблица хранит элементы логического плейбука (Playbook):
    - либо тема (topic_code),
    - либо конкретная проверка (check_code),
    - порядок элементов задаётся полем order_index.
    """

    op.create_table(
        "playbook_line_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "line_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("playbooks.id", ondelete="CASCADE"),
            nullable=False,
            comment="Playbook (logical line) this item belongs to.",
        ),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            comment="Element type: 'topic' or 'check'.",
        ),
        sa.Column(
            "topic_code",
            sa.String(length=100),
            nullable=True,
            comment="Topic code, e.g. 'corporate', 'tax', 'real_estate'.",
        ),
        sa.Column(
            "check_code",
            sa.String(length=100),
            nullable=True,
            comment="Check code, e.g. 'encumbrances_warranty'.",
        ),
        sa.Column(
            "order_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Order of items within the playbook line for UI/compilation.",
        ),
    )

    # Индекс по line_id, чтобы быстро получать все элементы шаблона по playbook_id
    op.create_index(
        "ix_playbook_line_items_line_id",
        "playbook_line_items",
        ["line_id"],
        unique=False,
    )


def downgrade() -> None:
    """
    Откатываем изменения: удаляем индекс и таблицу playbook_line_items.
    """

    op.drop_index("ix_playbook_line_items_line_id", table_name="playbook_line_items")
    op.drop_table("playbook_line_items")
