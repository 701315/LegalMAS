"""add_documents_classification_outcome

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-10 09:49:56.927417

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'


def upgrade() -> None:
    # ── 1. Новая колонка ─────────────────────────────────────────────────────
    op.add_column(
        "documents",
        sa.Column(
            "classification_outcome",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment=(
                "Business outcome of document-level classification: "
                "pending | typed | unknown | failed."
            ),
        ),
    )

    # ── 2. Backfill ──────────────────────────────────────────────────────────
    # Правила:
    #   - doc_type заполнен и не пустой       → typed
    #   - status IN (classified, enriched)
    #     но doc_type пустой                  → unknown
    #   - status = failed                     → оставляем pending
    #     (failed мог быть на любой стадии,
    #      не обязательно на classification)
    #   - иначе                               → pending
    op.execute("""
        UPDATE documents
        SET classification_outcome = CASE
            WHEN doc_type IS NOT NULL AND doc_type != ''
                THEN 'typed'
            WHEN status IN ('classified', 'enriched')
                AND (doc_type IS NULL OR doc_type = '')
                THEN 'unknown'
            ELSE 'pending'
        END
    """)

    # ── 3. Индекс ────────────────────────────────────────────────────────────
    op.create_index(
        "idx_documents_classification_outcome",
        "documents",
        ["classification_outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_documents_classification_outcome",
        table_name="documents",
    )
    op.drop_column("documents", "classification_outcome")

    