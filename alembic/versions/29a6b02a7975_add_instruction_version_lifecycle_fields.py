"""add_instruction_version_lifecycle_fields

Revision ID: 29a6b02a7975
Revises: 08f5150a0dde
Create Date: 2026-07-20 12:01:42.257808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '29a6b02a7975'
down_revision: Union[str, None] = '08f5150a0dde'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "document_type_instruction_versions"


def upgrade() -> None:
    # 1. Добавляем новые поля lifecycle
    op.add_column(
        TABLE,
        sa.Column(
            "version_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'draft'"),
            comment="Lifecycle status: draft | published | archived",
        ),
    )

    op.add_column(
        TABLE,
        sa.Column(
            "immutable_content_hash",
            sa.String(length=64),
            nullable=True,
            comment=(
                "Canonical SHA256 of compiled_payload. "
                "Set once at publish time, never changed after."
            ),
        ),
    )

    op.add_column(
        TABLE,
        sa.Column(
            "validation_report",
            JSONB,
            nullable=True,
            comment="Validation diagnostics produced at compile/publish time.",
        ),
    )

    op.add_column(
        TABLE,
        sa.Column(
            "parent_version_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="Version this draft was derived from (for audit trail).",
        ),
    )

    op.create_foreign_key(
        "fk_document_type_instruction_versions_parent_version_id",
        TABLE,
        TABLE,
        ["parent_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Переносим данные из is_published в version_status
    # published -> published
    # not published -> draft
    op.execute(
        f"""
        UPDATE {TABLE}
        SET version_status = CASE
            WHEN is_published = true THEN 'published'
            ELSE 'draft'
        END
        """
    )

    # 3. Если по историческим данным есть несколько published на один doc_type,
    #    оставляем одну "главную" published, остальные переводим в archived.
    #    Выбираем победителя детерминированно:
    #    published_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
    op.execute(
        f"""
        WITH ranked AS (
            SELECT
                id,
                doc_type_code,
                ROW_NUMBER() OVER (
                    PARTITION BY doc_type_code
                    ORDER BY published_at DESC NULLS LAST,
                             created_at DESC NULLS LAST,
                             id DESC
                ) AS rn
            FROM {TABLE}
            WHERE version_status = 'published'
        )
        UPDATE {TABLE} t
        SET version_status = 'archived'
        FROM ranked r
        WHERE t.id = r.id
          AND r.rn > 1
        """
    )

    # 4. Удаляем старое булево поле
    op.drop_column(TABLE, "is_published")

    # 5. Удаляем возможный автосгенерированный индекс от old index=True
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE indexname = 'ix_document_type_instruction_versions_doc_type_code'
            ) THEN
                DROP INDEX ix_document_type_instruction_versions_doc_type_code;
            END IF;
        END $$;
        """
    )

    # 6. Создаём новый индекс по lifecycle
    op.create_index(
        "idx_doc_type_instruction_versions_status",
        TABLE,
        ["doc_type_code", "version_status"],
        unique=False,
    )

    # 7. Partial unique index: только одна published версия на doc_type_code
    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_doc_type_instruction_versions_one_published
        ON {TABLE} (doc_type_code)
        WHERE version_status = 'published'
        """
    )


def downgrade() -> None:
    # 1. Удаляем partial unique index и lifecycle-index
    op.execute("DROP INDEX IF EXISTS uix_doc_type_instruction_versions_one_published")
    op.drop_index("idx_doc_type_instruction_versions_status", table_name=TABLE)

    # 2. Возвращаем is_published
    op.add_column(
        TABLE,
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether this instruction version is published for runtime usage.",
        ),
    )

    # 3. Перекладываем данные обратно
    op.execute(
        f"""
        UPDATE {TABLE}
        SET is_published = CASE
            WHEN version_status = 'published' THEN true
            ELSE false
        END
        """
    )

    # 4. Удаляем FK
    op.drop_constraint(
        "fk_document_type_instruction_versions_parent_version_id",
        TABLE,
        type_="foreignkey",
    )

    # 5. Удаляем новые поля
    op.drop_column(TABLE, "parent_version_id")
    op.drop_column(TABLE, "validation_report")
    op.drop_column(TABLE, "immutable_content_hash")
    op.drop_column(TABLE, "version_status")

    # 6. Возвращаем старый индекс по doc_type_code, если нужен downgrade
    op.create_index(
        "ix_document_type_instruction_versions_doc_type_code",
        TABLE,
        ["doc_type_code"],
        unique=False,
    )


    