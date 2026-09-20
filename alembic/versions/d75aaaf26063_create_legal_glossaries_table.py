"""create_legal_glossaries_table

Revision ID: d75aaaf26063
Revises: e665b9447550
Create Date: 2026-09-07 08:38:29.201216

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd75aaaf26063'
down_revision: Union[str, None] = 'e665b9447550'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_glossaries",
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
            comment="NULL = platform-wide glossary entry.",
        ),
        # ── Locale pair ──────────────────────────────────────────
        sa.Column(
            "source_locale",
            sa.String(10),
            nullable=False,
            comment="BCP-47 source language, e.g. 'ru'.",
        ),
        sa.Column(
            "target_locale",
            sa.String(10),
            nullable=False,
            comment="BCP-47 target language, e.g. 'en'.",
        ),
        # ── Term content ─────────────────────────────────────────
        sa.Column(
            "source_term",
            sa.String(500),
            nullable=False,
            comment="Original term in source_locale.",
        ),
        sa.Column(
            "target_term",
            sa.String(500),
            nullable=False,
            comment="Canonical translation in target_locale.",
        ),
        sa.Column(
            "term_category",
            sa.String(100),
            nullable=True,
            comment="Domain category, e.g. 'contract_law'.",
        ),
        sa.Column(
            "context_note",
            sa.Text(),
            nullable=True,
            comment="Disambiguation note for the translator / LLM.",
        ),
        # ── Status ───────────────────────────────────────────────
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Inactive entries excluded from resolution.",
        ),
        # ── Provenance ───────────────────────────────────────────
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who created or imported this entry.",
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
        "ix_legal_glossaries_tenant_id",
        "legal_glossaries",
        ["tenant_id"],
    )
    op.create_index(
        "idx_legal_glossary_locale_pair",
        "legal_glossaries",
        ["source_locale", "target_locale"],
    )
    op.create_index(
        "uix_legal_glossary_active_term",
        "legal_glossaries",
        ["tenant_id", "source_locale", "target_locale", "source_term"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uix_legal_glossary_active_term",
        table_name="legal_glossaries",
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_index(
        "idx_legal_glossary_locale_pair",
        table_name="legal_glossaries",
    )
    op.drop_index(
        "ix_legal_glossaries_tenant_id",
        table_name="legal_glossaries",
    )
    op.drop_table("legal_glossaries")