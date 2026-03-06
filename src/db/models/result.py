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
        String(1000),
        nullable=True,
        comment="S3 URI or inline evidence snippet",
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

    __table_args__ = (
        Index("idx_results_run", "run_id"),
        Index("idx_results_doc", "document_id"),
        Index("idx_results_severity", "run_id", "severity"),
        Index("idx_results_qc", "run_id", "qc_status"),
        Index(
            "idx_results_structured",
            "run_id",
            postgresql_where="structured_data IS NOT NULL",
        ),
    )
