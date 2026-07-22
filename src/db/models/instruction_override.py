# src/db/models/instruction_override.py

"""
Instruction override model.

Хранит patch-based override инструкции типа документа.

Поддерживаемые scope:
- tenant override:
    tenant_id задан,
    deal_id = NULL,
    override_scope = 'tenant'
- deal override:
    tenant_id задан,
    deal_id задан,
    override_scope = 'deal'

Lifecycle:
- draft
- active
- archived

Зачем это нужно:
- override должен применяться поверх конкретной базовой instruction version
  как JSON Patch (RFC 6902), а не как отдельная полная копия YAML;
- tenant-level override позволяет переопределять базовую published instruction
  для всего tenant-space;
- deal-level override позволяет переопределять tenant/base state только
  для одной сделки;
- archived overrides должны сохраняться для audit/history и не блокировать
  создание новой live override на тот же target.

Правила применения (реализуются в service-слое, не здесь):
- apply должен падать явно при конфликте patch, без silent fallback;
- JSON Patch test-операции используются для структурной безопасности;
- одновременно может существовать только одна неархивная tenant override
  на (tenant_id, instruction_version_id);
- одновременно может существовать только одна неархивная deal override
  на (deal_id, instruction_version_id).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class InstructionOverride(Base):
    """
    Patch-based override инструкции типа документа.

    Для непрофессионального программиста:
    - одна запись = один набор изменений (patch) поверх одной версии
      базовой инструкции;
    - override может действовать либо на весь tenant, либо только на одну сделку;
    - patch_ops хранит сами изменения в формате JSON Patch (RFC 6902),
      а не полный текст YAML;
    - is_stale = True означает, что базовая версия инструкции с тех пор
      изменилась, и override нужно пересмотреть перед использованием.
    """

    __tablename__ = "instruction_overrides"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment=(
            "Tenant that owns this override. "
            "Used for authorization and tenant isolation."
        ),
    )

    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment=(
            "Deal/project scope for this override. "
            "NULL for tenant-level overrides."
        ),
    )

    instruction_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_type_instruction_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Base instruction version this override is derived from.",
    )


    global_instruction_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("global_instruction_versions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment=(
            "Global instruction version this override is derived from. "
            "Mutually exclusive with instruction_version_id: "
            "exactly one must be non-null."
        ),
    )


    override_scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="deal",
        server_default=text("'deal'"),
        comment="Override scope: tenant | deal",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
        comment="Lifecycle status: draft | active | archived",
    )

    base_content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Expected source hash of the base version at override creation time.",
    )

    patch_ops: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        comment="RFC 6902 JSON Patch operations.",
    )

    is_stale: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True if base instruction version changed and override must be rebased.",
    )

    change_summary: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Human-readable summary of override changes.",
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created this override.",
    )

    __table_args__ = (
        Index(
            "idx_instruction_overrides_deal_stale",
            "deal_id",
            "is_stale",
        ),
        Index(
            "idx_instruction_overrides_scope_status",
            "tenant_id",
            "override_scope",
            "status",
        ),
        Index(
            "uix_instruction_overrides_deal_version_live",
            "deal_id",
            "instruction_version_id",
            unique=True,
            postgresql_where=text(
                "override_scope = 'deal' AND status <> 'archived'"
            ),
        ),
        Index(
            "uix_instruction_overrides_tenant_version_live",
            "tenant_id",
            "instruction_version_id",
            unique=True,
            postgresql_where=text(
                "override_scope = 'tenant' AND status <> 'archived'"
            ),
        ),
        CheckConstraint(
            "((override_scope = 'tenant' AND deal_id IS NULL) "
            "OR (override_scope = 'deal' AND deal_id IS NOT NULL))",
            name="ck_instruction_overrides_scope_deal_id",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_instruction_overrides_status",
        ),
        CheckConstraint(
            "((instruction_version_id IS NOT NULL AND global_instruction_version_id IS NULL) "
            "OR (instruction_version_id IS NULL AND global_instruction_version_id IS NOT NULL))",
            name="ck_instruction_overrides_version_id_xor",
        ),
    )


    