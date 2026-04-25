"""split check_results uniqueness by segment scope

Revision ID: 39923a1c6024
Revises: 7bdd613081b3
Create Date: 2026-04-24 10:39:38.302085

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39923a1c6024'
down_revision: Union[str, None] = '7bdd613081b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Для непрофессионального программиста:

    Раньше у нас был один уникальный индекс:
        uq_results_run_doc_check(run_id, document_id, check_id)

    Это означало:
    - для каждого run + документа + проверки хранится ровно одна строка;
    - если мы запускаем эту же проверку по нескольким сегментам одного файла,
      новые результаты перезаписывают старые.

    Теперь мы делим уникальность на два случая:

    1) single-document (segment_id IS NULL)
       - как и раньше, одна строка на (run, документ, проверка).

    2) multi-document (segment_id IS NOT NULL)
       - отдельная строка на (run, документ, сегмент, проверка).
    """

    # Удаляем старый уникальный индекс, который не учитывал segment_id.
    op.drop_index(
        "uq_results_run_doc_check",
        table_name="check_results",
        if_exists=True,
    )

    # Новый уникальный индекс для single-document:
    # одна строка на (run_id, document_id, check_id), но только когда segment_id NULL.
    op.create_index(
        "uq_results_run_doc_check_no_segment",
        "check_results",
        ["run_id", "document_id", "check_id"],
        unique=True,
        postgresql_where=sa.text("segment_id IS NULL"),
        if_not_exists=True,
    )

    # Новый уникальный индекс для multi-document:
    # одна строка на (run_id, document_id, segment_id, check_id),
    # но только когда segment_id NOT NULL.
    op.create_index(
        "uq_results_run_doc_segment_check",
        "check_results",
        ["run_id", "document_id", "segment_id", "check_id"],
        unique=True,
        postgresql_where=sa.text("segment_id IS NOT NULL"),
        if_not_exists=True,
    )


def downgrade() -> None:
    """
    Откат миграции:

    - удаляем новые частичные индексы;
    - возвращаем старый индекс uq_results_run_doc_check(run_id, document_id, check_id).
    """

    op.drop_index(
        "uq_results_run_doc_segment_check",
        table_name="check_results",
        if_exists=True,
    )

    op.drop_index(
        "uq_results_run_doc_check_no_segment",
        table_name="check_results",
        if_exists=True,
    )

    op.create_index(
        "uq_results_run_doc_check",
        "check_results",
        ["run_id", "document_id", "check_id"],
        unique=True,
        if_not_exists=True,
    )

    