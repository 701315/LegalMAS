# src/db/models/run_check_plan_item.py

"""
RunCheckPlanItem model.

Это execution ledger (журнал выполнения) для checks.
Источник истины для прогресса и финализации Run, а не CheckResult.

Инварианты:
- Создаётся ДО публикации execution-задачи; при outbox запись планирования и dispatch-message
  фиксируются в одной транзакции.
- Статус меняется атомарно: planned -> dispatched -> started -> terminal.
- Уникальность гарантируется partial unique indexes (отдельно для segment_id IS NULL и IS NOT NULL).
- CheckResult ссылается на эту запись как на domain output, но не наоборот.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class RunCheckPlanItem(Base):
    __tablename__ = "run_check_plan_items"

    # id, created_at, updated_at наследуются от Base

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    segment_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="ID логического сегмента (NULL для single-document файлов)",
    )

    check_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Идентификатор проверки из playbook/instruction",
    )

    check_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Человекочитаемое название (может быть неизвестно на раннем этапе планирования)",
    )

    check_origin: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Источник: global_playbook, document_type, cross_doc",
    )

    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("playbook_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Версия плейбука на момент планирования",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="planned",
        comment="planned, dispatched, started, succeeded, failed, skipped, timeout, cancelled",
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    dispatch_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Ссылка на dispatch-сущность; для outbox хранит outbox_message_id",
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # Partial unique indexes (правильный PostgreSQL-паттерн для nullable unique)
        Index(
            "idx_run_check_plan_item_unique_no_segment",
            "run_id",
            "document_id",
            "check_id",
            unique=True,
            postgresql_where=(segment_id.is_(None)),
        ),
        Index(
            "idx_run_check_plan_item_unique_with_segment",
            "run_id",
            "document_id",
            "check_id",
            "segment_id",
            unique=True,
            postgresql_where=(segment_id.isnot(None)),
        ),
        # Индексы для быстрой агрегации при финализации Run
        Index("idx_plan_item_run_status", "run_id", "status"),
        Index("idx_plan_item_document_check", "document_id", "check_id"),
    )


    