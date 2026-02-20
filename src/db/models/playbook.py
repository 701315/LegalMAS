"""
PlaybookVersion and ModelConfig models.
PlaybookVersion — a version of DD check definitions (YAML compiled to JSON).
ModelConfig — configuration of ML models used by the runner.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, Index, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import PlaybookStatus
from src.db.base import Base


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


class PlaybookVersion(Base):
    __tablename__ = "playbook_versions"

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
        comment="draft, stable, default (only one default allowed)",
    )

    model_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_configs.id"),
        nullable=True,
    )

    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this version was promoted to default",
    )

    __table_args__ = (
        Index("idx_playbook_status", "status"),
    )
