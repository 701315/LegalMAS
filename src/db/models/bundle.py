# src/db/models/bundle.py

"""
Bundle model — пакет документов, импортированных одной операцией.

Что такое Bundle:
- Одна операция импорта/загрузки документов внутри сделки (deal).
- Объединяет группу файлов, пришедших из одного источника:
  - zip — импорт ZIP‑архива c документацией;
  - vdr_api — загрузка из внешней VDR/данной комнаты;
  - local — ручная загрузка с фронта.

Зачем нужен Bundle:
- Позволяет:
  - отслеживать статус конкретной операции импорта (pending → completed / failed);
  - понимать, сколько файлов было в пакете (file_count);
  - хранить агрегированные error_details по импорту (например, почему часть файлов
    не удалось обработать);
  - видеть, когда импорт завершился (completed_at).
- Для юриста/оператора в UI это может выглядеть как список «пакетов загрузки» по сделке
  с количеством файлов и итоговым статусом каждого импорта.
"""


import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import BundleSourceType
from ..base import Base


class Bundle(Base):
    __tablename__ = "bundles"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=BundleSourceType.ZIP.value,
        comment="zip, vdr_api, local",
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    file_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
