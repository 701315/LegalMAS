# src/workers/exporter.py

"""
Exporter Worker — экспорт результатов по сделке.

Содержит две независимые Celery-таски:

────────────────────────────────────────────────────
1. export_results(run_id, deal_id, tenant_id)
────────────────────────────────────────────────────
Что делает:
- Вызывается оркестратором автоматически после завершения Run.
- Формирует полный пакет экспортных файлов по Run/сделке:
    - dd_grid_{run_id}.xlsx     — DD Grid с несколькими листами.
    - summary_{run_id}.xlsx     — Summary по сделке.
    - report_{run_id}.docx      — Word-отчёт.
    - aggregated_{run_id}.json  — JSON-дамп агрегации.
- При ошибке помечает Run как failed.

Архитектура:
- Синхронная Celery-таска (def) + async-ядро под db_uow().
- Вся логика генерации файлов вынесена в services.export.core.export_core.
- Файлы сохраняются через ArtifactStore внутри export_core.
- Переход sync → async выполняется один раз через run_async.

────────────────────────────────────────────────────
2. export_by_id(export_id)
────────────────────────────────────────────────────
Что делает:
- Вызывается из POST /api/v1/runs/{run_id}/export сразу после создания
  записи Export в БД.
- Обрабатывает одну конкретную запись Export по её export_id.
- Выбирает нужный файл из пакета результатов по полю export_type
  (grid_xlsx / deal_summary_xlsx / report_docx / aggregated_json).
- Обновляет запись Export через ExportRepository на каждом шаге lifecycle.

Lifecycle записи Export:
    pending → processing → completed
                        ↘ failed

Архитектура:
- Синхронная Celery-таска (def) + async-ядро под db_uow().
- БД-операции выполняются через db_uow / AsyncSession + ExportRepository.
- Вызывает тот же export_core, что и export_results, но читает параметры
  (run_id, deal_id, export_type) из записи Export, а не из аргументов таски.
- Переход sync → async выполняется один раз через run_async.
"""

import time
import uuid

from ops.metrics import get_metrics
from core.logging import get_logger
from db.uow import db_uow
from db.repositories.run_repo import RunRepository
from db.repositories.export_repo import ExportRepository
from core.constants import RunStatus
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.export.core import export_core


logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Существующая таска — НЕ ТРОГАТЬ
# Вызывается оркестратором после завершения Run
# ──────────────────────────────────────────────────────────────────────────────

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
    logger.info(
        "Export results task received",
        extra={"run_id": run_id, "deal_id": deal_id, "tenant_id": tenant_id},
    )

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
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "duration_sec": round(duration, 2),
                        "files_generated": len(result.get("refs", {})),
                    },
                )
                return result

            except Exception as e:
                logger.error(
                    "Экспорт завершился с ошибкой",
                    extra={"run_id": run_id, "deal_id": deal_id, "error": str(e)},
                )
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
                raise

    return run_async(_run())


# ──────────────────────────────────────────────────────────────────────────────
# НОВАЯ таска — для UI-инициированного экспорта
# Вызывается из POST /api/v1/runs/{run_id}/export
# ──────────────────────────────────────────────────────────────────────────────

