"""add document type instruction versions

Revision ID: 811cee605b40
Revises: 32193ce38171
Create Date: 2026-05-07 11:04:29.350797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '811cee605b40'
down_revision: Union[str, None] = '32193ce38171'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_type_instruction_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "doc_type_code",
            sa.String(length=100),
            nullable=False,
            comment="Machine-readable document type code, e.g. 'nda', 'real_estate_sale'.",
        ),
        sa.Column(
            "name",
            sa.String(length=300),
            nullable=True,
            comment="Optional display name of the document type instruction.",
        ),
        sa.Column(
            "source_format",
            sa.String(length=20),
            nullable=False,
            server_default="yaml",
            comment="Source format of the instruction snapshot, currently 'yaml'.",
        ),
        sa.Column(
            "source_yaml",
            sa.Text(),
            nullable=False,
            comment="Full raw YAML snapshot used for classification.",
        ),
        sa.Column(
            "source_sha256",
            sa.String(length=64),
            nullable=False,
            comment="SHA256 hash of the raw YAML snapshot.",
        ),
        sa.Column(
            "source_path",
            sa.String(length=1000),
            nullable=True,
            comment="Original repository/registry path of the YAML file, if known.",
        ),
        sa.Column(
            "git_commit",
            sa.String(length=40),
            nullable=True,
            comment="Git commit hash of the source repository, if available.",
        ),
        sa.Column(
            "semver",
            sa.String(length=20),
            nullable=True,
            comment="Optional human-readable semantic version, if maintained manually.",
        ),
        sa.Column(
            "compiled_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Optional normalized/compiled representation of the instruction.",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "doc_type_code",
            "source_sha256",
            name="uq_doc_type_instruction_versions_doc_type_code_sha256",
        ),
    )

    op.create_index(
        "idx_doc_type_instruction_versions_doc_type_code",
        "document_type_instruction_versions",
        ["doc_type_code"],
        unique=False,
    )

    op.create_index(
        "idx_doc_type_instruction_versions_sha256",
        "document_type_instruction_versions",
        ["source_sha256"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_doc_type_instruction_versions_sha256",
        table_name="document_type_instruction_versions",
    )
    op.drop_index(
        "idx_doc_type_instruction_versions_doc_type_code",
        table_name="document_type_instruction_versions",
    )
    op.drop_table("document_type_instruction_versions")