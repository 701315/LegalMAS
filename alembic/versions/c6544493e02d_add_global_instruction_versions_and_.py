"""add global_instruction_versions and extend instruction_overrides

Revision ID: c6544493e02d
Revises: 84f4430a94d3
Create Date: 2026-07-22 16:33:46.051278

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c6544493e02d'
down_revision: Union[str, None] = '84f4430a94d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем колонку для global instruction version
    op.add_column(
        "instruction_overrides",
        sa.Column(
            "global_instruction_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("global_instruction_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    op.create_index(
        "idx_instruction_overrides_global_version_id",
        "instruction_overrides",
        ["global_instruction_version_id"],
    )

    # 2. Делаем instruction_version_id nullable,
    # чтобы можно было хранить либо doc-type, либо global ref
    op.alter_column(
        "instruction_overrides",
        "instruction_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # 3. XOR constraint: должен быть заполнен ровно один FK
    op.create_check_constraint(
        "ck_instruction_overrides_version_id_xor",
        "instruction_overrides",
        (
            "((instruction_version_id IS NOT NULL AND global_instruction_version_id IS NULL) "
            "OR (instruction_version_id IS NULL AND global_instruction_version_id IS NOT NULL))"
        ),
    )

    # 4. Partial unique indexes для global overrides
    op.create_index(
        "uix_instruction_overrides_deal_global_version_live",
        "instruction_overrides",
        ["deal_id", "global_instruction_version_id"],
        unique=True,
        postgresql_where=sa.text(
            "override_scope = 'deal' "
            "AND status <> 'archived' "
            "AND global_instruction_version_id IS NOT NULL"
        ),
    )

    op.create_index(
        "uix_instruction_overrides_tenant_global_version_live",
        "instruction_overrides",
        ["tenant_id", "global_instruction_version_id"],
        unique=True,
        postgresql_where=sa.text(
            "override_scope = 'tenant' "
            "AND status <> 'archived' "
            "AND global_instruction_version_id IS NOT NULL"
        ),
    )

def downgrade() -> None:
    op.drop_index(
        "uix_instruction_overrides_tenant_global_version_live",
        table_name="instruction_overrides",
    )

    op.drop_index(
        "uix_instruction_overrides_deal_global_version_live",
        table_name="instruction_overrides",
    )

    op.drop_constraint(
        "ck_instruction_overrides_version_id_xor",
        "instruction_overrides",
        type_="check",
    )

    op.alter_column(
        "instruction_overrides",
        "instruction_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.drop_index(
        "idx_instruction_overrides_global_version_id",
        table_name="instruction_overrides",
    )

    op.drop_column("instruction_overrides", "global_instruction_version_id")


    