def _pick_file_ref(export_type: str, refs: dict | None) -> str | None:
    if not refs:
        return None

    priority = {
        "grid_xlsx": ["dd_grid", "grid", "main"],
        "deal_summary_xlsx": ["summary", "deal_summary", "main"],
        "report_docx": ["report_docx", "report", "main"],
        "aggregated_json": ["aggregated_json", "aggregated", "json", "main"],
    }

    for key in priority.get(export_type, []):
        value = refs.get(key)
        if isinstance(value, str) and value:
            return value

    for val in refs.values():
        if isinstance(val, str) and val:
            return val

    return None


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.export_by_id",
    track_job=False,
    queue="default",
)
def export_by_id(self, export_id: str) -> dict:
    """
    Синхронная Celery-таска UI-инициированного экспорта.

    Принимает export_id единственным аргументом — загружает запись Export
    из БД, читает из неё run_id / deal_id / export_type и запускает
    services.export.core.export_core.

    Внутри:
      - загружает запись Export по export_id из ExportRepository;
      - переводит статус pending → processing и делает commit;
      - вызывает services.export.core.export_core(...) с параметрами из записи;
      - выбирает основной file_ref из словаря refs по export_type;
      - переводит статус processing → completed, сохраняет file_ref и file_refs;
      - при ошибке переводит статус processing → failed, сохраняет error_message;
      - пишет метрику длительности экспорта по export_type;
      - пробрасывает исключение дальше, чтобы Celery видел failure.

    Args:
        export_id (str): UUID записи Export в виде строки.

    Returns:
        dict: {
            "export_id": str,
            "status": "completed",
            "file_ref": str | None,   — путь/ключ основного файла
            "file_refs": dict,        — все сгенерированные файлы по ключам
        }

    Raises:
        ValueError: если запись Export с указанным export_id не найдена в БД.
        Exception:  любая ошибка export_core — статус Export → failed,
                    ошибка пробрасывается в Celery.
    """
    logger.info(
        "Export by id task received",
        extra={"export_id": export_id, "celery_task_id": self.request.id},
    )

    started_at = time.time()
    metrics = get_metrics()

    async def _run() -> dict:
        async with db_uow() as uow:
            export_repo = ExportRepository(uow.session)
            export_uuid = uuid.UUID(export_id)

            export = await export_repo.get_by_id(export_uuid)
            if not export:
                raise ValueError(f"Export not found: {export_id}")

            run_id = str(export.run_id)
            deal_id = str(export.deal_id)
            export_type = export.export_type

            logger.info(
                "Export job started",
                extra={
                    "export_id": export_id,
                    "run_id": run_id,
                    "deal_id": deal_id,
                    "export_type": export_type,
                },
            )

            # pending → processing
            await export_repo.update(export_uuid, {"status": "processing"})
            await uow.session.commit()

            logger.info(
                "Export status changed",
                extra={
                    "export_id": export_id,
                    "from_status": "pending",
                    "to_status": "processing",
                },
            )

            try:
                result = await export_core(
                    run_id=run_id,
                    deal_id=deal_id,
                    tenant_id="default",
                    db=uow.session,
                )

                refs = result.get("refs", {}) if isinstance(result, dict) else {}
                logger.info(
                    "Export core returned refs",
                    extra={
                        "export_id": export_id,
                        "run_id": run_id,
                        "export_type": export_type,
                        "refs_keys": sorted(refs.keys()) if isinstance(refs, dict) else [],
                        "refs": refs,
                    },
                )

                file_ref = _pick_file_ref(export_type, refs)

                if not file_ref:
                    refs_keys = sorted(refs.keys()) if isinstance(refs, dict) else []
                    message = (
                        f"Export completed without primary artifact for export_type={export_type}. "
                        f"Available refs keys: {refs_keys}"
                    )

                    logger.error(
                        "Primary export artifact was not found",
                        extra={
                            "export_id": export_id,
                            "run_id": run_id,
                            "deal_id": deal_id,
                            "export_type": export_type,
                            "refs_keys": refs_keys,
                        },
                    )

                    await export_repo.update(
                        export_uuid,
                        {
                            "status": "failed",
                            "file_refs": refs or None,
                            "error_message": message[:2000],
                        },
                    )
                    await uow.session.commit()
                    raise RuntimeError(message)

                # processing → completed
                await export_repo.update(
                    export_uuid,
                    {
                        "status": "completed",
                        "file_ref": file_ref,
                        "file_refs": refs or None,
                        "error_message": None,
                    },
                )
                await uow.session.commit()

                duration = time.time() - started_at
                metrics.export_duration.labels(
                    export_type=export_type
                ).observe(duration)

                logger.info(
                    "Export completed",
                    extra={
                        "export_id": export_id,
                        "run_id": run_id,
                        "export_type": export_type,
                        "file_ref": file_ref,
                        "duration_sec": round(duration, 2),
                        "files_generated": len(refs),
                    },
                )

                return {
                    "export_id": export_id,
                    "status": "completed",
                    "file_ref": file_ref,
                    "file_refs": refs,
                }

            except Exception as e:
                logger.exception(
                    "Export failed",
                    extra={
                        "export_id": export_id,
                        "run_id": run_id,
                        "export_type": export_type,
                        "error": str(e),
                    },
                )
                # processing → failed
                await export_repo.update(
                    export_uuid,
                    {
                        "status": "failed",
                        "error_message": str(e)[:2000],
                    },
                )
                await uow.session.commit()
                raise

    return run_async(_run())


