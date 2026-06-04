# src/db/models/dd_request.py

"""
DDRequest model — persistent due diligence request for a deal.


Used for the "Requests" tab and exports (Request List / Appendix A).
"""


import uuid
from datetime import UTC, datetime


from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


from ..base import Base



class DDRequest(Base):
    __tablename__ = "dd_requests"


    # id из Base: UUID primary key


    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Deal this request belongs to",
    )


    title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional short title for the request",
    )


    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="critical | high | medium",
    )


    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Full request text for the counterparty",
    )


    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="open | in_progress | resolved",
    )


    check_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Originating check_id (if auto-generated from analysis/YAML)",
    )


    addressee: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Юридический советник",
        comment="Who the request is addressed to",
    )


    structured_values: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Structured values mentioned in the request (dates, amounts, etc.)",
    )


    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
        comment="Source of request: manual | yaml_template | aggregator",
    )


    # References to related documents and evidences as UUIDs
    document_refs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        comment="Related document IDs",
    )


    evidence_refs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        comment="Related check_result/evidence IDs",
    )


    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
