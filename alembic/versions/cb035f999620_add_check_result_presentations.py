"""add check result presentations

Revision ID: cb035f999620
Revises: 9317c6d16767
Create Date: 2026-09-06 08:14:17.049458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cb035f999620'
down_revision: Union[str, None] = '9317c6d16767'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "check_result_presentations",
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
            comment="Canonical CheckResult to which this presentation belongs.",
        ),
        sa.Column(
            "locale",
            sa.String(length=35),
            nullable=False,
            comment="BCP 47 presentation locale, for example en, ru, de, fr.",
        ),
        sa.Column(
            "content_version",
            sa.String(length=64),
            nullable=False,
            comment=(
                "Immutable source-content version identifier for this presentation. "
                "A new source version must not overwrite an approved older version."
            ),
        ),
        sa.Column(
            "source_content_hash",
            sa.String(length=64),
            nullable=False,
            comment=(
                "SHA-256 hash of canonical source fields used to produce "
                "this locale-specific presentation."
            ),
        ),
        sa.Column(
            "source_locale",
            sa.String(length=35),
            nullable=True,
            comment="Language of canonical source content when known.",
        ),
        sa.Column(
            "localized_check_name",
            sa.String(length=500),
            nullable=True,
            comment=(
                "Locale-specific check name when it is not supplied "
                "by a stable playbook translation dictionary."
            ),
        ),
        sa.Column(
            "display_text",
            sa.Text(),
            nullable=True,
            comment="Locale-specific primary factual result text.",
        ),
        sa.Column(
            "review_message",
            sa.Text(),
            nullable=True,
            comment="Locale-specific review explanation for the result drawer.",
        ),
        sa.Column(
            "dd_request_text",
            sa.Text(),
            nullable=True,
            comment="Locale-specific DD request text when applicable.",
        ),
        sa.Column(
            "translation_status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
            comment=(
                "Presentation lifecycle: pending, processing, ready, failed, "
                "reviewed, approved, stale."
            ),
        ),
        sa.Column(
            "translation_provider",
            sa.String(length=100),
            nullable=True,
            comment="Translation provider identifier, if generated externally.",
        ),
        sa.Column(
            "translation_model",
            sa.String(length=200),
            nullable=True,
            comment="Translation model identifier or version.",
        ),
        sa.Column(
            "translation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Translation provenance, diagnostics, usage, source fields, "
                "and batch metadata."
            ),
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Last presentation-generation failure message, if any.",
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who reviewed this locale-specific presentation.",
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when this presentation was reviewed.",
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="User who approved this presentation for controlled output.",
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when this presentation was approved.",
        ),
        sa.ForeignKeyConstraint(
            ["check_result_id"],
            ["check_results.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "check_result_id",
            "locale",
            "content_version",
            name="uq_check_result_presentations_identity",
        ),
    )

    op.create_index(
        "idx_check_result_presentations_result_locale",
        "check_result_presentations",
        ["check_result_id", "locale"],
    )

    op.create_index(
        "idx_check_result_presentations_locale_status",
        "check_result_presentations",
        ["locale", "translation_status"],
    )

    op.create_index(
        "idx_check_result_presentations_source_hash",
        "check_result_presentations",
        ["source_content_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_check_result_presentations_source_hash",
        table_name="check_result_presentations",
    )

    op.drop_index(
        "idx_check_result_presentations_locale_status",
        table_name="check_result_presentations",
    )

    op.drop_index(
        "idx_check_result_presentations_result_locale",
        table_name="check_result_presentations",
    )

    op.drop_table("check_result_presentations")
