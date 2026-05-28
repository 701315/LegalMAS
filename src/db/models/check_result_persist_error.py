# src/db/models/check_result_persist_error.py

"""
Ledger для ошибок сохранения CheckResult в БД (persist layer).

Одна запись = одна неуспешная попытка записи/обновления CheckResult.
Не участвует в финализации Run, служит для диагностики и возможного replay.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CheckResultPersistError(Base):
    __tablename__ = "check_result_persist_errors"

    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Run, в рамках которого произошла ошибка persist (если известен)",
    )

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Document, для которого пытались сохранить результат (если известен)",
    )

    check_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Check identifier from playbook, e.g. coc_001 (если известен)",
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment=(
            "Полный словарь аргументов upsert_single_check_result "
            "(только простые типы: строки/числа/JSON, без ORM-объектов)."
        ),
    )

    error_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Высокоуровневый тип ошибки: permanent_db_error / transient_db_error / db_string_truncation и т.п.",
    )

    sqlstate: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="SQLSTATE драйвера БД, если доступен",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Текст исключения (err или err.orig)",
    )

    retryable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Можно ли пытаться реплеить этот persist автоматически",
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество попыток повторной записи из fallback-воркера",
    )

    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Когда последний раз пытались реплеить ошибку persist",
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Когда ошибка была помечена решённой/закрытой",
    )

    resolution_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        comment="Статус разборки ошибки: open / resolved / ignored",
    )

    resolution_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Произвольный комментарий по результату ручного разбора ошибки",
    )

    __table_args__ = (
        Index("idx_cr_persist_errors_run", "run_id"),
        Index("idx_cr_persist_errors_doc", "document_id"),
        Index("idx_cr_persist_errors_status_retry", "resolution_status", "retryable"),
    )
