"""add doc type instruction version id to documents

Revision ID: 54915a77fedb
Revises: 811cee605b40
Create Date: 2026-05-07 11:15:52.018162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '54915a77fedb'
down_revision: Union[str, None] = '811cee605b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "doc_type_instruction_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Persisted YAML instruction snapshot used for document classification",
        ),
    )

    op.create_foreign_key(
        "fk_documents_doc_type_instruction_version_id",
        "documents",
        "document_type_instruction_versions",
        ["doc_type_instruction_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "idx_documents_instruction_version",
        "documents",
        ["doc_type_instruction_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_documents_instruction_version",
        table_name="documents",
    )

    op.drop_constraint(
        "fk_documents_doc_type_instruction_version_id",
        "documents",
        type_="foreignkey",
    )

    op.drop_column("documents", "doc_type_instruction_version_id")