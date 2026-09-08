"""add_review_and_human_override_fields_to_presentations

Revision ID: 2b76dda7061a
Revises: a8b23c04d1e2
Create Date: 2026-09-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2b76dda7061a"
down_revision: Union[str, None] = "a8b23c04d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ 1. Комментарий ревьюера (approve / reject / edit)
    op.add_column(
        "check_result_presentations",
        sa.Column(
            "review_comment",
            sa.Text(),
            nullable=True,
            comment="Reviewer comment for approval, rejection or edit.",
        ),
    )

    # ✅ 2. Ручной оверрайд перевода (JSONB — все локализованные поля)
    op.add_column(
        "check_result_presentations",
        sa.Column(
            "human_override_text",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Human-edited override of localized presentation fields.",
        ),
    )

    # ✅ 3. Снимок оригинального LLM-перевода до первой правки
    op.add_column(
        "check_result_presentations",
        sa.Column(
            "original_translation_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Snapshot of original LLM translation before first human edit.",
        ),
    )


def downgrade() -> None:
    op.drop_column("check_result_presentations", "original_translation_snapshot")
    op.drop_column("check_result_presentations", "human_override_text")
    op.drop_column("check_result_presentations", "review_comment")
