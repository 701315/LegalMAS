# src/db/models/document.py

"""
Document and DocumentVersion models.

Document:
- Описывает один файл в Data Room в контексте сделки (SPA, NDA, отчёт и т.п.).
- Хранит бизнес‑статус обработки (pending → extracted → sanitized → structured
  → classified → completed, а также failed / quarantine).
- Содержит:
  - processing_error_details — единый JSON‑контракт ошибок обработки:
    {stage, type, reason?, message, run_id?, timestamp};
  - метаданные классификации (doc_type, classification_level/confidence,
    applicable_triggers, language, jurisdiction_guess);
  - признаки для UX (reviewed_by_person, risk_level).

DocumentVersion:
- Отражает конкретную «техническую» версию документа в хранилище артефактов.
- Для каждой версии хранит ссылки на артефакты в S3/MinIO:
  - original_ref — исходный файл;
  - converted_pdf_ref — PDF после конвертации офисных форматов (DOCX, DOC и др.);
  - text_layout_raw_ref — сырой многоязычный текстовый макет;
  - layout_primary_ref — одноязычный layout по основному языку сделки;
  - text_layout_sanitized_ref — legacy / общий sanitized layout;
  - layout_primary_sanitized_ref — одноязычный layout после PII‑санитизации;
  - clause_tree_ref — legacy clause tree для primary сегмента;
  - file_graph_ref — граф файла: список логических сегментов + связи (v2);
  - chunks_manifest_v2_ref — file-level манифест чанков (v2);
  - segments_count — количество логических сегментов в файле (v2).
- Также фиксирует технические параметры пайплайна:
  - extraction_strategy, ocr_confidence;
  - origin_filetype/origin_extension;
  - pipeline_strategy (pdf_native, pdf_ocr, docx_via_pdf_native и т.п.).

DocumentSegment (v2):
- Описывает один логический документ внутри физического файла.
- Один DocumentVersion может содержать несколько DocumentSegment:
  основной договор, приложения, акты, счета и т.п.
- Каждый сегмент имеет свой segment_clause_tree_ref и segment_chunks_ref.
- В текущем v2‑контракте основными источниками истины являются:
  - file_graph_ref в DocumentVersion;
  - segment_clause_tree_ref и segment_chunks_ref в DocumentSegment.
- legacy clause_tree_ref в DocumentVersion, если заполнен, относится к primary‑сегменту
  и сохраняется только для обратной совместимости со старым кодом.

Для чего это нужно:
- backend‑воркеры всех стадий (import, extract, pii, structure, classify, checks)
  читают и обновляют статусы/refs строго через эти модели;
- фронт может по одному Document:
  - понять, где он сейчас в пайплайне и почему мог остановиться;
  - показать юристу понятное сообщение об ошибке и дать ссылку на Run;
  - подсветить документы с низкой уверенностью или требующие ручной проверки.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import DocumentStageExecutionStatus, DocumentStatus

from ..base import Base


class Document(Base):
    __tablename__ = "documents"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )

    bundle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bundles.id", ondelete="CASCADE"),
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    folder_path: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
        comment="Relative path in Data Room: '01. Corporate/Charter Docs'",
    )

    source_extension: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Original file extension including dot, e.g. '.pdf', '.docx'",
    )

    source_filetype: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Internal file type from file_validator: pdf, docx, xlsx, image, etc.",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DocumentStatus.PENDING.value,
    )

    processing_error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Last processing error metadata: " "{stage, type, reason, message, run_id, timestamp}"
        ),
    )

    reviewed_by_person: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Has this document been manually reviewed by a lawyer",
    )

    risk_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Risk level: low, medium, high, critical",
    )

    doc_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="SPA, NDA, Employment, etc. Set by Classifier.",
    )

    language: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="RU, EN, etc.",
    )

    # NEW (v2): Результаты pre-run language discovery на уровне документа.
    #
    # Для непрофессионального программиста:
    # - detected_languages хранит список всех языков, которые автоматический
    #   анализ нашёл в этом файле (например: ['ru', 'en']).
    # - language_discovery_status показывает состояние этапа определения
    #   языков для этого документа.
    #
    # Эти поля нужны, чтобы:
    # - оркестратор и воркеры не делали повторную дорогостоящую проверку
    #   языков для одного и того же файла;
    # - можно было понять, какие документы уже обработаны, а какие ещё нет;
    # - фронт и админские инструменты могли отлаживать/диагностировать
    #   language discovery независимо от основного пайплайна анализа.
    detected_languages: Mapped[list[str] | None] = mapped_column(
        PG_ARRAY(String(10)),
        nullable=True,
        comment="All languages detected in this document, e.g. ['ru', 'en'].",
    )

    language_discovery_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "Status of pre-run language discovery for this document: "
            "pending / processing / completed / failed"
        ),
    )

    jurisdiction_guess: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    sha256_file: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA256 hash of original file for dedup",
    )

    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    classification_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Final classification confidence 0.0-1.0",
    )

    classification_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Level that made final decision: L1, L2, L3, L4, HYBRID",
    )

    classification_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full classification history with all levels tried",
    )

    classification_requires_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment=(
            "True, если HybridClassifier.details['requires_manual_review'] == True. "
            "Используется для подсветки документов, требующих ручной проверки "
            "результата классификации."
        ),
    )

    classification_outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        comment=(
            "Business outcome of document-level classification: "
            "pending | typed | unknown | failed. "
            "НЕ путать с Document.status (pipeline stage). "
            "Отвечает на вопрос: был ли тип документа определён?"
        ),
    )

    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="PlaybookVersion used for DD checks in this analysis",
    )

    doc_type_instruction_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_type_instruction_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Persisted YAML instruction snapshot used for document classification",
    )

    applicable_triggers: Mapped[list[str] | None] = mapped_column(
        PG_ARRAY(String(100)),
        nullable=True,
        comment="Triggered conditions for conditional checks (from YAML)",
    )

    __table_args__ = (
        Index("idx_documents_deal_status", "deal_id", "status"),
        Index("idx_documents_classification_outcome", "classification_outcome"),
        Index("idx_documents_deal_sha256", "deal_id", "sha256_file"),
        Index("idx_documents_instruction_version", "doc_type_instruction_version_id"),
        Index("idx_documents_bundle", "bundle_id"),
        Index(
            "idx_documents_classification",
            "deal_id",
            "doc_type",
            "classification_confidence",
        ),
        Index("idx_documents_deal_lang_discovery", "deal_id", "language_discovery_status"),
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_num: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    original_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="S3 URI to original file",
    )

    converted_pdf_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to PDF converted from original office format (DOCX, DOC, etc.). "
            "Если заполнено — extract_worker использует его вместо original_ref. "
            "Для исходных PDF всегда NULL."
        ),
    )

    primary_source_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to primary-language-only source file (usually PDF). "
            "Build by language worker before extract; "
            "extract_worker prefers this over converted_pdf_ref/original_ref."
        ),
    )

    text_layout_raw_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to raw multilingual text layout JSON. "
            "Это исходный layout после extract без фильтрации по основному языку."
        ),
    )

    layout_primary_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to primary-language-only layout JSON. "
            "Формируется после определения языков документа и выбора основного "
            "языка сделки. Именно этот layout должен быть основным входом для "
            "downstream-стадий анализа."
        ),
    )

    text_layout_sanitized_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to legacy/general PII-sanitized layout JSON. "
            "Оставлено для обратной совместимости и fallback."
        ),
    )

    layout_primary_sanitized_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to primary-language-only PII-sanitized layout JSON. "
            "Это целевой основной layout для structure, chunking, retrieval и checks."
        ),
    )

    clause_tree_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "LEGACY: S3 URI to clause tree JSON (single-document / primary segment).\n"
            "\n"
            "В v2 режиме это поле считается устаревшим и используется только\n"
            "для обратной совместимости со старым кодом (STRUCTURE/CHUNKS v1).\n"
            "Новая архитектура STRUCTURE/CHUNKS v2 должна опираться на:\n"
            "- file_graph_ref\n"
            "- DocumentSegment.segment_clause_tree_ref\n"
        ),
    )

    # ── Multi-document поля (v2) ──────────────────────────────────────────────
    # Оба поля опциональны (nullable=True).
    # Если NULL — версия обработана в legacy-режиме (один сегмент = весь файл).
    # Если заполнены — версия обработана в v2-режиме с сегментацией.

    file_graph_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to file_graph.json — граф файла: список логических сегментов "
            "(SegmentDocument) и связи между ними (CrossDocumentLink). "
            "NULL означает legacy-режим (один сегмент = весь файл). "
            "Заполняется workers.build_structure.\n"
            "\n"
            "CHUNKS v2 читают этот ref чтобы определить, какие "
            "segment_clause_tree_*.json и DocumentSegment нужно загрузить."
        ),
    )

    chunks_manifest_v2_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to chunks_manifest_v2.json — file-level манифест чанков.\n"
            "\n"
            "Для непрофессионального программиста:\n"
            "- Это один JSON-файл, который описывает весь набор чанков по файлу,\n"
            "  но сами тексты чанков лежат по ссылкам segment_chunks_ref "
            "в таблице DocumentSegment.\n"
            "- retrieval/checks/LLM должны начинать чтение именно с этого файла.\n"
            "\n"
            "NULL означает, что CHUNKS v2 ещё не отработали для этой версии."
        ),
    )

    chunk_plan_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to chunk_plan.json — Phase 10 Chunk Planner output.\n"
            "\n"
            "Вычисляется в structure_builder после Phase 9 quality analysis.\n"
            "Читается chunk_builder для quality-aware chunking.\n"
            "NULL означает что Phase 10 не выполнялся (legacy mode или ошибка\n"
            "planning) — chunk_builder использует дефолтные параметры."
        ),
    )

    segments_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "Количество логических сегментов (логических документов) в файле. "
            "NULL — legacy-режим. "
            "1 — файл содержит один документ (stub или реальная сегментация дала 1). "
            "2+ — файл содержит несколько логических документов. "
            "Используется для быстрой фильтрации в API и для метрик."
        ),
    )

    extraction_strategy: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="pdfplumber, ocr_only, hybrid",
    )

    ocr_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Average OCR confidence 0.0-1.0",
    )

    origin_filetype: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "Internal type of the file this version originates from: " "pdf, docx, image, etc."
        ),
    )

    origin_extension: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Original extension of source file, e.g. '.pdf', '.docx', '.png'",
    )

    pipeline_strategy: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "High-level processing route: "
            "pdf_native, pdf_ocr, docx_via_pdf_native, docx_via_pdf_ocr, image_ocr, etc."
        ),
    )

    __table_args__ = (
        Index("idx_docver_doc_version", "document_id", "version_num"),
        Index(
            "idx_docver_file_graph_ref",
            "document_id",
            postgresql_where=text("file_graph_ref IS NOT NULL"),
        ),
        Index(
            "idx_docver_chunks_manifest_v2_ref",
            "document_id",
            postgresql_where=text("chunks_manifest_v2_ref IS NOT NULL"),
        ),
    )


class DocumentSegment(Base):
    """
    Один логический документ внутри физического файла (v2).

    Для непрофессионального программиста:
    Когда один PDF содержит несколько документов (основной договор +
    Приложение №1 + Акт приёма-передачи), для каждого из них создаётся
    отдельная строка DocumentSegment. Они все ссылаются на один
    DocumentVersion через document_version_id.

    Зачем нужна отдельная таблица (а не просто JSONB в DocumentVersion):
    - Можно делать запросы типа "найди все сегменты типа appendix по сделке"
      с индексом, без десериализации JSON.
    - Можно хранить отдельные S3-ссылки на дерево и чанки каждого сегмента.
    - Можно запускать checks на конкретный сегмент, зная его segment_id.

    Связи:
    - document_version_id → DocumentVersion (один ко многим)
    - segment_id — детерминированный UUID из make_segment_id() в models.py,
      стабилен между перезапусками пайплайна (важно для REUSE_STRUCTURE).
    """

    __tablename__ = "document_segments"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Ссылка на DocumentVersion, которому принадлежит этот сегмент",
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        comment=(
            "Денормализованная ссылка на Document для упрощения запросов. "
            "Избавляет от JOIN с document_versions при поиске сегментов по document_id."
        ),
    )

    segment_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment=(
            "Детерминированный UUID сегмента. "
            "Генерируется через make_segment_id(document_id, segment_order). "
            "Стабилен между перезапусками пайплайна."
        ),
    )

    segment_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Порядковый номер сегмента в файле (0-based). 0 = первый документ в файле.",
    )

    segment_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unknown",
        comment=(
            "Тип логического документа: "
            "contract | appendix | amendment | act | invoice | schedule | other | unknown"
        ),
    )

    segment_title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Человекочитаемый заголовок сегмента, например 'Приложение №1'",
    )

    page_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Первая страница сегмента в файле (включительно, нумерация с 1)",
    )

    page_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Последняя страница сегмента в файле (включительно)",
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment=(
            "True — этот сегмент является основным (primary). "
            "Ровно один сегмент на DocumentVersion должен иметь is_primary=True. "
            "В legacy-совместимых сценариях clause_tree_ref в DocumentVersion, "
            "если заполнен, относится к этому сегменту."
        ),
    )

    confidence: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="MEDIUM",
        comment="Уверенность определения границ сегмента: LOW | MEDIUM | HIGH",
    )

    # S3-ссылки на артефакты этого конкретного сегмента.
    # Именование: segment_clause_tree_ref, segment_chunks_ref
    # (не просто clause_tree_ref, чтобы не путать с полями DocumentVersion).

    segment_clause_tree_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI к ClauseTree этого сегмента. "
            "Путь: ArtifactPath.segment_clause_tree(tenant_id, deal_id, document_id, segment_id). "
            "NULL до завершения стадии STRUCTURE."
        ),
    )

    segment_chunks_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI к чанкам этого сегмента. "
            "Путь: ArtifactPath.segment_chunks(tenant_id, deal_id, document_id, segment_id). "
            "NULL до завершения стадии CHUNKS."
        ),
    )

    segment_meta: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Дополнительные метаданные сегмента в свободном формате JSONB. "
            "Например: {'detected_by': 'regex', 'heading_text': 'ПРИЛОЖЕНИЕ №1'}. "
            "Не используется в бизнес-логике напрямую — только для отладки и аудита."
        ),
    )

    segment_doc_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment=(
            "Код типа документа для этого сегмента (type_code из YAMLRegistry). "
            "Например: 'nda', 'employment', 'real_estate_sale'. "
            "Устанавливается HybridClassifier при segment-level классификации."
        ),
    )

    segment_doc_type_instruction_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_type_instruction_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Persisted YAML instruction snapshot used for segment classification",
    )

    segment_classification_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Уверенность классификации сегмента 0.0–1.0 (final_confidence из HybridClassifier).",
    )

    segment_classification_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment=(
            "Уровень, который дал финальное решение для сегмента: " "L3, L4, HYBRID, COPIED и т.п."
        ),
    )

    segment_confidence_zone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment=(
            "Зона уверенности segment-level классификации: "
            "high | medium | low | unknown."
        ),
    )

    segment_applicable_triggers: Mapped[list[str] | None] = mapped_column(
        PG_ARRAY(String(100)),
        nullable=True,
        comment=(
            "Список сработавших триггеров/условий для этого сегмента "
            "(как applicable_triggers в Document, но на уровне сегмента)."
        ),
    )

    segment_classification_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Полный payload HybridClassifier для этого сегмента: "
            "{levels_tried, candidates, final_type, final_confidence, confidence_zone, ...}."
        ),
    )

    segment_classification_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
        comment=(
            "Pipeline-статус segment-level классификации: "
            "pending | classified | unknown | skipped | failed. "
            "Источник истины для orchestrator: стадия завершена если статус "
            "в (classified, unknown, skipped). "
            "НЕ путать с segment_doc_type (бизнес-тип) и "
            "segment_confidence_zone (диагностика уверенности)."
        ),
    )

    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "segment_id",
            name="uq_document_segments_version_segment",
        ),
        UniqueConstraint(
            "document_version_id",
            "segment_order",
            name="uq_document_segments_version_order",
        ),
        Index(
            "idx_document_segments_version",
            "document_version_id",
        ),
        Index(
            "idx_segments_version_classification_status",
            "document_version_id",
            "segment_classification_status",
        ),
        Index(
            "idx_document_segments_document",
            "document_id",
        ),
        Index(
            "idx_document_segments_type",
            "document_id",
            "segment_type",
        ),
        Index(
            "idx_document_segments_primary",
            "document_version_id",
            postgresql_where=text("is_primary = true"),
        ),
        Index(
            "idx_document_segments_instruction_version",
            "segment_doc_type_instruction_version_id",
        ),
    )


class DocumentStageExecution(Base):
    """
    One execution attempt of one pipeline stage for one document version.

    Зачем нужна эта модель:
    - это durable слой идемпотентности для document-level pipeline;
    - оркестратор создаёт такую запись ДО постановки Celery task;
    - worker получает stage_execution_id и обновляет lifecycle записи;
    - активный execution блокирует повторную постановку той же стадии
      для той же версии документа и той же orchestration strategy.

    Важно:
    - это не замена Document.status;
    - это не замена Job;
    - это отдельный execution ledger именно для переходов pipeline-стадий
      на уровне document_version.
    """

    __tablename__ = "document_stage_executions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Run that initiated this stage execution",
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Document to which this stage execution belongs",
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Exact document version processed by this stage execution",
    )

    from_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Document.status value before this stage execution started",
    )

    to_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Target Document.status expected after successful stage completion",
    )

    orchestration_strategy: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "High-level orchestration strategy for this execution attempt "
            "(e.g. V2_ONLY, REUSE_STRUCTURE, FULL_RERUN). "
            "Not the same as DocumentVersion.pipeline_strategy."
        ),
    )

    task_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Celery task name that executes this stage",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStageExecutionStatus.PLANNED.value,
        comment=(
            "Lifecycle of this stage execution attempt: "
            "planned / dispatched / started / succeeded / failed / cancelled"
        ),
    )

    celery_task_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Celery task id returned by send_task/apply_async if available",
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Execution error metadata: " "{stage, type, reason, message, run_id, timestamp, extra}"
        ),
    )

    result_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Structured terminal result metadata for successfully completed stages. "
            "Used for semantic enrichment stage outcomes: "
            "{terminal_outcome, segments_enriched, segments_timed_out, "
            "segments_failed, segments_skipped_budget, budget_exhausted, ...}"
        ),
    )

    progress_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Live progress snapshot for long-running stages.",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when worker actually started execution",
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when execution finished (success/fail/cancel)",
    )

    __table_args__ = (
        Index("idx_dse_run_created", "run_id", "created_at"),
        Index("idx_dse_docver_created", "document_version_id", "created_at"),
        Index("idx_dse_doc_stage_status", "document_id", "to_status", "status"),
        Index(
            "uq_dse_active_stage_per_version_task",
            "run_id",
            "document_version_id",
            "task_name",
            unique=True,
            postgresql_where=text("status IN ('planned', 'dispatched', 'started')"),
        ),
    )

    