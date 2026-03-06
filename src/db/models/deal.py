"""
Deal model — top-level entity representing an M&A transaction.
Each deal belongs to a tenant and contains bundles of documents.
"""

import uuid

from sqlalchemy import Index, String, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import DealStatus, PIIMode
from ..base import Base


class Deal(Base):
    __tablename__ = "deals"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    deal_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="E.g. SPA, SHA, Asset Purchase",
    )

    jurisdiction: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="E.g. RU, EN, RU/EN",
    )

    languages: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(10)),
        nullable=True,
        comment="Document languages: ['RU', 'EN']",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DealStatus.CREATED.value,
    )

    pii_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=PIIMode.LOCAL_ONLY.value,
        comment="152-FZ: local_only or cloud_fallback_allowed",
    )

    profile: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="full",
        comment="Check profile: core, full, max",
    )

    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Selected playbook version (FK added after PlaybookVersion model)",
    )

    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of the latest analysis run for this deal",
    )

    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
        comment="Arbitrary deal metadata",
    )

    __table_args__ = (Index("idx_deals_tenant_status", "tenant_id", "status"),)
