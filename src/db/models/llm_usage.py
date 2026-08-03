# src/db/models/llm_usage.py

"""
LLMUsageEvent — immutable ledger записей потребления LLM-токенов.

Каждая запись = один LLM-вызов с привязкой к tenant/deal/run/document/stage.

Принципы:
- immutable: записи не обновляются, только создаются;
- best-effort: сбой записи не ломает основной pipeline;
- idempotent: request_uid + UniqueConstraint защищают от дублей при Celery retry.
"""

import uuid

from sqlalchemy import Boolean, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class LLMUsageEvent(Base):
    __tablename__ = "llm_usage_events"

    # ── Business context ──────────────────────────────────────────────────────

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Owner tenant. Denormalized for fast tenant-scoped queries.",
    )

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Deal (project) this LLM call belongs to.",
    )

    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Run that triggered this LLM call. NULL for calls outside a run.",
    )

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Document being processed. NULL for deal-level calls.",
    )

    # ── Stage ─────────────────────────────────────────────────────────────────

    stage: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "Pipeline stage: classification_l4 | checks_detection_llm | "
            "checks_extraction_llm | structure_semantic_enrichment | heading_refiner"
        ),
    )

    check_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Check identifier (e.g. coc_001). Only for checks stages.",
    )

    # ── LLM metadata ──────────────────────────────────────────────────────────

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="LLM provider: ollama | openai | llamacpp",
    )

    model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Model name or path.",
    )

    # ── Token accounting ──────────────────────────────────────────────────────

    prompt_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Input prompt tokens.",
    )

    completion_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Generated completion tokens.",
    )

    total_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total = prompt + completion. Computed on write.",
    )

    # ── Call quality ──────────────────────────────────────────────────────────

    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="LLM call wall time in milliseconds.",
    )

    llm_attempts: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of attempts including retries.",
    )

    parse_success: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="Whether LLM response was successfully parsed.",
    )

    error_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Error type if call failed. NULL on success.",
    )

    # ── Idempotency ───────────────────────────────────────────────────────────

    request_uid: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Unique id for this LLM call. Prevents duplicate entries on Celery retry.",
    )

    __table_args__ = (
        UniqueConstraint(
            "request_uid",
            name="uq_llm_usage_events_request_uid",
        ),
        Index("idx_llm_usage_deal_stage", "deal_id", "stage"),
        Index("idx_llm_usage_deal_created", "deal_id", "created_at"),
        Index("idx_llm_usage_run", "run_id"),
        Index("idx_llm_usage_tenant_created", "tenant_id", "created_at"),
    )

