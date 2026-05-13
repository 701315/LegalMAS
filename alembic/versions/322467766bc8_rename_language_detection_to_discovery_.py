"""rename_language_detection_to_discovery_in_documents

Revision ID: 322467766bc8
Revises: 5a65d6dfd5d5
Create Date: 2026-05-13 13:00:30.012485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '322467766bc8'
down_revision: Union[str, None] = '5a65d6dfd5d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Переименовываем колонку documents.language_detection_status
    # → documents.language_discovery_status.
    #
    # Причина: терминологическое расщепление в bounded context language discovery.
    # На уровне deal уже используется language_discovery_status (добавлено в 6960a5a69d79).
    # На уровне document было добавлено language_detection_status — исторически,
    # до фиксации единого терминологического словаря.
    # Теперь оба уровня используют единый термин "discovery".
    #
    # Воздействие:
    #   - Таблица: documents, колонка language_detection_status → language_discovery_status
    #   - Индекс: нет (на этой колонке индекса не было)
    #   - ORM-модель: Document.language_detection_status → Document.language_discovery_status
    #   - Репозиторий: убрать fallback-слой _language_discovery_status_column()
    #   - Воркеры: update_language_detection() → update_language_discovery()
    op.alter_column(
        "documents",
        "language_detection_status",
        new_column_name="language_discovery_status",
    )


def downgrade() -> None:
    # Откат: возвращаем исходное имя колонки.
    op.alter_column(
        "documents",
        "language_discovery_status",
        new_column_name="language_detection_status",
    )