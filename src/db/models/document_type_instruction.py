# src/db/models/document_type_instruction.py

"""
Document type instruction version model.

Хранит версионированную инструкцию для конкретного doc_type.

Lifecycle:
  draft → published → archived

Ownership scopes:
  - platform: tenant_id IS NULL, видима всем tenant'ам на чтение
  - tenant:   tenant_id IS NOT NULL, принадлежит одному tenant'у

Инварианты:
- только draft может быть изменён;
- published версия immutable: YAML, compiled_payload, hash не меняются;
- только одна published platform версия на doc_type;
- только одна published tenant версия на (doc_type, tenant_id);
- immutable_content_hash выставляется единожды при publish;
- tenant не редактирует platform instruction inplace;
- identical source snapshots могут существовать:
  - один раз на platform уровне;
  - по одному разу в каждом tenant-space.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DocumentTypeInstructionVersion(Base):
    __tablename__ = "document_type_instruction_versions"

    doc_type_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Machine-readable document type code, e.g. 'nda', 'real_estate_sale'.",
    )

    name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        comment="Optional display name of the document type instruction.",
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "NULL = platform-owned instruction visible to all tenants. "
            "Non-null = tenant-owned instruction visible only inside this tenant."
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
        comment="Source format of the instruction snapshot, currently 'yaml'.",
    )

    source_yaml: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full raw YAML snapshot used for classification.",
    )

    source_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA256 hash of the raw YAML snapshot.",
    )

    source_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Original repository/registry path of the YAML file, if known.",
    )

    git_commit: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Git commit hash of the source repository, if available.",
    )

    semver: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Optional human-readable semantic version, if maintained manually.",
    )

    compiled_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Normalized compiled representation of the instruction.",
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
        comment=(
            "Canonical SHA256 of compiled_payload. "
            "Set once at publish time, never changed after."
        ),
    )

    validation_report: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Validation diagnostics produced at compile/publish time.",
    )

    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_type_instruction_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Version this draft was derived from (for audit trail).",
    )

    derived_from_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_type_instruction_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "If this tenant-owned instruction was copied/derived from another "
            "instruction version, stores the source version id."
        ),
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this version was published.",
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created this instruction version.",
    )

    change_summary: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Human-readable summary of changes in this version.",
    )

    __table_args__ = (
        Index(
            "idx_doc_type_instruction_versions_doc_type_code",
            "doc_type_code",
        ),
        Index(
            "ix_document_type_instruction_versions_tenant_id",
            "tenant_id",
        ),
        Index(
            "idx_doc_type_instruction_versions_sha256",
            "source_sha256",
        ),
        Index(
            "idx_doc_type_instruction_versions_status",
            "doc_type_code",
            "version_status",
        ),
        Index(
            "uix_doc_type_instruction_versions_platform_source_sha256",
            "doc_type_code",
            "source_sha256",
            unique=True,
            postgresql_where=text("owner_scope = 'platform'"),
        ),
        Index(
            "uix_doc_type_instruction_versions_tenant_source_sha256",
            "doc_type_code",
            "source_sha256",
            "tenant_id",
            unique=True,
            postgresql_where=text("owner_scope = 'tenant'"),
        ),
        Index(
            "uix_doc_type_instr_ver_one_published_platform",
            "doc_type_code",
            unique=True,
            postgresql_where=text(
                "version_status = 'published' AND owner_scope = 'platform'"
            ),
        ),
        Index(
            "uix_doc_type_instr_ver_one_published_tenant",
            "doc_type_code",
            "tenant_id",
            unique=True,
            postgresql_where=text(
                "version_status = 'published' AND owner_scope = 'tenant'"
            ),
        ),
        CheckConstraint(
            "((owner_scope = 'platform' AND tenant_id IS NULL) "
            "OR (owner_scope = 'tenant' AND tenant_id IS NOT NULL))",
            name="ck_doc_type_instruction_versions_owner_scope_tenant",
        ),
    )


    