# src/db/repositories/run_summary_repo.py

"""
Repository для RunSummary.

Ответственности:
- чтение summary по run_id;
- создание записи (status='pending') с deterministic fallback;
- атомарный claim для генерации (защита от двойной генерации
  при нескольких API-воркерах);
- поиск terminal-runs без summary для dispatcher;
- восстановление зависших 'generating' записей.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.run import Run
from db.models.run_summary import RunSummary

# Terminal-статусы run, для которых имеет смысл строить резюме.
TERMINAL_RUN_STATUSES = ("completed", "completed_with_errors")


class RunSummaryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_run_id(self, run_id: uuid.UUID) -> Optional[RunSummary]:
        """Вернуть summary для run или None."""
        stmt = select(RunSummary).where(RunSummary.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        fallback: dict,
    ) -> RunSummary:
        """Создать запись summary со status='pending' и fallback."""
        summary = RunSummary(
            run_id=run_id,
            tenant_id=tenant_id,
            status="pending",
            fallback=fallback,
        )
        self.session.add(summary)
        await self.session.flush()
        return summary

    async def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        **kwargs,
    ) -> None:
        """Обновить статус и произвольные поля summary."""
        values = {"status": status, "updated_at": datetime.utcnow(), **kwargs}
        stmt = update(RunSummary).where(RunSummary.run_id == run_id).values(**values)
        await self.session.execute(stmt)

    async def claim_for_generation(self, run_id: uuid.UUID) -> bool:
        """
        Атомарно занять запись для генерации.

        UPDATE ... WHERE status IN ('pending','failed') — только один
        воркер из N получит rowcount=1 и пойдёт генерировать.
        Остальные получат 0 и пропустят ход.
        """
        stmt = (
            update(RunSummary)
            .where(RunSummary.run_id == run_id)
            .where(RunSummary.status.in_(["pending", "failed"]))
            .values(status="generating", updated_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return (result.rowcount or 0) == 1

    async def find_runs_needing_summary(
        self,
        limit: int = 5,
    ) -> list[uuid.UUID]:
        """
        Найти terminal-runs, для которых требуется генерация резюме.

        Кандидаты:
        1. Запись RunSummary ещё не создана (id is None).
        2. Запись существует в статусе 'pending' или 'failed',
           время повтора наступило (next_retry_at <= now или NULL)
           и лимит попыток не превышен (retry_count < 5).
        """
        now = datetime.utcnow()
        stmt = (
            select(Run.id)
            .outerjoin(RunSummary, RunSummary.run_id == Run.id)
            .where(Run.status.in_(list(TERMINAL_RUN_STATUSES)))
            .where(
                (RunSummary.id.is_(None))
                | (
                    (RunSummary.status.in_(["pending", "failed"]))
                    & (
                        (RunSummary.next_retry_at.is_(None))
                        | (RunSummary.next_retry_at <= now)
                    )
                    & (RunSummary.retry_count < 5)
                )
            )
            .order_by(Run.completed_at.desc().nulls_last())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result]

    async def recover_stale_generating(
        self,
        minutes: int = 10,
    ) -> int:
        """
        Вернуть в 'pending' записи, зависшие в 'generating' дольше N минут
        (например, после рестарта API-процесса).
        """
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        stmt = (
            update(RunSummary)
            .where(RunSummary.status == "generating")
            .where(RunSummary.updated_at < threshold)
            .values(status="pending", updated_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0


        