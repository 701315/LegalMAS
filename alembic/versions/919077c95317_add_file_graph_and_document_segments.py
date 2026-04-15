"""add_file_graph_and_document_segments

Revision ID: 919077c95317
Revises: cce5a9ce81e0
Create Date: 2026-04-15 07:47:04.562685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '919077c95317'
down_revision: Union[str, None] = 'cce5a9ce81e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Новые поля в document_versions ────────────────────────────────────

    # file_graph_ref: S3 URI к file_graph.json (граф файла с сегментами).
    # NULL = legacy-режим (один документ = весь файл).
    op.add_column(
        "document_versions",
        sa.Column(
            "file_graph_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI to file_graph.json — список логических сегментов файла "
                "и связи между ними. NULL означает legacy-режим (один сегмент = весь файл)."
            ),
        ),
    )

    # segments_count: количество логических сегментов в файле.
    # NULL = legacy, 1 = один документ, 2+ = несколько логических документов.
    op.add_column(
        "document_versions",
        sa.Column(
            "segments_count",
            sa.Integer(),
            nullable=True,
            comment=(
                "Количество логических сегментов в файле. "
                "NULL = legacy-режим, 1 = один документ, 2+ = multi-doc."
            ),
        ),
    )

    # Partial index: быстрый поиск только версий с file_graph (v2 режим).
    # Занимает значительно меньше места, чем полный индекс по всей колонке.
    op.create_index(
        "idx_docver_file_graph_ref",
        "document_versions",
        ["document_id"],
        postgresql_where=sa.text("file_graph_ref IS NOT NULL"),
    )

    # ── 2. Новая таблица document_segments ────────────────────────────────────

    op.create_table(
        "document_segments",

        # Первичный ключ — стандартный UUID из Base
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),

        # Стандартные временные метки из Base
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),

        # Ссылка на DocumentVersion (родительская версия)
        sa.Column(
            "document_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
            comment="Ссылка на DocumentVersion, которому принадлежит этот сегмент",
        ),

        # Денормализованная ссылка на Document (для быстрых запросов без JOIN)
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            comment=(
                "Денормализованная ссылка на Document. "
                "Позволяет искать сегменты по document_id без JOIN через document_versions."
            ),
        ),

        # Детерминированный UUID сегмента (uuid5 по document_id + segment_order).
        # Стабилен между перезапусками пайплайна — важно для REUSE_STRUCTURE.
        sa.Column(
            "segment_id",
            sa.String(length=36),
            nullable=False,
            comment=(
                "Детерминированный UUID сегмента. "
                "Генерируется через make_segment_id(document_id, segment_order). "
                "Стабилен между перезапусками пайплайна."
            ),
        ),

        # Порядковый номер сегмента в файле (0-based).
        sa.Column(
            "segment_order",
            sa.Integer(),
            nullable=False,
            comment="Порядковый номер сегмента в файле (0-based). 0 = первый документ.",
        ),

        # Тип логического документа.
        sa.Column(
            "segment_type",
            sa.String(length=50),
            nullable=False,
            server_default="unknown",
            comment=(
                "Тип: contract | appendix | amendment | act | invoice | schedule | other | unknown"
            ),
        ),

        # Человекочитаемый заголовок сегмента.
        sa.Column(
            "segment_title",
            sa.String(length=500),
            nullable=True,
            comment="Заголовок сегмента, например 'Приложение №1 к договору'",
        ),

        # Диапазон страниц (нумерация с 1, включительно).
        sa.Column(
            "page_start",
            sa.Integer(),
            nullable=False,
            comment="Первая страница сегмента в файле (включительно, с 1)",
        ),
        sa.Column(
            "page_end",
            sa.Integer(),
            nullable=False,
            comment="Последняя страница сегмента в файле (включительно)",
        ),

        # Флаг primary-сегмента. Ровно один сегмент на версию = True.
        # clause_tree_ref и chunks_ref в DocumentVersion указывают на него.
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment=(
                "True = основной сегмент. Ровно один на DocumentVersion. "
                "clause_tree_ref/chunks_ref в DocumentVersion указывают на него."
            ),
        ),

        # Уверенность определения границ сегмента.
        sa.Column(
            "confidence",
            sa.String(length=10),
            nullable=False,
            server_default="MEDIUM",
            comment="Уверенность сегментации: LOW | MEDIUM | HIGH",
        ),

        # S3 URI к артефактам этого конкретного сегмента.
        sa.Column(
            "segment_clause_tree_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI к ClauseTree этого сегмента. "
                "ArtifactPath.segment_clause_tree(tenant_id, deal_id, document_id, segment_id). "
                "NULL до завершения стадии STRUCTURE."
            ),
        ),
        sa.Column(
            "segment_chunks_ref",
            sa.String(length=1000),
            nullable=True,
            comment=(
                "S3 URI к чанкам этого сегмента. "
                "ArtifactPath.segment_chunks(tenant_id, deal_id, document_id, segment_id). "
                "NULL до завершения стадии CHUNKS."
            ),
        ),

        # Свободные метаданные сегмента для отладки и аудита.
        sa.Column(
            "segment_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Доп. метаданные сегмента: {'detected_by': 'regex', 'heading_text': ...}. "
                "Только для отладки — не используется в бизнес-логике."
            ),
        ),
    )

    # ── 3. Constraints ────────────────────────────────────────────────────────

    # Уникальность segment_id внутри версии: защита от двойной записи.
    op.create_unique_constraint(
        "uq_document_segments_version_segment",
        "document_segments",
        ["document_version_id", "segment_id"],
    )

    # Уникальность порядкового номера внутри версии.
    op.create_unique_constraint(
        "uq_document_segments_version_order",
        "document_segments",
        ["document_version_id", "segment_order"],
    )

    # ── 4. Индексы ────────────────────────────────────────────────────────────

    # Основной рабочий запрос: "все сегменты для document_version_id=X"
    op.create_index(
        "idx_document_segments_version",
        "document_segments",
        ["document_version_id"],
    )

    # Денормализованный поиск по document_id без JOIN
    op.create_index(
        "idx_document_segments_document",
        "document_segments",
        ["document_id"],
    )

    # Поиск по типу сегмента в документе: "все appendix в document_id=X"
    op.create_index(
        "idx_document_segments_type",
        "document_segments",
        ["document_id", "segment_type"],
    )

    # Partial index: только primary-сегменты (самый частый запрос)
    op.create_index(
        "idx_document_segments_primary",
        "document_segments",
        ["document_version_id"],
        postgresql_where=sa.text("is_primary = true"),
    )


def downgrade() -> None:
    # Порядок обратный upgrade: сначала индексы, потом таблицы/колонки.

    # ── 1. Убираем индексы и таблицу document_segments ───────────────────────
    op.drop_index(
        "idx_document_segments_primary",
        table_name="document_segments",
        postgresql_where=sa.text("is_primary = true"),
    )
    op.drop_index("idx_document_segments_type", table_name="document_segments")
    op.drop_index("idx_document_segments_document", table_name="document_segments")
    op.drop_index("idx_document_segments_version", table_name="document_segments")

    op.drop_constraint(
        "uq_document_segments_version_order",
        "document_segments",
        type_="unique",
    )
    op.drop_constraint(
        "uq_document_segments_version_segment",
        "document_segments",
        type_="unique",
    )

    op.drop_table("document_segments")

    # ── 2. Убираем поля и индекс из document_versions ────────────────────────
    op.drop_index(
        "idx_docver_file_graph_ref",
        table_name="document_versions",
        postgresql_where=sa.text("file_graph_ref IS NOT NULL"),
    )
    op.drop_column("document_versions", "segments_count")
    op.drop_column("document_versions", "file_graph_ref")

    