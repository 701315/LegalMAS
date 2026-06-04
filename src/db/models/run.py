# src/db/models/run.py

"""
Run and Job models.

Run — один полный запуск анализа по сделке / набору документов.
Job — одна фоновая задача внутри Run (например, import, extract, classify, run_deal_checks).

Почему это важно:
- Run хранит конфигурацию и итоговый статус всего запуска;
- Job хранит статус отдельных фоновых операций внутри запуска;
- фронтенд обычно работает в первую очередь с Run, потому что именно он отражает
  "общий прогресс анализа" для юриста.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import JobStatus, RunStatus

from ..base import Base


class Run(Base):
    __tablename__ = "runs"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    bundle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bundles.id", ondelete="SET NULL"),
        nullable=True,
    )

    playbook_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id"),
        nullable=False,
    )

    model_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_configs.id"),
        nullable=True,
    )

    environment_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="sha256(docker_image + lib_versions + model_weights)",
    )

    profile: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="full",
        comment="core, full, max",
    )

    checks_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="global_and_doc_type",
        comment=(
            "Режим проверок для этого Run: " "global_only / doc_type_only / global_and_doc_type"
        ),
    )

    checks_scope: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Сегментный scope для checks в этом Run. "
            "Например: {'scope_preset': 'primary_only'} "
            "или {'include_primary': true, 'include_segment_types': ['appendix']}"
        ),
    )

    pipeline_strategy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="REUSE_STRUCTURE",
        comment=(
            "Стратегия пайплайна для этого Run: "
            "REUSE_CHECKS_ONLY, REUSE_STRUCTURE, FULL_RERUN и т.п."
        ),
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=RunStatus.PENDING.value,
    )

    total_checks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    completed_checks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    has_errors: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="True, если в рамках этого Run есть ошибки или проблемные документы",
    )

    failed_docs_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество документов со статусом FAILED в этом Run/сделке",
    )

    quarantine_docs_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество документов со статусом QUARANTINE в этом Run/сделке",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    risk_summary_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="S3 URI to risk_summary.json",
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )


class Job(Base):
    __tablename__ = "jobs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    task_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment=(
            "import, extract, sanitize, structure, classify, " "run_deal_checks, aggregate, export"
        ),
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=JobStatus.QUEUED.value,
    )

    worker_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Celery worker hostname",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    __table_args__ = (Index("idx_jobs_run_status", "run_id", "status"),)
