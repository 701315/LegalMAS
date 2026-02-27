"""add document families and members

Revision ID: cf3726abeb23
Revises: c2615169b7f9
Create Date: 2026-02-27 22:13:19.672606

"""
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import UUID

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf3726abeb23'
down_revision: Union[str, None] = 'c2615169b7f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_families",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("deal_id", UUID(as_uuid=True), sa.ForeignKey("deals.id"), nullable=False),
        sa.Column("master_doc_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column(
            "master_classification_level",
            sa.String(10),
            nullable=True,
            comment="Classification level of master doc L0, L1, L2, L3",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_document_families_deal_id",
        "document_families",
        ["deal_id"],
    )
    op.create_index(
        "ix_document_families_master_level",
        "document_families",
        ["master_classification_level"],
    )

    op.create_table(
        "document_family_members",
        sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("document_families.id"), nullable=False),
        sa.Column("doc_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("relation_to_master", sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint("family_id", "doc_id"),
    )


def downgrade() -> None:
    op.drop_table("document_family_members")
    op.drop_index("ix_document_families_master_level", table_name="document_families")
    op.drop_index("ix_document_families_deal_id", table_name="document_families")
    op.drop_table("document_families")
