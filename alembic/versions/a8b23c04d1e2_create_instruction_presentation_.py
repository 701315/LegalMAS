"""create_instruction_presentation_localization_table

Revision ID: a8b23c04d1e2
Revises: d75aaaf26063
Create Date: 2026-09-07 09:58:55.947256

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a8b23c04d1e2'
down_revision: Union[str, None] = 'd75aaaf26063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instruction_presentation_localizations",
        # ── PK (from Base) ───────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # ── Multi-tenancy ────────────────────────────────────────
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
            comment="NULL = platform-wide fallback localization entry.",
        ),
        # ── Identity & Locale ────────────────────────────────────
        sa.Column(
            "instruction_key",
            sa.String(200),
            nullable=False,
            comment="Stable dot-separated key representing the target UI entity.",
        ),
        sa.Column(
            "locale",
            sa.String(10),
            nullable=False,
            comment="BCP-47 target language code, e.g. 'en', 'ru'.",
        ),
        # ── Content ──────────────────────────────────────────────
        sa.Column(
            "label",
            sa.String(500),
            nullable=False,
            comment="Translated display name / header label.",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Optional tooltip description or helper text.",
        ),
        # ── Status ───────────────────────────────────────────────
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Inactive localizations are excluded from resolving.",
        ),
        # ── Provenance ───────────────────────────────────────────
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who created or uploaded this localization entry.",
        ),
        # ── Timestamps (from Base) ───────────────────────────────
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
            nullable=False,
        ),
    )

    # ── Indexes ──────────────────────────────────────────────────
    op.create_index(
        "ix_instruction_presentation_localizations_tenant_id",
        "instruction_presentation_localizations",
        ["tenant_id"],
    )
    op.create_index(
        "idx_instruction_localization_lookup",
        "instruction_presentation_localizations",
        ["instruction_key", "locale"],
    )
    op.create_index(
        "uix_instruction_localization_unique_active",
        "instruction_presentation_localizations",
        ["tenant_id", "instruction_key", "locale"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uix_instruction_localization_unique_active",
        table_name="instruction_presentation_localizations",
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_index(
        "idx_instruction_localization_lookup",
        table_name="instruction_presentation_localizations",
    )
    op.drop_index(
        "ix_instruction_presentation_localizations_tenant_id",
        table_name="instruction_presentation_localizations",
    )
    op.drop_table("instruction_presentation_localizations")