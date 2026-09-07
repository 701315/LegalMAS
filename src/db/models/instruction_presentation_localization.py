# src/db/models/instruction_presentation_localization.py

"""
Instruction presentation localization model (Sprint 4.1).

Stores translations and labels for static system artifacts, such as
DD Grid headers, column names, playbook check titles, and UI field keys.

Ownership & Precedence:
- tenant_id IS NULL  → platform-wide static localization, visible to all tenants.
- tenant_id NOT NULL → tenant-specific static label override.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class InstructionPresentationLocalization(Base):
    """
    Localized presentation record for an instruction or UI key.

    Inherits from Base: id (UUID PK), created_at, updated_at.

    Properties:
    - tenant_id: NULL = platform-wide fallback; non-NULL = tenant override.
    - instruction_key: unique stable dot-separated key, e.g. 'dd_grid.column.severity'.
    - locale: BCP-47 locale code, e.g. 'ru', 'en'.
    - label: the localized name to show in the UI/Grid.
    - description: optional context note or tooltip explanation.
    - is_active: soft-delete flag. Inactive entries are ignored during resolution.
    - created_by: audit trail — who created this localization entry.
    """

    __tablename__ = "instruction_presentation_localizations"

    # ── Multi-tenancy ────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL = platform-wide fallback localization entry.",
    )

    # ── Identity & Locale ────────────────────────────────────────
    instruction_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment=(
            "Stable dot-separated key representing the target UI entity, "
            "e.g. 'dd_grid.column.severity' or a playbook check code."
        ),
    )

    locale: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="BCP-47 target language code, e.g. 'en', 'ru'.",
    )

    # ── Content ──────────────────────────────────────────────────
    label: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Translated display name / header label.",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional tooltip description or helper text.",
    )

    # ── Status ───────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Inactive localizations are excluded from resolving.",
    )

    # ── Provenance ───────────────────────────────────────────────
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created or uploaded this localization entry.",
    )

    # ── Indexes ──────────────────────────────────────────────────
    __table_args__ = (
        # Fast lookup by key and locale (used by the grid presentation builder)
        Index(
            "idx_instruction_localization_lookup",
            "instruction_key",
            "locale",
        ),
        # Partial unique constraint: enforce single active translation per tenant-key-locale.
        Index(
            "uix_instruction_localization_unique_active",
            "tenant_id",
            "instruction_key",
            "locale",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )


