"""add tenant scope to playbooks

Revision ID: d58a5baaaa7a
Revises: 21e1b267f0e9
Create Date: 2026-07-24 08:05:44.374465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd58a5baaaa7a'
down_revision: Union[str, None] = '21e1b267f0e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── playbooks ────────────────────────────────────────────────
    op.add_column(
        "playbooks",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "NULL = platform-owned, visible to all tenants. "
                "Non-null = tenant-owned, visible only inside this tenant."
            ),
        ),
    )
    op.add_column(
        "playbooks",
        sa.Column(
            "owner_scope",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'platform'"),
            comment="Ownership scope: platform | tenant",
        ),
    )

    op.create_foreign_key(
        "fk_playbooks_tenant_id",
        source_table="playbooks",
        referent_table="tenants",
        local_cols=["tenant_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_playbooks_tenant_id",
        "playbooks",
        ["tenant_id"],
    )

    op.create_check_constraint(
        "ck_playbooks_owner_scope_tenant",
        "playbooks",
        (
            "((owner_scope = 'platform' AND tenant_id IS NULL) "
            "OR (owner_scope = 'tenant' AND tenant_id IS NOT NULL))"
        ),
    )

    # ── playbook_versions ────────────────────────────────────────
    op.add_column(
        "playbook_versions",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "NULL = platform-owned version. "
                "Non-null = tenant-owned version. "
                "Must match tenant scope of parent Playbook."
            ),
        ),
    )
    op.add_column(
        "playbook_versions",
        sa.Column(
            "owner_scope",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'platform'"),
            comment="Ownership scope: platform | tenant",
        ),
    )

    op.create_foreign_key(
        "fk_playbook_versions_tenant_id",
        source_table="playbook_versions",
        referent_table="tenants",
        local_cols=["tenant_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_playbook_versions_tenant_id",
        "playbook_versions",
        ["tenant_id"],
    )

    op.create_check_constraint(
        "ck_playbook_versions_owner_scope_tenant",
        "playbook_versions",
        (
            "((owner_scope = 'platform' AND tenant_id IS NULL) "
            "OR (owner_scope = 'tenant' AND tenant_id IS NOT NULL))"
        ),
    )


def downgrade() -> None:
    # ── playbook_versions ────────────────────────────────────────
    op.drop_constraint(
        "ck_playbook_versions_owner_scope_tenant",
        "playbook_versions",
        type_="check",
    )
    op.drop_index("ix_playbook_versions_tenant_id", table_name="playbook_versions")
    op.drop_constraint(
        "fk_playbook_versions_tenant_id",
        "playbook_versions",
        type_="foreignkey",
    )
    op.drop_column("playbook_versions", "owner_scope")
    op.drop_column("playbook_versions", "tenant_id")

    # ── playbooks ────────────────────────────────────────────────
    op.drop_constraint(
        "ck_playbooks_owner_scope_tenant",
        "playbooks",
        type_="check",
    )
    op.drop_index("ix_playbooks_tenant_id", table_name="playbooks")
    op.drop_constraint(
        "fk_playbooks_tenant_id",
        "playbooks",
        type_="foreignkey",
    )
    op.drop_column("playbooks", "owner_scope")
    op.drop_column("playbooks", "tenant_id")