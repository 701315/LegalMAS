# src/db/models/global_instruction.py

"""
Global instruction version model.

Хранит версионированную инструкцию, применимую к любому типу документа
(confidentiality, governing law, term и т.д.).

Паттерн идентичен DocumentTypeInstructionVersion.
Ключевые отличия:
- instruction_code вместо doc_type_code
- group (nullable) для группировки в каталоге
- нет derived_from_version_id (нет cross-scope copy-on-write)
- нет привязки к doc_type; применимость хранится в compiled_payload

Lifecycle: draft → published → archived
Ownership: platform (tenant_id IS NULL) | tenant (tenant_id NOT NULL)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class GlobalInstructionVersion(Base):
    __tablename__ = "global_instruction_versions"

    instruction_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment=(
            "Machine-readable instruction family code, "
            "e.g. 'confidentiality_and_trade_secrets', 'governing_law'. "
            "Matches the 'id' field in the source YAML."
        ),
    )

    name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        comment="Display name of the global instruction.",
    )

    group: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment=(
            "Grouping label for catalog UI, e.g. 'Confidentiality', 'Term'. "
            "Taken from YAML field 'group'."
        ),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "NULL = platform-owned, visible to all tenants. "
            "Non-null = tenant-owned, visible only inside this tenant."
        ),
    )

    owner_scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="platform",
        server_default=text("'platform'"),
        comment="Ownership scope: platform | tenant",
    )

    source_format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="yaml",
        server_default=text("'yaml'"),
        comment="Source format, currently 'yaml'.",
    )

    source_yaml: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full raw YAML snapshot of the global instruction.",
    )

    source_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA256 of the canonical source YAML.",
    )

    source_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Original file path, e.g. 'playbooks/global_checks/confidentiality/...'.",
    )

    git_commit: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Git commit hash of the source, if available.",
    )

    semver: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Optional semantic version.",
    )

    compiled_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Normalized compiled representation. "
            "Compatible with GlobalCheckConfig from core/playbooks/compiler.py."
        ),
    )

    version_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
        comment="Lifecycle status: draft | published | archived",
    )

    immutable_content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA256 of compiled_payload. Set once at publish, never changed.",
    )

    validation_report: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Validation diagnostics from compile/publish time.",
    )

    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("global_instruction_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Version this draft was cloned from (audit trail).",
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    change_summary: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "idx_global_instruction_versions_code",
            "instruction_code",
        ),
        Index(
            "idx_global_instruction_versions_tenant_id",
            "tenant_id",
        ),
        Index(
            "idx_global_instruction_versions_sha256",
            "source_sha256",
        ),
        Index(
            "idx_global_instruction_versions_status",
            "instruction_code",
            "version_status",
        ),
        Index(
            "idx_global_instruction_versions_group",
            "group",
        ),
        # Уникальность snapshot в platform scope
        Index(
            "uix_global_instruction_versions_platform_sha256",
            "instruction_code",
            "source_sha256",
            unique=True,
            postgresql_where=text("owner_scope = 'platform'"),
        ),
        # Уникальность snapshot в tenant scope
        Index(
            "uix_global_instruction_versions_tenant_sha256",
            "instruction_code",
            "source_sha256",
            "tenant_id",
            unique=True,
            postgresql_where=text("owner_scope = 'tenant'"),
        ),
        # Одна published platform version на instruction_code
        Index(
            "uix_global_instruction_versions_one_published_platform",
            "instruction_code",
            unique=True,
            postgresql_where=text(
                "version_status = 'published' AND owner_scope = 'platform'"
            ),
        ),
        # Одна published tenant version на (instruction_code, tenant_id)
        Index(
            "uix_global_instruction_versions_one_published_tenant",
            "instruction_code",
            "tenant_id",
            unique=True,
            postgresql_where=text(
                "version_status = 'published' AND owner_scope = 'tenant'"
            ),
        ),
        CheckConstraint(
            "((owner_scope = 'platform' AND tenant_id IS NULL) "
            "OR (owner_scope = 'tenant' AND tenant_id IS NOT NULL))",
            name="ck_global_instruction_versions_owner_scope_tenant",
        ),
    )


    