"""add segment provenance fields to check_results

Revision ID: f9070b8a76b8
Revises: 919077c95317
Create Date: 2026-04-15 12:46:30.737513

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9070b8a76b8'
down_revision: Union[str, None] = '919077c95317'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем nullable-поля сегмента в check_results
    op.add_column(
        "check_results",
        sa.Column(
            "segment_id",
            sa.String(length=200),
            nullable=True,
            comment="Logical segment identifier within a multi-document physical file",
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "segment_type",
            sa.String(length=100),
            nullable=True,
            comment="Logical segment type: contract, appendix, annex, amendment, invoice, act, etc.",
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "segment_title",
            sa.String(length=500),
            nullable=True,
            comment="Human-readable title of the logical segment",
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "segment_order",
            sa.Integer(),
            nullable=True,
            comment="Order of the logical segment within the physical file",
        ),
    )

    op.add_column(
        "check_results",
        sa.Column(
            "is_primary_segment",
            sa.Boolean(),
            nullable=True,
            comment="True if the finding belongs to the primary logical segment of the file",
        ),
    )

    # 2. Индексы для segment-aware запросов
    op.create_index(
        "idx_results_run_segment",
        "check_results",
        ["run_id", "segment_id"],
        unique=False,
    )

    op.create_index(
        "idx_results_run_primary_segment",
        "check_results",
        ["run_id", "is_primary_segment"],
        unique=False,
    )


def downgrade() -> None:
    # Откатываем в обратном порядке: сначала индексы, потом колонки
    op.drop_index("idx_results_run_primary_segment", table_name="check_results")
    op.drop_index("idx_results_run_segment", table_name="check_results")

    op.drop_column("check_results", "is_primary_segment")
    op.drop_column("check_results", "segment_order")
    op.drop_column("check_results", "segment_title")
    op.drop_column("check_results", "segment_type")
    op.drop_column("check_results", "segment_id")

    