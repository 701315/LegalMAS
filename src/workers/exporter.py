# src/workers/exporter.py

"""
Exporter Worker — (экспорт результатов по сделке).

Что делает:
- Формирует полный пакет экспортных файлов по Run/сделке:
  - dd_grid_{run_id}.xlsx      — DD Grid с несколькими листами.
  - summary_{run_id}.xlsx      — Summary по сделке.
  - report_{run_id}.docx       — Word‑отчёт.
  - aggregated_{run_id}.json   — JSON‑дамп агрегации.

Архитектура:
- Синхронная Celery‑таска export_results (def) + async‑ядро export_core(...) под db_uow().
- Вся логика агрегации и генерации файлов вынесена в services.export.core.export_core.
- БД‑операции выполняются через db_uow / AsyncSession.
- Файлы сохраняются в хранилище через ArtifactStore внутри export_core.
- Переход sync → async выполняется один раз через run_async,
  без ручного управления event loop в коде таски.
"""

import time
import uuid

from ops.metrics import get_metrics
from core.logging import get_logger
from db.uow import db_uow
from db.repositories.run_repo import RunRepository
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.export.core import export_core
from core.constants import RunStatus

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
      - открывает UnitOfWork через db_uow();
      - вызывает services.export.core.export_core(...);
      - пишет метрику длительности экспорта;
      - при ошибке помечает Run как failed;
      - возвращает результат с refs на сгенерированные файлы.
    """
    logger.info("Запуск экспорта", run_id=run_id, deal_id=deal_id)

    started_at = time.time()
    metrics = get_metrics()

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            run_uuid = uuid.UUID(run_id)

            try:
                result = await export_core(
                    run_id=run_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    db=uow.session,
                )

                duration = time.time() - started_at
                metrics.export_duration.labels(
                    export_type="full_deal_export"
                ).observe(duration)

                logger.info(
                    "Экспорт завершён",
                    run_id=run_id,
                    deal_id=deal_id,
                    duration_sec=round(duration, 2),
                    files_generated=len(result.get("refs", {})),
                )

                return result

            except Exception as e:
                logger.error(
                    "Экспорт завершился с ошибкой",
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "error": str(e),
                    },
                )
                # Помечаем Run как failed и сохраняем детали ошибки
                await run_repo.update_status(
                    run_uuid,
                    RunStatus.FAILED.value,
                    error_details={
                        "stage": "export",
                        "type": "failed",
                        "reason": "export_error",
                        "message": str(e),
                    },
                )

                # Пробрасываем ошибку дальше, чтобы Celery видел failure
                raise

    # Запускаем async‑ядро через общий мост run_async
    return run_async(_run())
