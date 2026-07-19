"""add instruction overrides and run snapshots

Revision ID: f856963c49d5
Revises: 2798a8a88dfb
Create Date: 2026-07-19 09:12:17.145746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f856963c49d5'
down_revision: Union[str, None] = '2798a8a88dfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Расширяем document_type_instruction_versions: publish/audit поля.
    op.add_column(
        "document_type_instruction_versions",
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this instruction version is published for runtime usage.",
        ),
    )

    op.add_column(
        "document_type_instruction_versions",
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this version was published.",
        ),
    )

    op.add_column(
        "document_type_instruction_versions",
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who created this instruction version.",
        ),
    )

    op.add_column(
        "document_type_instruction_versions",
        sa.Column(
            "change_summary",
            sa.String(length=1000),
            nullable=True,
            comment="Human-readable summary of changes in this version.",
        ),
    )

    op.create_foreign_key(
        "fk_doc_type_instruction_versions_created_by_users",
        "document_type_instruction_versions",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2. Расширяем runs: frozen snapshot manifest + effective payload.
    op.add_column(
        "runs",
        sa.Column(
            "instruction_snapshot_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Frozen manifest of instruction references for this Run: "
                "{doc_type: {version_id, content_hash, override_id}}"
            ),
        ),
    )

    op.add_column(
        "runs",
        sa.Column(
            "instruction_snapshot_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Frozen effective compiled instruction payload used at runtime: "
                "{doc_type: compiled_payload}"
            ),
        ),
    )

    # 3. Новая таблица instruction_overrides (JSON Patch поверх base version).
    op.create_table(
        "instruction_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "instruction_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("base_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "patch_ops",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("change_summary", sa.String(length=1000), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["instruction_version_id"],
            ["document_type_instruction_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "deal_id",
            "instruction_version_id",
            name="uq_instruction_overrides_deal_version",
        ),
    )

    op.create_index(
        "ix_instruction_overrides_deal_id",
        "instruction_overrides",
        ["deal_id"],
        unique=False,
    )

    op.create_index(
        "ix_instruction_overrides_instruction_version_id",
        "instruction_overrides",
        ["instruction_version_id"],
        unique=False,
    )

    op.create_index(
        "idx_instruction_overrides_deal_stale",
        "instruction_overrides",
        ["deal_id", "is_stale"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_instruction_overrides_deal_stale",
        table_name="instruction_overrides",
    )
    op.drop_index(
        "ix_instruction_overrides_instruction_version_id",
        table_name="instruction_overrides",
    )
    op.drop_index(
        "ix_instruction_overrides_deal_id",
        table_name="instruction_overrides",
    )
    op.drop_table("instruction_overrides")

    op.drop_column("runs", "instruction_snapshot_payload")
    op.drop_column("runs", "instruction_snapshot_manifest")

    op.drop_constraint(
        "fk_doc_type_instruction_versions_created_by_users",
        "document_type_instruction_versions",
        type_="foreignkey",
    )
    op.drop_column("document_type_instruction_versions", "change_summary")
    op.drop_column("document_type_instruction_versions", "created_by")
    op.drop_column("document_type_instruction_versions", "published_at")
    op.drop_column("document_type_instruction_versions", "is_published")


    