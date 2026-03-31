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
  - text_layout_raw_ref — сырой текстовый макет;
  - text_layout_sanitized_ref — макет после PII‑санитизации;
  - clause_tree_ref — дерево пунктов договора.
- Также фиксирует технические параметры пайплайна:
  - extraction_strategy, ocr_confidence;
  - origin_filetype/origin_extension;
  - pipeline_strategy (pdf_native, pdf_ocr, docx_via_pdf_native и т.п.).

Для чего это нужно:
- backend‑воркеры всех стадий (import, extract, pii, structure, classify, checks)
  читают и обновляют статусы/refs строго через эти модели;
- фронт может по одному Document:
  - понять, где он сейчас в пайплайне и почему мог остановиться;
  - показать юристу понятное сообщение об ошибке и дать ссылку на Run;
  - подсветить документы с низкой уверенностью или требующие ручной проверки.
"""


import uuid

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Column,
    Boolean,
    DateTime,
    ARRAY,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import DocumentStatus
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
            "Last processing error metadata: "
            "{stage, type, reason, message, run_id, timestamp}"
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

    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="PlaybookVersion used for DD checks in this analysis",
    )

    applicable_triggers: Mapped[list[str] | None] = mapped_column(
        PG_ARRAY(String(100)),
        nullable=True,
        comment="Triggered conditions for conditional checks (from YAML)",
    )

    __table_args__ = (
        Index("idx_documents_deal_status", "deal_id", "status"),
        Index("idx_documents_deal_sha256", "deal_id", "sha256_file"),
        Index("idx_documents_bundle", "bundle_id"),
        Index(
            "idx_documents_classification",
            "deal_id",
            "doc_type",
            "classification_confidence",
        ),
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
    
    # --- НОВОЕ ПОЛЕ ---
    # Хранит ссылку на PDF, который получился после конвертации DOCX/DOC → PDF.
    # Если документ изначально был PDF — это поле всегда NULL.
    # extract_worker смотрит сначала сюда, и только если NULL — берёт original_ref.
    converted_pdf_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment=(
            "S3 URI to PDF converted from original office format (DOCX, DOC, etc.). "
            "Если заполнено — extract_worker использует его вместо original_ref. "
            "Для исходных PDF всегда NULL."
        ),
    )


    text_layout_raw_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="S3 URI to raw text layout JSON",
    )

    text_layout_sanitized_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="S3 URI to PII-sanitized text layout JSON",
    )

    clause_tree_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="S3 URI to clause tree JSON",
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
            "Internal type of the file this version originates from: "
            "pdf, docx, image, etc."
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
    )
