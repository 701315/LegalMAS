"""dd global_instruction_versions table

Revision ID: 84f4430a94d3
Revises: 84abe1f67319
Create Date: 2026-07-22 16:01:01.711875

"""
from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '84f4430a94d3'
down_revision: Union[str, None] = '84abe1f67319'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "global_instruction_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("instruction_code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(300), nullable=True),
        sa.Column("group", sa.String(100), nullable=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_scope",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'platform'"),
        ),
        sa.Column(
            "source_format",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'yaml'"),
        ),
        sa.Column("source_yaml", sa.Text, nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_path", sa.String(1000), nullable=True),
        sa.Column("git_commit", sa.String(40), nullable=True),
        sa.Column("semver", sa.String(20), nullable=True),
        sa.Column("compiled_payload", postgresql.JSONB, nullable=True),
        sa.Column(
            "version_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("immutable_content_hash", sa.String(64), nullable=True),
        sa.Column("validation_report", postgresql.JSONB, nullable=True),
        sa.Column(
            "parent_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("global_instruction_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("change_summary", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "((owner_scope = 'platform' AND tenant_id IS NULL) "
            "OR (owner_scope = 'tenant' AND tenant_id IS NOT NULL))",
            name="ck_global_instruction_versions_owner_scope_tenant",
        ),
    )

    # Basic indexes
    op.create_index(
        "idx_global_instruction_versions_instruction_code",
        "global_instruction_versions",
        ["instruction_code"],
    )
    op.create_index(
        "idx_global_instruction_versions_tenant_id",
        "global_instruction_versions",
        ["tenant_id"],
    )
    op.create_index(
        "idx_global_instruction_versions_sha256",
        "global_instruction_versions",
        ["source_sha256"],
    )
    op.create_index(
        "idx_global_instruction_versions_status",
        "global_instruction_versions",
        ["instruction_code", "version_status"],
    )
    op.create_index(
        "idx_global_instruction_versions_group",
        "global_instruction_versions",
        ["group"],
    )

    # Partial unique indexes — требуют postgresql_where
    op.create_index(
        "uix_global_instruction_versions_platform_source_sha256",
        "global_instruction_versions",
        ["instruction_code", "source_sha256"],
        unique=True,
        postgresql_where=sa.text("owner_scope = 'platform'"),
    )
    op.create_index(
        "uix_global_instruction_versions_tenant_source_sha256",
        "global_instruction_versions",
        ["instruction_code", "source_sha256", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("owner_scope = 'tenant'"),
    )
    op.create_index(
        "uix_global_instruction_versions_one_published_platform",
        "global_instruction_versions",
        ["instruction_code"],
        unique=True,
        postgresql_where=sa.text(
            "version_status = 'published' AND owner_scope = 'platform'"
        ),
    )
    op.create_index(
        "uix_global_instruction_versions_one_published_tenant",
        "global_instruction_versions",
        ["instruction_code", "tenant_id"],
        unique=True,
        postgresql_where=sa.text(
            "version_status = 'published' AND owner_scope = 'tenant'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uix_global_instruction_versions_one_published_tenant",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "uix_global_instruction_versions_one_published_platform",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "uix_global_instruction_versions_tenant_source_sha256",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "uix_global_instruction_versions_platform_source_sha256",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "idx_global_instruction_versions_group",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "idx_global_instruction_versions_status",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "idx_global_instruction_versions_sha256",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "idx_global_instruction_versions_tenant_id",
        table_name="global_instruction_versions",
    )
    op.drop_index(
        "idx_global_instruction_versions_instruction_code",
        table_name="global_instruction_versions",
    )
    op.drop_table("global_instruction_versions")
