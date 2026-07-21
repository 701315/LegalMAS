# src/db/models/playbook.py

"""
Playbook, PlaybookVersion and ModelConfig models.
Playbook — logical playbook line (product-level template).
PlaybookVersion — a version of DD check definitions (YAML compiled to JSON).
ModelConfig — configuration of ML models used by the runner.

Дополнительно:
PlaybookLineItem — элементы логического плейбука (строки конструктора):
- ссылка на конкретную инструкцию из global instruction catalog (instruction_code),
- с порядком отображения (order_index).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.constants import PlaybookStatus

from ..base import Base


class ModelConfig(Base):
    __tablename__ = "model_configs"

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    embeddings_primary: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="intfloat/multilingual-e5-large",
    )

    embeddings_fallback: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        default="cointegrated/LaBSE",
    )

    retrieval_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="candidate_n, llm_context_k, etc.",
    )

    scoring_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="dense_weight, sparse_weight, metadata_boost",
    )


class Playbook(Base):
    """
    Logical playbook line (template).

    Example: 'Real estate RU (core DD)', 'M&A RU full', 'NDA EN'.
    Stores high-level semantics: type of deal, jurisdiction, language, etc.
    Versions of this playbook are stored in PlaybookVersion.
    """

    __tablename__ = "playbooks"

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Machine-readable code, e.g. 'real_estate_ru_core'.",
    )

    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        comment="Display name for UI, e.g. 'Real estate RU (core DD)'.",
    )

    description: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Optional description for UI.",
    )

    deal_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Deal type: real_estate, mna, nda, corporate, etc.",
    )

    jurisdiction: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Primary jurisdiction: e.g. RU, EN, DE.",
    )

    language: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="Primary language: e.g. 'ru', 'en'.",
    )

    risk_profile: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Optional risk/profile label: standard/high/vendor/buyer/etc.",
    )

    # Связь с элементами конструктора (строками шаблона).
    # Один Playbook (линия) может содержать много элементов (topics/checks).
    line_items: Mapped[list["PlaybookLineItem"]] = relationship(
        "PlaybookLineItem",
        back_populates="playbook",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PlaybookVersion(Base):
    __tablename__ = "playbook_versions"

    # link to logical Playbook (optional for backward compatibility).
    playbook_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="SET NULL"),
        nullable=True,
        comment="Logical Playbook this version belongs to.",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="E.g. M&A_RU",
    )

    semver: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Semantic version: 1.0.0, 2.3.1",
    )

    git_commit: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Git commit hash",
    )

    yaml_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA256 of YAML source file",
    )

    compiled_checks: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Compiled check definitions from YAML",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PlaybookStatus.DRAFT.value,
        comment="Lifecycle: draft, published, archived. Legacy: stable, default.",
    )

    is_default: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        comment="True if this is the global default version for new deals.",
    )

    immutable_content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Canonical SHA256 of compiled_checks. Set at publish, never changed after.",
    )

    validation_report: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Validation diagnostics from compile/publish.",
    )

    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Version this draft was derived from.",
    )

    source_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Canonical source specification used to build this version. "
            "Contains bundles/include_ids/exclude_ids/profile/"
            "model_config_id/from_line_id. "
            "NULL for legacy YAML-based versions."
        ),
    )

    source_payload_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Deterministic SHA256 of canonical JSON serialization of source_payload.",
    )


    model_config_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("model_configs.id"),
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this version was published (immutable).",
    )

    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this version was promoted to default.",
    )

    trigger_definitions: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Trigger definitions from YAML: "
            "{'residential_property': {'any_keywords': ['квартира', 'жилой дом']}}"
        ),
    )

    dd_request_templates: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "DD request templates from YAML: "
            "[{'if_check_fails': 'encumbrances_warranty', 'request': '...'}]"
        ),
    )

    section_markers: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Section markers for Structure Builder: "
            "['Предмет договора', 'Цена и порядок расчетов']"
        ),
    )

    classification_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Classification config: "
            "{'keywords': {...}, 'exclusions': [...], 'weights': {...}, 'patterns': {...}}"
        ),
    )

    __table_args__ = (
        Index("idx_playbook_versions_status", "status"),
        Index(
            "uix_playbook_versions_one_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )

class PlaybookLineItem(Base):
    """
    Элемент логического плейбука (строка конструктора).

    Один элемент = одна инструкция из instruction/global catalog.
    Компиляция плейбука опирается на instruction_code напрямую.
    """

    __tablename__ = "playbook_line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key",
    )

    line_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("playbooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Playbook (logical line) this item belongs to.",
    )

    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Element type. Currently supported: 'check'.",
    )

    instruction_code: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Canonical instruction code from global instruction catalog.",
    )

    order_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order of items within the playbook line for UI/compilation.",
    )

    playbook: Mapped[Playbook] = relationship(
        "Playbook",
        back_populates="line_items",
    )