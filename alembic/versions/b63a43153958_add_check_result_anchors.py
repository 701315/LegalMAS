"""add check result anchors

Revision ID: b63a43153958
Revises: 7ea844f630e0
Create Date: 2026-09-21 17:59:17.136305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b63a43153958'
down_revision: Union[str, None] = '7ea844f630e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "check_result_anchors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
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
        sa.Column(
            "check_result_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Canonical CheckResult to which this anchor belongs.",
        ),
        sa.Column(
            "clause_uid",
            sa.String(length=200),
            nullable=True,
            comment="Effective clause UID, e.g. 'main_contract:7.3.2'.",
        ),
        sa.Column(
            "clause_ref",
            sa.String(length=200),
            nullable=True,
            comment="Human-readable clause ref, e.g. 'п. 7.3.2'.",
        ),
        sa.Column(
            "quoted_text",
            sa.Text(),
            nullable=True,
            comment="Verbatim quote from source used as evidence.",
        ),
        sa.Column("span_start", sa.Integer(), nullable=True,
                  comment="Start char offset within canonical source text."),
        sa.Column("span_end", sa.Integer(), nullable=True,
                  comment="End char offset (exclusive)."),
        sa.Column(
            "source_content_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex of canonical source text at extraction time.",
        ),
        sa.Column("page", sa.Integer(), nullable=True, comment="1-based page number."),
        sa.Column(
            "layout_element_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="Layout element IDs covered by this anchor.",
        ),
        sa.Column(
            "bbox_union",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Union bounding box [x0, top, x1, bottom].",
        ),
        sa.Column(
            "segment_id",
            sa.String(length=200),
            nullable=True,
            comment="Logical segment identifier within multi-doc file.",
        ),
        sa.Column(
            "anchor_method",
            sa.String(length=50),
            nullable=False,
            comment="CheckAnchorMethod value.",
        ),
        sa.Column(
            "anchor_confidence",
            sa.Float(),
            nullable=False,
            comment="Confidence in [0.0, 1.0].",
        ),
        sa.Column(
            "anchor_validation_passed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if round-trip validation passed.",
        ),
        sa.Column(
            "anchor_diagnostics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Free-form diagnostics.",
        ),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True for the single primary anchor of the CheckResult.",
        ),
        sa.ForeignKeyConstraint(
            ["check_result_id"], ["check_results.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_cra_result", "check_result_anchors", ["check_result_id"])
    op.create_index(
        "uq_cra_one_primary",
        "check_result_anchors",
        ["check_result_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )
    op.create_index(
        "idx_cra_document_clause",
        "check_result_anchors",
        ["segment_id", "clause_uid"],
    )
    op.create_index(
        "idx_cra_document_span",
        "check_result_anchors",
        ["segment_id", "page", "span_start"],
    )

    # Denormalized primary anchor on CheckResult (populated by B4).
    op.add_column(
        "check_results",
        sa.Column("primary_anchor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "check_results",
        sa.Column("primary_anchor_method", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "check_results",
        sa.Column("primary_anchor_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "check_results",
        sa.Column(
            "anchor_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_foreign_key(
        "fk_check_results_primary_anchor_id",
        "check_results",
        "check_result_anchors",
        ["primary_anchor_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_check_results_primary_anchor_id", "check_results", type_="foreignkey",
    )
    op.drop_column("check_results", "anchor_stale")
    op.drop_column("check_results", "primary_anchor_confidence")
    op.drop_column("check_results", "primary_anchor_method")
    op.drop_column("check_results", "primary_anchor_id")

    op.drop_index("uq_cra_one_primary", table_name="check_result_anchors")
    op.drop_index("idx_cra_document_span", table_name="check_result_anchors")
    op.drop_index("idx_cra_document_clause", table_name="check_result_anchors")
    op.drop_index("idx_cra_result", table_name="check_result_anchors")
    op.drop_table("check_result_anchors")
