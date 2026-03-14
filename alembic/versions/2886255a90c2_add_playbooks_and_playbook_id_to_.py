"""add playbooks and playbook_id to playbook_versions

Revision ID: 2886255a90c2
Revises: 6df6ab5ae7c7
Create Date: 2026-03-14 17:11:48.720776

"""
from typing import Sequence, Union
from sqlalchemy.dialects import postgresql
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2886255a90c2'
down_revision: Union[str, None] = '6df6ab5ae7c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Создаём таблицу playbooks
    op.create_table(
        "playbooks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
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
            "code",
            sa.String(length=100),
            nullable=False,
            unique=True,
            comment="Machine-readable code, e.g. 'real_estate_ru_core'.",
        ),
        sa.Column(
            "title",
            sa.String(length=300),
            nullable=False,
            comment="Display name for UI, e.g. 'Real estate RU (core DD)'.",
        ),
        sa.Column(
            "description",
            sa.String(length=1000),
            nullable=True,
            comment="Optional description for UI.",
        ),
        sa.Column(
            "deal_type",
            sa.String(length=100),
            nullable=True,
            comment="Deal type: real_estate, mna, nda, corporate, etc.",
        ),
        sa.Column(
            "jurisdiction",
            sa.String(length=50),
            nullable=True,
            comment="Primary jurisdiction: e.g. RU, EN, DE.",
        ),
        sa.Column(
            "language",
            sa.String(length=10),
            nullable=True,
            comment="Primary language: e.g. 'ru', 'en'.",
        ),
        sa.Column(
            "risk_profile",
            sa.String(length=50),
            nullable=True,
            comment="Optional risk/profile label: standard/high/vendor/buyer/etc.",
        ),
    )

    # Индекс по code (дублирует unique, но ускоряет lookup)
    op.create_index(
        "ix_playbooks_code",
        "playbooks",
        ["code"],
        unique=True,
    )

    # 2) Добавляем колонку playbook_id в playbook_versions
    op.add_column(
        "playbook_versions",
        sa.Column(
            "playbook_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Logical Playbook this version belongs to.",
        ),
    )

    # 3) Добавляем внешний ключ на playbooks.id c ondelete=SET NULL
    op.create_foreign_key(
        "fk_playbook_versions_playbook_id_playbooks",
        source_table="playbook_versions",
        referent_table="playbooks",
        local_cols=["playbook_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Удаляем FK и колонку playbook_id
    op.drop_constraint(
        "fk_playbook_versions_playbook_id_playbooks",
        "playbook_versions",
        type_="foreignkey",
    )
    op.drop_column("playbook_versions", "playbook_id")

    # Удаляем индекс и таблицу playbooks
    op.drop_index("ix_playbooks_code", table_name="playbooks")
    op.drop_table("playbooks")