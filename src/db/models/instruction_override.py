# src/db/models/instruction_override.py

"""
Instruction override model.

Хранит diff-based override инструкции типа документа для конкретной сделки (проекта),
БЕЗ полного дублирования YAML.

Зачем это нужно:
- override должен применяться поверх конкретной базовой instruction version
  как JSON Patch (RFC 6902), а не как отдельная полная копия YAML;
- base_content_hash фиксирует, к какой именно версии базового источника
  был создан patch — если базовая версия изменится, override помечается
  как is_stale и требует ручного rebase;
- change_summary и created_by дают человеко-читаемый audit trail изменений.

Правила применения (реализуются в InstructionOverrideService, не здесь):
- apply должен падать явно при конфликте patch, без silent fallback;
- JSON Patch test-операции используются для структурной безопасности;
- один override на пару (deal_id, instruction_version_id) — обеспечивается
  UNIQUE constraint.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class InstructionOverride(Base):
    """
    Override инструкции типа документа для конкретной сделки.

    Для непрофессионального программиста:
    - одна запись = один набор изменений (patch) поверх одной версии
      базовой YAML-инструкции, привязанный к конкретному проекту (deal_id);
    - patch_ops хранит сами изменения в формате JSON Patch (RFC 6902),
      а не полный текст YAML;
    - is_stale = True означает, что базовая версия инструкции с тех пор
      изменилась, и override нужно пересмотреть перед использованием.
    """

    __tablename__ = "instruction_overrides"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Deal/project scope for this override.",
    )

    instruction_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_type_instruction_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Base instruction version this override is derived from.",
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
        UniqueConstraint(
            "deal_id",
            "instruction_version_id",
            name="uq_instruction_overrides_deal_version",
        ),
        Index(
            "idx_instruction_overrides_deal_stale",
            "deal_id",
            "is_stale",
        ),
    )