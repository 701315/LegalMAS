"""add_run_check_plan_items_and_snapshot_version

Revision ID: bc56177ec084
Revises: f856963c49d5
Create Date: 2026-07-20 07:27:39.279769

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bc56177ec084'
down_revision: Union[str, None] = 'f856963c49d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем snapshot_schema_version в runs
    op.add_column(
        'runs',
        sa.Column('snapshot_schema_version', sa.Integer(), nullable=True, 
                  comment="NULL for legacy runs, 1 for strict snapshot-backed runs")
    )

    # 2. Создаём таблицу run_check_plan_items
    op.create_table(
        'run_check_plan_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('segment_id', sa.String(length=200), nullable=True),
        sa.Column('check_id', sa.String(length=100), nullable=False),
        sa.Column('check_name', sa.String(length=500), nullable=True),
        sa.Column('check_origin', sa.String(length=50), nullable=True),
        sa.Column('playbook_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='planned'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['playbook_version_id'], ['playbook_versions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Индексы
    op.create_index('ix_run_check_plan_items_run_id', 'run_check_plan_items', ['run_id'])
    op.create_index('ix_run_check_plan_items_deal_id', 'run_check_plan_items', ['deal_id'])
    op.create_index('ix_run_check_plan_items_document_id', 'run_check_plan_items', ['document_id'])
    
    # Partial unique indexes
    op.create_index(
        'idx_run_check_plan_item_unique_no_segment',
        'run_check_plan_items',
        ['run_id', 'document_id', 'check_id'],
        unique=True,
        postgresql_where=sa.text('segment_id IS NULL')
    )
    op.create_index(
        'idx_run_check_plan_item_unique_with_segment',
        'run_check_plan_items',
        ['run_id', 'document_id', 'check_id', 'segment_id'],
        unique=True,
        postgresql_where=sa.text('segment_id IS NOT NULL')
    )
    op.create_index('idx_plan_item_run_status', 'run_check_plan_items', ['run_id', 'status'])
    op.create_index('idx_plan_item_document_check', 'run_check_plan_items', ['document_id', 'check_id'])

    # 3. Добавляем plan_item_id в check_results с FK
    op.add_column(
        'check_results',
        sa.Column('plan_item_id', postgresql.UUID(as_uuid=True), nullable=True, 
                  comment="Execution plan item that produced this result")
    )
    op.create_foreign_key(
        'fk_check_results_plan_item',
        'check_results', 'run_check_plan_items',
        ['plan_item_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_check_results_plan_item_id', 'check_results', ['plan_item_id'])


def downgrade() -> None:
    # Обратный порядок
    op.drop_index('ix_check_results_plan_item_id', table_name='check_results')
    op.drop_constraint('fk_check_results_plan_item', 'check_results', type_='foreignkey')
    op.drop_column('check_results', 'plan_item_id')

    op.drop_index('idx_plan_item_document_check', table_name='run_check_plan_items')
    op.drop_index('idx_plan_item_run_status', table_name='run_check_plan_items')
    op.drop_index('idx_run_check_plan_item_unique_with_segment', table_name='run_check_plan_items')
    op.drop_index('idx_run_check_plan_item_unique_no_segment', table_name='run_check_plan_items')
    op.drop_index('ix_run_check_plan_items_document_id', table_name='run_check_plan_items')
    op.drop_index('ix_run_check_plan_items_deal_id', table_name='run_check_plan_items')
    op.drop_index('ix_run_check_plan_items_run_id', table_name='run_check_plan_items')
    
    op.drop_table('run_check_plan_items')

    op.drop_column('runs', 'snapshot_schema_version')