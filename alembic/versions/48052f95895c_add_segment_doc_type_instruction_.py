"""add segment doc type instruction version id

Revision ID: 48052f95895c
Revises: 54915a77fedb
Create Date: 2026-05-07 11:49:25.473678

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '48052f95895c'
down_revision: Union[str, None] = '54915a77fedb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_segments",
        sa.Column(
            "segment_doc_type_instruction_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Persisted YAML instruction snapshot used for segment classification",
        ),
    )

    op.create_foreign_key(
        "fk_document_segments_instruction_version_id",
        "document_segments",
        "document_type_instruction_versions",
        ["segment_doc_type_instruction_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "idx_document_segments_instruction_version",
        "document_segments",
        ["segment_doc_type_instruction_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_document_segments_instruction_version",
        table_name="document_segments",
    )

    op.drop_constraint(
        "fk_document_segments_instruction_version_id",
        "document_segments",
        type_="foreignkey",
    )

    op.drop_column("document_segments", "segment_doc_type_instruction_version_id")