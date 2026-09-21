# src/db/models/check_result_anchor.py

"""
CheckResultAnchor — one anchor per finding, N per CheckResult.

Denormalized primary anchor (CheckResult.primary_anchor_id +
primary_anchor_method + primary_anchor_confidence + anchor_stale)
declared on CheckResult model (B1a update to result.py — см. шаг 5).
"""

import uuid

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CheckResultAnchor(Base):
    __tablename__ = "check_result_anchors"

    check_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("check_results.id", ondelete="CASCADE"),
        nullable=False,
        comment="Canonical CheckResult to which this anchor belongs.",
    )

    # ── Semantic ──────────────────────────────────────────────────────────
    clause_uid: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Effective clause UID, e.g. 'main_contract:7.3.2'.",
    )
    clause_ref: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Human-readable clause ref, e.g. 'п. 7.3.2'.",
    )
    quoted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Verbatim quote from source used as evidence.",
    )
    span_start: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Start char offset within canonical source text.",
    )
    span_end: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="End char offset (exclusive).",
    )
    source_content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hex of canonical source text at extraction time.",
    )

    # ── Geometric ─────────────────────────────────────────────────────────
    page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="1-based page number.",
    )
    layout_element_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="Layout element IDs covered by this anchor.",
    )
    bbox_union: Mapped[list[float] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Union bounding box [x0, top, x1, bottom] in PDF coords.",
    )
    segment_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Logical segment identifier within multi-doc file.",
    )

    # ── Provenance ────────────────────────────────────────────────────────
    anchor_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="CheckAnchorMethod value (StrEnum).",
    )
    anchor_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Confidence in [0.0, 1.0].",
    )
    anchor_validation_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if round-trip validation of the anchor passed.",
    )
    anchor_diagnostics: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Free-form diagnostics.",
    )

    # ── Primary flag (at most one per check_result_id) ────────────────────
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True for the single primary anchor of the CheckResult.",
    )

    __table_args__ = (
        Index("idx_cra_result", "check_result_id"),
        Index(
            "uq_cra_one_primary",
            "check_result_id",
            unique=True,
            postgresql_where=(is_primary.is_(True)),
        ),
        Index("idx_cra_document_clause", "segment_id", "clause_uid"),
        Index("idx_cra_document_span", "segment_id", "page", "span_start"),
    )

    