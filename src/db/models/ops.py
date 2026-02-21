"""
Operational models: IdempotencyKey, AuditLog, DLQRecord.
IdempotencyKey — prevents duplicate API requests.
AuditLog — immutable log of all actions (no UPDATE/DELETE).
DLQRecord — dead letter queue for failed tasks.
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


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

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    artifact_refs: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(1000)),
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    next_action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="retry_manual",
        comment="retry_manual, skip, escalate",
    )
