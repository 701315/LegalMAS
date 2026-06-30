"""add_tenants_users_tables_b1

Revision ID: 3240cca82e12
Revises: 84986185f7eb
Create Date: 2026-06-30 10:14:51.702214

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3240cca82e12"
down_revision: Union[str, None] = "84986185f7eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Seed constants ──────────────────────────────────────────────────────────
# Эти UUID фиксированы и совпадают с DEV_TENANT_ID в config.py.
DEV_TENANT_ID = "11111111-1111-1111-1111-111111111111"
DEV_SUPERADMIN_ID = "22222222-2222-2222-2222-222222222222"

# ВАЖНО:
# Замените значение ниже на реальный bcrypt hash для пароля "superadmin",
# сгенерированный командой:
# python3 -c "import bcrypt; print(bcrypt.hashpw(b'superadmin', bcrypt.gensalt()).decode())"
DEV_SUPERADMIN_PASSWORD_HASH = "$2b$12$GHE7WbrQQhrpMNTg4qh0B./ArArVvmVFZJ5qMEkOmbqv.5msxctie"


def upgrade() -> None:
    # ── 1. Таблица tenants ──────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(500),
            nullable=False,
        ),
        sa.Column(
            "slug",
            sa.String(100),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "notes",
            sa.Text,
            nullable=True,
        ),
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
    op.create_index(
        "ix_tenants_slug",
        "tenants",
        ["slug"],
        unique=True,
    )

    # ── 2. Таблица users ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "email",
            sa.String(320),
            nullable=False,
        ),
        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=False,
        ),
        sa.Column(
            "full_name",
            sa.String(500),
            nullable=True,
        ),
        sa.Column(
            "system_role",
            sa.String(50),
            nullable=False,
            server_default="member",
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
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
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # ── 3. Seed: dev tenant ─────────────────────────────────────────────────
    # Вставляем ДО создания FK на deals, чтобы существующие deals
    # с этим tenant_id могли ссылаться на реальную запись.
    op.execute(
        sa.text(
            f"""
            INSERT INTO tenants (id, name, slug, is_active, created_at, updated_at)
            VALUES (
                '{DEV_TENANT_ID}'::uuid,
                'Dev Tenant',
                'dev',
                true,
                NOW(),
                NOW()
            )
            ON CONFLICT DO NOTHING
            """
        )
    )

    # ── 4. Repair: deals с zero UUID → DEV_TENANT_ID ───────────────────────
    op.execute(
        sa.text(
            f"""
            UPDATE deals
            SET tenant_id = '{DEV_TENANT_ID}'::uuid
            WHERE tenant_id = '00000000-0000-0000-0000-000000000000'
            """
        )
    )

    # ── 5. FK: deals.tenant_id → tenants.id ─────────────────────────────────
    op.create_foreign_key(
        "fk_deals_tenant_id",
        "deals",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # ── 6. Seed: superadmin user ────────────────────────────────────────────
    op.execute(
        sa.text(
            f"""
            INSERT INTO users (
                id, tenant_id, email, password_hash,
                full_name, system_role, is_active,
                created_at, updated_at
            )
            VALUES (
                '{DEV_SUPERADMIN_ID}'::uuid,
                '{DEV_TENANT_ID}'::uuid,
                'superadmin@steloom.com',
                '{DEV_SUPERADMIN_PASSWORD_HASH}',
                'System Administrator',
                'superadmin',
                true,
                NOW(),
                NOW()
            )
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    # Удаляем в обратном порядке

    # 1. Удалить seed superadmin
    op.execute(
        sa.text(
            f"DELETE FROM users WHERE id = '{DEV_SUPERADMIN_ID}'::uuid"
        )
    )

    # 2. Убрать FK с deals
    op.drop_constraint("fk_deals_tenant_id", "deals", type_="foreignkey")

    # 3. Откатить repair: вернуть zero UUID
    op.execute(
        sa.text(
            f"""
            UPDATE deals
            SET tenant_id = '00000000-0000-0000-0000-000000000000'
            WHERE tenant_id = '{DEV_TENANT_ID}'::uuid
            """
        )
    )

    # 4. Удалить seed tenant
    op.execute(
        sa.text(
            f"DELETE FROM tenants WHERE id = '{DEV_TENANT_ID}'::uuid"
        )
    )

    # 5. Удалить таблицы
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")