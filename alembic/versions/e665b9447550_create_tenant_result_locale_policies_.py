"""create_tenant_result_locale_policies_table

Revision ID: e665b9447550
Revises: 818879bb7d5e
Create Date: 2026-09-07 07:32:16.243315

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e665b9447550'
down_revision: Union[str, None] = '818879bb7d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tenant_result_locale_policies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'tenant_id',
            sa.UUID(),
            nullable=False,
            comment='Tenant owning this policy. One policy per tenant constraint.',
        ),
        sa.Column(
            'allowed_locales',
            postgresql.ARRAY(sa.String(length=10)),
            server_default='{}',
            nullable=False,
            comment='List of allowed BCP 47 output locales. Empty means all registry locales are allowed.',
        ),
        sa.Column(
            'is_translation_enabled',
            sa.Boolean(),
            server_default='true',
            nullable=False,
            comment='Enables or disables LLM translation pipeline for the entire tenant.',
        ),
        sa.Column(
            'restrict_to_allowed',
            sa.Boolean(),
            server_default='true',
            nullable=False,
            comment='If True, strictly enforce 422/403 for locales not in allowed_locales.',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id'],
            ['tenants.id'],
            name='fk_tenant_result_locale_policies_tenant_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name='pk_tenant_result_locale_policies'),
        sa.UniqueConstraint(
            'tenant_id', name='uq_tenant_result_locale_policies_tenant'
        ),
    )
    op.create_index(
        'ix_tenant_result_locale_policies_tenant_id',
        'tenant_result_locale_policies',
        ['tenant_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_tenant_result_locale_policies_tenant_id',
        table_name='tenant_result_locale_policies',
    )
    op.drop_table('tenant_result_locale_policies')

    