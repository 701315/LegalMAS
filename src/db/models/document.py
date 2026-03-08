"""
Document and DocumentVersion models.
Document — a single file in the data room.
DocumentVersion — tracks extracted/processed versions of a document.
"""

import uuid

from sqlalchemy import (
    Float, 
    ForeignKey, 
    Index, 
    Integer, 
    String,
    Column,
    String,
    Boolean,
    DateTime, 
    ARRAY
)

from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DocumentStatus.PENDING.value,
    )

    # NEW: флаг "документ проверен юристом"
    reviewed_by_person: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Has this document been manually reviewed by a lawyer",
    )

    risk_level: Mapped[str | None] = mapped_column(   # NEW
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

    applicable_triggers: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)),
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

    __table_args__ = (Index("idx_docver_doc_version", "document_id", "version_num"),)
