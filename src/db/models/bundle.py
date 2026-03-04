"""
Bundle model — a batch of documents imported together.
Each import operation creates one bundle within a deal.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import BundleSourceType
from db.base import Base


class Bundle(Base):
    __tablename__ = "bundles"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=BundleSourceType.ZIP.value,
        comment="zip, vdr_api, local",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    file_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
