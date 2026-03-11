# src/workers/exporter.py


"""
Exporter Worker — Stage 9.

Производит полный пакет экспортных файлов по сделке:
  - dd_grid_{run_id}.xlsx      — DD Grid с 4 листами
  - summary_{run_id}.xlsx      — Summary с 5 листами
  - report_{run_id}.docx       — Word-отчёт с 7 разделами
  - aggregated_{run_id}.json   — JSON-дамп агрегации

Архитектура:
  - Синхронная Celery‑таска (def) + async‑ядро (как у всех остальных воркеров).
  - Вся логика агрегации и экспорта вынесена в src/services/export/core.py.
  - БД‑операции выполняются через db_uow / AsyncSession.
  - Файлы сохраняются через ArtifactStore.
"""

import asyncio
import time

from ops.metrics import get_metrics
from core.logging import get_logger
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.export.core import export_core

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.export_results",
    track_job=False,
    queue="default",
)
def export_results(
    self,
    run_id: str,
    deal_id: str,
    tenant_id: str,
) -> dict:
    """
    Синхронная Celery‑таска экспорта результатов сделки.

    Внутри:
      - создаёт event loop;
      - открывает UnitOfWork через db_uow();
      - вызывает services.export.core.export_core(...);
      - возвращает результат с refs на сгенерированные файлы.
    """
    logger.info("Запуск экспорта", run_id=run_id, deal_id=deal_id)

    started_at = time.time()
    metrics = get_metrics()

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)

        async def _run() -> dict:
            async with db_uow() as uow:
                result = await export_core(
                    run_id=run_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    db=uow.session,
                )

                duration = time.time() - started_at
                metrics.export_duration.labels(export_type="full_deal_export").observe(duration)

                logger.info(
                    "Экспорт завершён",
                    run_id=run_id,
                    deal_id=deal_id,
                    duration_sec=round(duration, 2),
                    files_generated=len(result.get("refs", {})),
                )

                return result

        return loop.run_until_complete(_run())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
