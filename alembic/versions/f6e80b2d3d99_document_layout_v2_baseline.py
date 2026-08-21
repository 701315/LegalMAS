"""document_layout_v2_baseline

Revision ID: f6e80b2d3d99
Revises: e59483da6a25
Create Date: 2024-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f6e80b2d3d99"
down_revision = "e59483da6a25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. DocumentVersion: новые поля v2
    op.add_column(
        "document_versions",
        sa.Column("canonical_layout_ref", sa.String(1024), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "detected_languages",
            postgresql.ARRAY(sa.String(10)),
            nullable=True,
        ),
    )

    # 2. Run: policy для missing target language
    #    ВНИМАНИЕ: таблица называется "runs", НЕ "review_runs"!
    op.add_column(
        "runs",
        sa.Column(
            "missing_target_language_policy",
            sa.String(64),
            nullable=False,
            server_default="BLOCK_DOCUMENT_CONTINUE_RUN",
        ),
    )

    # 3. Новая таблица: run-scoped language resolution
    op.create_table(
        "document_run_language_resolution",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_language", sa.String(10), nullable=False),
        sa.Column(
            "available_languages",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("effective_language", sa.String(10), nullable=True),
        sa.Column("resolution_status", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("canonical_layout_ref", sa.String(1024), nullable=True),
        sa.Column("layout_primary_ref", sa.String(1024), nullable=True),
        sa.Column(
            "layout_primary_sanitized_ref", sa.String(1024), nullable=True
        ),
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
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "document_version_id",
            name="uq_doc_run_lang_resolution_run_version",
        ),
    )
    op.create_index(
        "idx_doc_run_lang_res_run",
        "document_run_language_resolution",
        ["run_id"],
    )
    op.create_index(
        "idx_doc_run_lang_res_doc",
        "document_run_language_resolution",
        ["document_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_doc_run_lang_res_doc",
        table_name="document_run_language_resolution",
    )
    op.drop_index(
        "idx_doc_run_lang_res_run",
        table_name="document_run_language_resolution",
    )
    op.drop_table("document_run_language_resolution")
    op.drop_column("runs", "missing_target_language_policy")
    op.drop_column("document_versions", "detected_languages")
    op.drop_column("document_versions", "canonical_layout_ref")
