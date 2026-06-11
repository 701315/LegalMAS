"""add display semantics to check_results

Revision ID: a1b2c3d4e5f6
Revises: c2d3e4f5a6b7
Create Date: 2025-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── A. Check definition denormalization ────────────────────────────────────
    op.add_column(
        "check_results",
        sa.Column(
            "ui_mode",
            sa.String(length=50),
            nullable=True,
            comment=(
                "Denormalized ui_mode from CheckDefinition: "
                "clause_presence, risk_detection, field_extraction, compliance"
            ),
        ),
    )

    # ── B. Canonical display semantics ────────────────────────────────────────
    op.add_column(
        "check_results",
        sa.Column(
            "display_text",
            sa.Text(),
            nullable=True,
            comment=(
                "Canonical human-facing factual text for DD Grid cell. "
                "Single source of truth for primary display."
            ),
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "machine_reason_code",
            sa.String(length=100),
            nullable=True,
            comment=(
                "Internal machine reason code (e.g. rules_confident_positive). "
                "For diagnostics only, never shown as primary text."
            ),
        ),
    )

    # ── C. Canonical review semantics ─────────────────────────────────────────
    op.add_column(
        "check_results",
        sa.Column(
            "review_status",
            sa.String(length=50),
            nullable=True,
            comment=(
                "Canonical review workflow status: "
                "no_issue_detected, issue_detected, clause_missing, "
                "unclear, manual_review_required, not_applicable, technical_failure"
            ),
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "review_message",
            sa.Text(),
            nullable=True,
            comment=(
                "Advisory explanation for lawyer. "
                "Shown in drawer/details, never as primary cell text."
            ),
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "needs_manual_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Explicit boolean flag for review workflow filtering.",
        ),
    )

    # ── D. Indexes ────────────────────────────────────────────────────────────
    op.create_index(
        "idx_results_review_status",
        "check_results",
        ["run_id", "review_status"],
        unique=False,
    )

    op.create_index(
        "idx_results_manual_review",
        "check_results",
        ["run_id", "needs_manual_review"],
        unique=False,
        postgresql_where=sa.text("needs_manual_review = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_results_manual_review", table_name="check_results")
    op.drop_index("idx_results_review_status", table_name="check_results")

    op.drop_column("check_results", "needs_manual_review")
    op.drop_column("check_results", "review_message")
    op.drop_column("check_results", "review_status")
    op.drop_column("check_results", "machine_reason_code")
    op.drop_column("check_results", "display_text")
    op.drop_column("check_results", "ui_mode")


    