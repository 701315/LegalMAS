"""
DocumentRelation and Family models.
DocumentRelation — link between two documents (master-appendix, amendment, etc.).
Family — group of related documents with one master.
"""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import RelationType
from src.db.base import Base


class Family(Base):
    __tablename__ = "families"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    master_doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )


class DocumentRelation(Base):
    __tablename__ = "document_relations"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    target_doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    relation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="master, appendix, amendment, etc.",
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        comment="Detection confidence 0.0-1.0",
    )

    evidence_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Why this relation was detected",
    )

    family_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_relations_deal_source", "deal_id", "source_doc_id"),
        Index("idx_relations_deal_target", "deal_id", "target_doc_id"),
        Index("idx_relations_deal_type", "deal_id", "relation_type"),
        Index(
            "idx_relations_family",
            "family_id",
            postgresql_where="family_id IS NOT NULL",
        ),
        Index(
            "idx_relations_traversal",
            "deal_id",
            "source_doc_id",
            "relation_type",
            confidence.desc(),
        ),
    )
