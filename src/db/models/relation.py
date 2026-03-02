"""
DocumentRelation and family models.

DocumentRelation — связь между двумя документами (master-appendix, amendment, version и т.п.).
DocumentFamily / DocumentFamilyMember — группа связанных документов с одним мастером.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class DocumentFamily(Base):
    __tablename__ = "document_families"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

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
    master_classification_level: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="L0, L1, L2, L3 from HybridClassifier result",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    members: Mapped[list["DocumentFamilyMember"]] = relationship(
        "DocumentFamilyMember",
        back_populates="family",
        lazy="selectin",
    )


class DocumentFamilyMember(Base):
    __tablename__ = "document_family_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_families.id", ondelete="CASCADE"),
        nullable=False,
    )

    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    relation_to_master: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    family: Mapped[DocumentFamily] = relationship(
        "DocumentFamily",
        back_populates="members",
    )

    __table_args__ = (
        UniqueConstraint(
            "family_id",
            "doc_id",
            name="uq_document_family_members_family_doc",
        ),
    )


class DocumentRelation(Base):
    __tablename__ = "document_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

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
        comment="master, appendix, amendment, version, etc.",
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    # Если потом захочешь связать relation с family, можно добавить поле family_id -> DocumentFamily.id.
    # Сейчас оставляем без этого, чтобы точно совпадать с существующей таблицей document_relations.

    __table_args__ = (
        Index("idx_relations_deal_source", "deal_id", "source_doc_id"),
        Index("idx_relations_deal_target", "deal_id", "target_doc_id"),
        Index("idx_relations_deal_type", "deal_id", "relation_type"),
        Index(
            "idx_relations_traversal",
            "deal_id",
            "source_doc_id",
            "relation_type",
            confidence.desc(),
        ),
    )
