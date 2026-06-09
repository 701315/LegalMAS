"""add_segment_classification_status_and_dse_unique_index

Revision ID: b1c2d3e4f5a6
Revises: 0a8530c61f74
Create Date: 2026-06-09 21:16:52.650023

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '0a8530c61f74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = '0a8530c61f74'



def upgrade() -> None:
    # ── 1. Новая колонка ─────────────────────────────────────────────────────
    op.add_column(
        "document_segments",
        sa.Column(
            "segment_classification_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment=(
                "Pipeline-статус segment-level классификации: "
                "pending | classified | unknown | skipped | failed."
            ),
        ),
    )

    # ── 2. Backfill ──────────────────────────────────────────────────────────
    # Правило:
    #   - есть segment_doc_type                    → classified
    #   - segment_confidence_zone = 'unknown'       → unknown
    #   - есть segment_classification_level         → classified
    #     (был обработан, тип определён на каком-то уровне)
    #   - иначе                                     → pending
    op.execute("""
        UPDATE document_segments
        SET segment_classification_status = CASE
            WHEN segment_doc_type IS NOT NULL AND segment_doc_type != ''
                THEN 'classified'
            WHEN segment_confidence_zone = 'unknown'
                THEN 'unknown'
            WHEN segment_classification_level IS NOT NULL
                AND segment_classification_level != ''
                THEN 'classified'
            ELSE 'pending'
        END
    """)

    # ── 3. Индекс для readiness-запросов ─────────────────────────────────────
    op.create_index(
        "idx_segments_version_classification_status",
        "document_segments",
        ["document_version_id", "segment_classification_status"],
    )

    # ── 4. Partial unique index для document_stage_executions ────────────────
    # Сначала чистим дубликаты активных execution-записей.
    # Оставляем только самую раннюю запись для каждой комбинации
    # (run_id, document_version_id, task_name) среди активных статусов.
    # Это безопасно: дубликаты появились из-за бага UNKNOWN-сегментов,
    # который мы сейчас и исправляем.
    op.execute("""
        DELETE FROM document_stage_executions
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY run_id, document_version_id, task_name
                        ORDER BY created_at ASC
                    ) AS rn
                FROM document_stage_executions
                WHERE status IN ('planned', 'dispatched', 'started')
            ) ranked
            WHERE rn > 1
        )
    """)

    op.create_index(
        "uq_dse_active_stage_per_version_task",
        "document_stage_executions",
        ["run_id", "document_version_id", "task_name"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('planned', 'dispatched', 'started')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_dse_active_stage_per_version_task",
        table_name="document_stage_executions",
    )
    op.drop_index(
        "idx_segments_version_classification_status",
        table_name="document_segments",
    )
    op.drop_column("document_segments", "segment_classification_status")