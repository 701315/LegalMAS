# src/db/models/ops.py

"""
Operational models: IdempotencyKey, AuditLog, DLQRecord.

Назначение слоя ops:
- хранить операционные данные, которые помогают делать backend предсказуемым и поддерживаемым;
- не относятся напрямую к бизнес‑сущностям (сделки, документы), но описывают,
  как ими пользовались и что происходило с задачами.

Что делает каждая модель:

- IdempotencyKey
  - предотвращает повторную обработку одинаковых API‑запросов (idempotent POST/PUT);
  - хранит статус обработки (processing/completed/failed), кешированный результат и срок жизни;
  - по tenant_id + endpoint + idempotency_key позволяет безопасно переигрывать запросы
    и возвращать тот же ответ без повторного запуска пайплайна.

- AuditLog
  - неизменяемый журнал действий в системе (INSERT‑only, без UPDATE/DELETE);
  - фиксирует, кто и что сделал: импорт, запуск Run, санитизация PII, доступ к документам и т.п.;
  - используется для аудита, расследований и объяснимости результатов анализа для юристов.

- DLQRecord
  - хранит записи о задачах, которые окончательно не смогли завершиться (после всех ретраев);
  - задаёт единый формат для операционной DLQ: тип задачи, тип сбоя, error_details, артефакты;
  - помогает support‑команде находить, разбирать и при необходимости вручную переигрывать упавшие задачи.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    endpoint: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="processing",
        comment="processing, completed, failed",
    )

    response_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    result: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Cached response for replay",
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "endpoint",
            "idempotency_key",
            name="uq_idempotency_tenant_endpoint_key",
        ),
        Index("idx_idempotency_tenant_key", "tenant_id", "idempotency_key"),
        Index("idx_idempotency_expires", "expires_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="IMPORT, EXTRACT, SANITIZE, RUN, EXPORT, QC_ACTION, PII_ACCESS, etc.",
    )

    actor: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="User email or system identifier",
    )

    actor_role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    __table_args__ = (
        Index("idx_audit_deal_action", "deal_id", "action"),
        Index("idx_audit_tenant_created", "tenant_id", "created_at"),
    )


class DLQRecord(Base):
    __tablename__ = "dlq_records"

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    source_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original Celery task_id that produced this DLQ record",
    )

    task_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    failure_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="transient, permanent, timeout, quota",
    )

    dedupe_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional stable fingerprint for deduplication/grouping of repeated failures",
    )

    error_details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    artifact_refs: Mapped[list[str]] = mapped_column(
        ARRAY(String(1000)),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    next_action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="retry_manual",
        server_default=text("'retry_manual'"),
        comment="retry_manual, skip, escalate",
    )

    __table_args__ = (
        Index("idx_dlq_created_at", "created_at"),
        Index("idx_dlq_task_failure_created", "task_type", "failure_type", "created_at"),
        Index("idx_dlq_next_action_created", "next_action", "created_at"),
        Index("idx_dlq_source_task_id", "source_task_id"),
        Index("idx_dlq_dedupe_key", "dedupe_key"),
    )

