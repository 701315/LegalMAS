# src/db/models/result.py

"""
CheckResult model — result of a single DD check on a document.
Each check produces one result with evidence, severity, and QC status.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import QCStatus

from ..base import Base


class CheckResult(Base):
    __tablename__ = "check_results"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    check_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Check identifier from playbook, e.g. coc_001",
    )

    check_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Human-readable check name",
    )

    result: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="fail, pass, unclear",
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="critical, high, medium, pass, unclear",
    )

    value_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Short description of what was found",
    )

    evidence_ref: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="S3 URI or inline evidence snippet; may be long text",
    )

    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Detection confidence 0.0-1.0",
    )

    detector_used: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="rules, llm, hybrid",
    )

    quality_flags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="Flags: structure_degraded, llm_fallback_used, etc.",
    )

    structured_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Extracted structured fields from check",
    )

    conditional_check_triggered: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this check was triggered by a conditional rule",
    )

    trigger_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Name of the trigger that activated this check",
    )

    origin: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Source of check definition: global_playbook, document_type_playbook, cross_doc",
    )

    page: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Page number where evidence was found",
    )

    clause_uid: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Clause UID or chunk identifier within the document",
    )

    element_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Layout element ID (for precise highlighting in viewer)",
    )

    bbox: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Bounding box of evidence in document coordinates (for viewer highlight)",
    )

    segment_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Logical segment identifier within a multi-document physical file",
    )

    segment_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Logical segment type: contract, appendix, annex, amendment, invoice, act, etc.",
    )

    segment_title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Human-readable title of the logical segment",
    )

    segment_order: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Order of the logical segment within the physical file",
    )

    is_primary_segment: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if the finding belongs to the primary logical segment of the file",
    )

    chunk_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment=(
            "Full chunk identifier from retrieval/chunking layer, "
            "e.g. {doc_id}:{segment_id}:{clause_uid}:{sub_idx}"
        ),
    )

    chunk_index: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=(
            "Sub-chunk index within clause or segment. "
            "0 = whole clause/default chunk, 1+ = sized subchunk"
        ),
    )

    context_trace: Mapped[list[dict] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Compact retrieval/extraction provenance trace. "
            "List of the top-ranked contexts/chunks used to build LLM context."
        ),
    )

    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Версия плейбука, которой был выполнен этот check (для аудита)",
    )

    plan_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("run_check_plan_items.id", ondelete="SET NULL"),
        nullable=True,
        comment="Execution plan item that produced this result",
    )

    # --- Execution status fields ---

    execution_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        comment=(
            "Technical execution status of this check: "
            "PENDING, RUNNING, SUCCESS, COMPUTE_FAILED, PERSIST_FAILED, TIMEOUT, FAILED(legacy)"
        ),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this check execution started",
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this check execution reached a terminal state",
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Error/timeout details for COMPUTE_FAILED, PERSIST_FAILED, TIMEOUT and legacy FAILED executions",
    )

    # --- QC fields ---

    qc_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=QCStatus.PENDING.value,
    )

    qc_by: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="User who performed QC",
    )

    qc_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    qc_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- Canonical display semantics (Spec v2) ---

    ui_mode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "Denormalized ui_mode from CheckDefinition: "
            "clause_presence, risk_detection, field_extraction, compliance"
        ),
    )

    display_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Canonical human-facing factual text for DD Grid cell. "
            "Single source of truth for primary display."
        ),
    )

    machine_reason_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment=(
            "Internal machine reason code (e.g. rules_confident_positive). "
            "For diagnostics only, never shown as primary text."
        ),
    )

    # --- Canonical review semantics (Spec v2) ---

    review_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "Canonical review workflow status: "
            "no_issue_detected, issue_detected, clause_missing, "
            "unclear, manual_review_required, not_applicable, technical_failure"
        ),
    )

    review_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Advisory explanation for lawyer. "
            "Shown in drawer/details, never as primary cell text."
        ),
    )

    needs_manual_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Explicit boolean flag for review workflow filtering.",
    )


    __table_args__ = (
        Index("idx_results_run", "run_id"),
        Index("idx_results_doc", "document_id"),
        Index("idx_results_severity", "run_id", "severity"),
        Index("idx_results_qc", "run_id", "qc_status"),
        Index(
            "idx_results_structured",
            "run_id",
            postgresql_where=(structured_data.isnot(None)),
        ),
        Index("idx_results_run_segment", "run_id", "segment_id"),
        Index("idx_results_chunk_id", "chunk_id"),
        Index(
            "idx_results_run_primary_segment",
            "run_id",
            "is_primary_segment",
            postgresql_where=(is_primary_segment.isnot(None)),
        ),
        Index(
            "uq_results_run_doc_check_no_segment",
            "run_id",
            "document_id",
            "check_id",
            unique=True,
            postgresql_where=(segment_id.is_(None)),
        ),
        Index(
            "uq_results_run_doc_segment_check",
            "run_id",
            "document_id",
            "segment_id",
            "check_id",
            unique=True,
            postgresql_where=(segment_id.isnot(None)),
        ),
        Index("idx_results_review_status", "run_id", "review_status"),
        Index(
            "idx_results_manual_review",
            "run_id",
            "needs_manual_review",
            postgresql_where=(needs_manual_review.is_(True)),
        ),
    )

class CheckResultPresentation(Base):
    """
    Locale-specific presentation of a canonical CheckResult.

    The canonical CheckResult owns execution, evidence, provenance, QC, and
    factual result identity. This child model stores only user-facing content
    for one presentation locale and one source-content version.
    """

    __tablename__ = "check_result_presentations"

    check_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("check_results.id", ondelete="CASCADE"),
        nullable=False,
        comment="Canonical CheckResult to which this presentation belongs.",
    )

    locale: Mapped[str] = mapped_column(
        String(35),
        nullable=False,
        comment="BCP 47 presentation locale, for example en, ru, de, fr.",
    )

    content_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "Immutable source-content version identifier for this presentation. "
            "A new source version must not overwrite an approved older version."
        ),
    )

    source_content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "SHA-256 hash of canonical source fields used to produce "
            "this locale-specific presentation."
        ),
    )

    source_locale: Mapped[str | None] = mapped_column(
        String(35),
        nullable=True,
        comment="Language of canonical source content when known.",
    )

    localized_check_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment=(
            "Locale-specific check name when it is not supplied "
            "by a stable playbook translation dictionary."
        ),
    )

    display_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Locale-specific primary factual result text.",
    )

    review_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Locale-specific review explanation for the result drawer.",
    )

    dd_request_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Locale-specific DD request text when applicable.",
    )

    translation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment=(
            "Presentation lifecycle: pending, processing, ready, failed, "
            "reviewed, approved, stale."
        ),
    )

    translation_provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Translation provider identifier, if generated externally.",
    )

    translation_model: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Translation model identifier or version.",
    )

    translation_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Translation provenance, diagnostics, usage, source fields, "
            "and batch metadata."
        ),
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last presentation-generation failure message, if any.",
    )

    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who reviewed this locale-specific presentation.",
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when this presentation was reviewed.",
    )

    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who approved this presentation for controlled output.",
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when this presentation was approved.",
    )

    __table_args__ = (
        UniqueConstraint(
            "check_result_id",
            "locale",
            "content_version",
            name="uq_check_result_presentations_identity",
        ),
        Index(
            "idx_check_result_presentations_result_locale",
            "check_result_id",
            "locale",
        ),
        Index(
            "idx_check_result_presentations_locale_status",
            "locale",
            "translation_status",
        ),
        Index(
            "idx_check_result_presentations_source_hash",
            "source_content_hash",
        ),
    )
