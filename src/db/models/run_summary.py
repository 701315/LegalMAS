# src/db/models/run_summary.py

"""
RunSummary model — LLM-generated executive summary for a completed run.

Lifecycle:
1. Run completes → summary record created with status='pending'
2. Dispatcher picks up → status='generating'
3. LLM generation completes → status='ready' (text populated) or 'failed' (fallback only)

Architectural principles:
- 1-to-1 with runs (UNIQUE run_id) — one active summary per run;
- fallback JSONB is ALWAYS populated (deterministic overview, no LLM);
- text/claims populated only when LLM generation + validation passed;
- provenance fields (model, prompt_version) for auditability.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class RunSummary(Base):
    __tablename__ = "run_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending | generating | ready | failed",
    )

    text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="LLM-generated markdown with [F-XXXX] citations",
    )

    claims: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Pass A output: structured claims with finding_ids",
    )

    fallback: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Deterministic structured overview (always available)",
    )

    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="LLM model used (e.g., qwen2.5:14b-instruct)",
    )

    prompt_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Prompt template version (e.g., executive_summary_v1)",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if generation failed",
    )

    retry_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
        comment="Number of failed generation attempts",
    )

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Scheduled time for the next generation attempt (backoff)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


    