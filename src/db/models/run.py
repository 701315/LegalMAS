"""
Run and Job models.
Run — a complete analysis execution against a deal/bundle.
Job — a single task within a run (one document, one processing step).
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import JobStatus
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

    model_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_configs.id"),
        nullable=False,
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

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
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

    started_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
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
        comment="import, extract, sanitize, structure, classify, run_checks, aggregate, export",
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
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
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
