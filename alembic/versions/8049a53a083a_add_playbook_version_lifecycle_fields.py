"""add playbook version lifecycle fields

Revision ID: 8049a53a083a
Revises: 29a6b02a7975
Create Date: 2026-07-20 15:51:28.661608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '8049a53a083a'
down_revision: Union[str, None] = '29a6b02a7975'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "playbook_versions"


def upgrade() -> None:
    # 1. Добавляем новые поля
    op.add_column(
        TABLE,
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if this is the global default version for new deals.",
        ),
    )

    op.add_column(
        TABLE,
        sa.Column(
            "immutable_content_hash",
            sa.String(64),
            nullable=True,
            comment="Canonical SHA256 of compiled_checks. Set at publish.",
        ),
    )

    op.add_column(
        TABLE,
        sa.Column(
            "validation_report",
            JSONB,
            nullable=True,
            comment="Validation diagnostics from compile/publish.",
        ),
    )

    op.add_column(
        TABLE,
        sa.Column(
            "parent_version_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="Version this draft was derived from.",
        ),
    )

    op.create_foreign_key(
        "fk_playbook_versions_parent_version_id",
        TABLE,
        TABLE,
        ["parent_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Миграция данных: default → published + is_default=True
    op.execute(
        f"""
        UPDATE {TABLE}
        SET is_default = true, status = 'published'
        WHERE status = 'default'
        """
    )

    # 3. Миграция данных: stable → published
    op.execute(
        f"""
        UPDATE {TABLE}
        SET status = 'published'
        WHERE status = 'stable'
        """
    )

    # 4. Обновляем старый индекс
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_playbook_status'
            ) THEN
                DROP INDEX idx_playbook_status;
            END IF;
        END $$;
        """
    )

    op.create_index(
        "idx_playbook_versions_status",
        TABLE,
        ["status"],
    )

    # 5. Partial unique: один is_default=true глобально
    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_playbook_versions_one_default
        ON {TABLE} (is_default)
        WHERE is_default = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uix_playbook_versions_one_default")
    op.drop_index("idx_playbook_versions_status", table_name=TABLE)

    # Восстанавливаем старый индекс
    op.create_index("idx_playbook_status", TABLE, ["status"])

    # Обратная миграция данных
    op.execute(
        f"""
        UPDATE {TABLE}
        SET status = 'default'
        WHERE is_default = true AND status = 'published'
        """
    )
    op.execute(
        f"""
        UPDATE {TABLE}
        SET status = 'stable'
        WHERE status = 'published' AND is_default = false
        """
    )

    op.drop_constraint(
        "fk_playbook_versions_parent_version_id",
        TABLE,
        type_="foreignkey",
    )
    op.drop_column(TABLE, "parent_version_id")
    op.drop_column(TABLE, "validation_report")
    op.drop_column(TABLE, "immutable_content_hash")
    op.drop_column(TABLE, "is_default")

    