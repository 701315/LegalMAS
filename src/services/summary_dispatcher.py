# src/services/summary_dispatcher.py

"""
SummaryDispatcher — фоновый автозапуск генерации резюме.

Запускается в lifespan API-процесса как asyncio-задача и каждые
N секунд:
1. восстанавливает зависшие 'generating' записи (после рестартов);
2. ищет terminal-runs без summary;
3. спавнит генерацию в отдельной asyncio-задаче.

Не трогает код рана: только читает статусы runs и пишет run_summaries.

Защита от гонок при нескольких API-воркерах:
- in-flight set внутри процесса;
- атомарный claim_for_generation в БД (UPDATE ... WHERE status IN ...);
- UNIQUE(run_id) + обработка IntegrityError при создании записи.
"""

import asyncio
import uuid
from typing import Optional

from core.logging import get_logger
from db.session import transactional_session
from db.repositories.run_summary_repo import RunSummaryRepository
from services.run_summary_service import RunSummaryService

logger = get_logger(__name__)

_DISPATCH_INTERVAL_SEC = 10
_BATCH_SIZE = 2


class SummaryDispatcher:
    def __init__(
        self,
        interval_sec: float = _DISPATCH_INTERVAL_SEC,
        batch_size: int = _BATCH_SIZE,
    ) -> None:
        self.interval_sec = interval_sec
        self.batch_size = batch_size
        self._task: Optional[asyncio.Task] = None
        self._inflight: set[uuid.UUID] = set()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="summary_dispatcher")
        logger.info(
            "Summary dispatcher started",
            interval_sec=self.interval_sec,
            batch_size=self.batch_size,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Summary dispatcher stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — dispatcher never dies
                logger.warning("Summary dispatcher tick failed", error=str(exc))
            await asyncio.sleep(self.interval_sec)

    async def _tick(self) -> None:
        # ── Фаза 1: восстановление + поиск кандидатов (короткая транзакция)
        async with transactional_session() as session:
            repo = RunSummaryRepository(session)
            recovered = await repo.recover_stale_generating(minutes=10)
            run_ids = await repo.find_runs_needing_summary(limit=self.batch_size)

        if recovered:
            logger.info("Summary dispatcher recovered stale jobs", count=recovered)

        # ── Фаза 2: спавн генераций ───────────────────────────────────
        for run_id in run_ids:
            if run_id in self._inflight:
                continue
            self._inflight.add(run_id)
            asyncio.create_task(
                self._generate_safe(run_id), name=f"summary_gen_{run_id}"
            )

    async def _generate_safe(self, run_id: uuid.UUID) -> None:
        try:
            async with transactional_session() as session:
                service = RunSummaryService(session)
                await service.generate(run_id)
            logger.info("Summary dispatcher: generation finished", run_id=str(run_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Summary dispatcher: generation error",
                run_id=str(run_id),
                error=str(exc),
            )
        finally:
            self._inflight.discard(run_id)


_dispatcher: Optional[SummaryDispatcher] = None


def get_summary_dispatcher() -> SummaryDispatcher:
    """Singleton dispatcher для lifespan API."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SummaryDispatcher()
    return _dispatcher


    