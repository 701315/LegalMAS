"""
Legal glossary model for translation quality enforcement (Sprint 3.1).

Stores source→target term mappings used to inject domain-specific
vocabulary into LLM translation prompts.

Ownership:
- tenant_id IS NULL  → platform-wide glossary, visible to all tenants.
- tenant_id NOT NULL → tenant-specific override, takes precedence
  during glossary resolution (S3.2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class LegalGlossary(Base):
    """
    Single source→target legal term mapping.

    Inherits from Base: id (UUID PK), created_at, updated_at.

    Properties:
    - tenant_id: NULL = platform-wide; non-NULL = tenant override.
    - source_locale / target_locale: BCP-47 pair, e.g. 'ru' → 'en'.
    - source_term / target_term: the actual glossary entry.
    - term_category: optional domain tag for filtering.
    - context_note: optional disambiguation hint for the LLM.
    - is_active: soft-delete flag; inactive entries excluded from resolution.
    - created_by: audit trail — who imported or authored this entry.
    """

    __tablename__ = "legal_glossaries"

    # ── Multi-tenancy ────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL = platform-wide glossary entry.",
    )

    # ── Locale pair ──────────────────────────────────────────────
    source_locale: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="BCP-47 source language, e.g. 'ru'.",
    )
    target_locale: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="BCP-47 target language, e.g. 'en'.",
    )

    # ── Term content ─────────────────────────────────────────────
    source_term: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Original term in source_locale.",
    )
    target_term: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Canonical translation in target_locale.",
    )
    term_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Domain category, e.g. 'contract_law', 'corporate_law'.",
    )
    context_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Disambiguation note for the translator / LLM.",
    )

    # ── Status ───────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Inactive entries are excluded from glossary resolution.",
    )

    # ── Provenance ───────────────────────────────────────────────
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created or imported this entry.",
    )

    # ── Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        # Fast batch lookup by locale pair (glossary resolver S3.2)
        Index(
            "idx_legal_glossary_locale_pair",
            "source_locale",
            "target_locale",
        ),
        # Partial unique: no two ACTIVE entries with same tenant+pair+term
        Index(
            "uix_legal_glossary_active_term",
            "tenant_id",
            "source_locale",
            "target_locale",
            "source_term",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )
