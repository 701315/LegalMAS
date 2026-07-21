"""add tenant scope to instruction versions and overrides

Revision ID: 63ae307cde4e
Revises: e8de58ea67ef
Create Date: 2026-07-21 09:53:59.250313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '63ae307cde4e'
down_revision: Union[str, None] = 'e8de58ea67ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOC_TABLE = "document_type_instruction_versions"
OVERRIDE_TABLE = "instruction_overrides"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. document_type_instruction_versions
    # ------------------------------------------------------------------
    op.add_column(
        DOC_TABLE,
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "NULL = platform-owned instruction visible to all tenants. "
                "Non-null = tenant-owned instruction visible only inside this tenant."
            ),
        ),
    )

    op.add_column(
        DOC_TABLE,
        sa.Column(
            "owner_scope",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'platform'"),
            comment="Ownership scope: platform | tenant",
        ),
    )

    op.add_column(
        DOC_TABLE,
        sa.Column(
            "derived_from_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "If this tenant-owned instruction was copied/derived from another "
                "instruction version, stores the source version id."
            ),
        ),
    )

    op.create_foreign_key(
        "fk_document_type_instruction_versions_tenant_id",
        DOC_TABLE,
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_foreign_key(
        "fk_document_type_instruction_versions_derived_from_version_id",
        DOC_TABLE,
        DOC_TABLE,
        ["derived_from_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_document_type_instruction_versions_tenant_id",
        DOC_TABLE,
        ["tenant_id"],
        unique=False,
    )

    op.execute(
        f"""
        UPDATE {DOC_TABLE}
        SET owner_scope = 'platform'
        WHERE owner_scope IS NULL
        """
    )

    op.create_check_constraint(
        "ck_doc_type_instruction_versions_owner_scope_tenant",
        DOC_TABLE,
        "((owner_scope = 'platform' AND tenant_id IS NULL) "
        "OR (owner_scope = 'tenant' AND tenant_id IS NOT NULL))",
    )

    # Старый unique больше не подходит для multi-tenant identical copies.
    op.drop_constraint(
        "uq_doc_type_instruction_versions_doc_type_code_sha256",
        DOC_TABLE,
        type_="unique",
    )

    # Старый partial unique published index тоже слишком грубый:
    # он не различает platform и tenant scopes.
    op.execute(
        "DROP INDEX IF EXISTS uix_doc_type_instruction_versions_one_published"
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_doc_type_instruction_versions_platform_source_sha256
        ON {DOC_TABLE} (doc_type_code, source_sha256)
        WHERE owner_scope = 'platform'
        """
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_doc_type_instruction_versions_tenant_source_sha256
        ON {DOC_TABLE} (doc_type_code, source_sha256, tenant_id)
        WHERE owner_scope = 'tenant'
        """
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_doc_type_instr_ver_one_published_platform
        ON {DOC_TABLE} (doc_type_code)
        WHERE version_status = 'published' AND owner_scope = 'platform'
        """
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_doc_type_instr_ver_one_published_tenant
        ON {DOC_TABLE} (doc_type_code, tenant_id)
        WHERE version_status = 'published' AND owner_scope = 'tenant'
        """
    )

    # ------------------------------------------------------------------
    # 2. instruction_overrides
    # ------------------------------------------------------------------
    op.add_column(
        OVERRIDE_TABLE,
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "Tenant that owns this override. "
                "Used for authorization and tenant isolation."
            ),
        ),
    )

    op.add_column(
        OVERRIDE_TABLE,
        sa.Column(
            "override_scope",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'deal'"),
            comment="Override scope: tenant | deal",
        ),
    )

    # Для existing rows нужен initial default = 'active',
    # потом переключим default на 'draft' для новых записей.
    op.add_column(
        OVERRIDE_TABLE,
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'active'"),
            comment="Lifecycle status: draft | active | archived",
        ),
    )

    op.create_foreign_key(
        "fk_instruction_overrides_tenant_id",
        OVERRIDE_TABLE,
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_instruction_overrides_tenant_id",
        OVERRIDE_TABLE,
        ["tenant_id"],
        unique=False,
    )

    # Backfill tenant_id из deals.tenant_id
    op.execute(
        f"""
        UPDATE {OVERRIDE_TABLE} io
        SET tenant_id = d.tenant_id
        FROM deals d
        WHERE io.deal_id = d.id
          AND io.tenant_id IS NULL
        """
    )

    # Жёсткая проверка: после backfill NULL остаться не должен.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM {OVERRIDE_TABLE}
                WHERE tenant_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Backfill failed: instruction_overrides.tenant_id contains NULL values';
            END IF;
        END $$;
        """
    )

    op.alter_column(
        OVERRIDE_TABLE,
        "tenant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.alter_column(
        OVERRIDE_TABLE,
        "deal_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # Переключаем default для новых записей: draft.
    op.alter_column(
        OVERRIDE_TABLE,
        "status",
        existing_type=sa.String(length=20),
        server_default=sa.text("'draft'"),
    )

    # Старый unique constraint больше не подходит:
    # - не поддерживает tenant scope
    # - не поддерживает archived history
    op.drop_constraint(
        "uq_instruction_overrides_deal_version",
        OVERRIDE_TABLE,
        type_="unique",
    )

    op.create_check_constraint(
        "ck_instruction_overrides_scope_deal_id",
        OVERRIDE_TABLE,
        "((override_scope = 'tenant' AND deal_id IS NULL) "
        "OR (override_scope = 'deal' AND deal_id IS NOT NULL))",
    )

    op.create_check_constraint(
        "ck_instruction_overrides_status",
        OVERRIDE_TABLE,
        "status IN ('draft', 'active', 'archived')",
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_instruction_overrides_deal_version_live
        ON {OVERRIDE_TABLE} (deal_id, instruction_version_id)
        WHERE override_scope = 'deal' AND status <> 'archived'
        """
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_instruction_overrides_tenant_version_live
        ON {OVERRIDE_TABLE} (tenant_id, instruction_version_id)
        WHERE override_scope = 'tenant' AND status <> 'archived'
        """
    )

    op.create_index(
        "idx_instruction_overrides_scope_status",
        OVERRIDE_TABLE,
        ["tenant_id", "override_scope", "status"],
        unique=False,
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1. instruction_overrides
    #
    # ВНИМАНИЕ: downgrade здесь lossy.
    # Старый schema не умеет хранить:
    # - tenant-scope overrides
    # - archived history без конфликтов по unique(deal_id, instruction_version_id)
    # Поэтому:
    # - tenant overrides удаляются
    # - deal overrides дедуплицируются до одной записи на pair(deal, version)
    # ------------------------------------------------------------------

    # Удаляем tenant-scope rows — старый schema их не умеет хранить.
    op.execute(
        f"""
        DELETE FROM {OVERRIDE_TABLE}
        WHERE override_scope = 'tenant'
        """
    )

    # Дедупликация deal-scope rows для возврата старого unique constraint.
    op.execute(
        f"""
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY deal_id, instruction_version_id
                    ORDER BY
                        CASE status
                            WHEN 'active' THEN 0
                            WHEN 'draft' THEN 1
                            ELSE 2
                        END,
                        updated_at DESC NULLS LAST,
                        created_at DESC NULLS LAST,
                        id DESC
                ) AS rn
            FROM {OVERRIDE_TABLE}
            WHERE override_scope = 'deal'
        )
        DELETE FROM {OVERRIDE_TABLE} io
        USING ranked r
        WHERE io.id = r.id
          AND r.rn > 1
        """
    )

    op.execute("DROP INDEX IF EXISTS uix_instruction_overrides_deal_version_live")
    op.execute("DROP INDEX IF EXISTS uix_instruction_overrides_tenant_version_live")

    op.drop_index(
        "idx_instruction_overrides_scope_status",
        table_name=OVERRIDE_TABLE,
    )

    op.drop_constraint(
        "ck_instruction_overrides_status",
        OVERRIDE_TABLE,
        type_="check",
    )

    op.drop_constraint(
        "ck_instruction_overrides_scope_deal_id",
        OVERRIDE_TABLE,
        type_="check",
    )

    op.drop_constraint(
        "fk_instruction_overrides_tenant_id",
        OVERRIDE_TABLE,
        type_="foreignkey",
    )

    op.drop_index(
        "ix_instruction_overrides_tenant_id",
        table_name=OVERRIDE_TABLE,
    )

    op.alter_column(
        OVERRIDE_TABLE,
        "deal_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.drop_column(OVERRIDE_TABLE, "status")
    op.drop_column(OVERRIDE_TABLE, "override_scope")
    op.drop_column(OVERRIDE_TABLE, "tenant_id")

    op.create_unique_constraint(
        "uq_instruction_overrides_deal_version",
        OVERRIDE_TABLE,
        ["deal_id", "instruction_version_id"],
    )

    # ------------------------------------------------------------------
    # 2. document_type_instruction_versions
    #
    # ВНИМАНИЕ: downgrade здесь lossy.
    # Старый schema не умеет хранить tenant-owned instruction versions.
    # Поэтому tenant-owned rows удаляются.
    # ------------------------------------------------------------------
    op.execute(
        f"""
        DELETE FROM {DOC_TABLE}
        WHERE owner_scope = 'tenant'
        """
    )

    op.execute(
        "DROP INDEX IF EXISTS uix_doc_type_instr_ver_one_published_tenant"
    )
    op.execute(
        "DROP INDEX IF EXISTS uix_doc_type_instr_ver_one_published_platform"
    )
    op.execute(
        "DROP INDEX IF EXISTS uix_doc_type_instruction_versions_tenant_source_sha256"
    )
    op.execute(
        "DROP INDEX IF EXISTS uix_doc_type_instruction_versions_platform_source_sha256"
    )

    op.drop_constraint(
        "ck_doc_type_instruction_versions_owner_scope_tenant",
        DOC_TABLE,
        type_="check",
    )

    op.drop_constraint(
        "fk_document_type_instruction_versions_derived_from_version_id",
        DOC_TABLE,
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_document_type_instruction_versions_tenant_id",
        DOC_TABLE,
        type_="foreignkey",
    )

    op.drop_index(
        "ix_document_type_instruction_versions_tenant_id",
        table_name=DOC_TABLE,
    )

    op.drop_column(DOC_TABLE, "derived_from_version_id")
    op.drop_column(DOC_TABLE, "owner_scope")
    op.drop_column(DOC_TABLE, "tenant_id")

    op.create_unique_constraint(
        "uq_doc_type_instruction_versions_doc_type_code_sha256",
        DOC_TABLE,
        ["doc_type_code", "source_sha256"],
    )

    op.execute(
        f"""
        CREATE UNIQUE INDEX uix_doc_type_instruction_versions_one_published
        ON {DOC_TABLE} (doc_type_code)
        WHERE version_status = 'published'
        """
    )


    