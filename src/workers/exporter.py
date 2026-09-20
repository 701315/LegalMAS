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
What it does:
- Вызывается из POST /api/v1/runs/{run_id}/export сразу после создания
  записи Export в БД.
- Обрабатывает одну конкретную запись Export по её export_id.
- Выбирает нужный файл из пакета результатов по полю export_type
  (grid_xlsx / deal_summary_xlsx / report_docx / aggregated_json).
- Обновляет запись Export через ExportRepository на каждом шаге lifecycle.
- Пишет записи в audit_log на каждом переходе статуса.

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
from typing import Any

from core.constants import RunStatus
from core.logging import get_logger
from db.repositories.audit_repo import AuditRepository
from db.repositories.export_repo import ExportRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from ops.metrics import get_metrics
from services.export.core import export_core

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Таска автоматического экспорта после завершения Run
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
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    output_locale: str | None = None,
    presentation_locale: str = "en",
    **kwargs: Any,
) -> dict:
    eff_locale = (
        output_locale 
        or presentation_locale 
        or kwargs.get("output_locale") 
        or kwargs.get("presentation_locale", "en")
    )

    logger.info(
        "Export results task received",
        run_id=run_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        output_locale=output_locale,
        presentation_locale=presentation_locale,
        effective_locale=eff_locale,
    )

    started_at = time.time()
    metrics = get_metrics()

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            audit_repo = AuditRepository(uow.session)
            run_uuid = uuid.UUID(run_id)
            deal_uuid = uuid.UUID(deal_id)

            run_obj = await run_repo.get_by_id(run_uuid)
            if run_obj is None:
                raise ValueError(f"Run not found: {run_id}")

            task_tenant_uuid: uuid.UUID | None = None
            try:
                task_tenant_uuid = uuid.UUID(tenant_id)
            except (ValueError, AttributeError, TypeError):
                task_tenant_uuid = None

            if getattr(run_obj, "tenant_id", None) is None:
                if task_tenant_uuid is None:
                    raise ValueError(
                        f"Run {run_id} has no tenant_id and task tenant_id is invalid: {tenant_id}"
                    )
                tenant_uuid = task_tenant_uuid
                logger.warning(
                    "export_results: using task tenant_id because run.tenant_id is missing",
                    run_id=run_id,
                    deal_id=deal_id,
                    tenant_id=str(tenant_uuid),
                )
            else:
                tenant_uuid = run_obj.tenant_id
                if task_tenant_uuid is not None and task_tenant_uuid != tenant_uuid:
                    logger.warning(
                        "export_results: task tenant_id differs from run.tenant_id; using run.tenant_id",
                        run_id=run_id,
                        deal_id=deal_id,
                        task_tenant_id=str(task_tenant_uuid),
                        run_tenant_id=str(tenant_uuid),
                    )

            try:
                result = await export_core(
                    run_id=run_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    db=uow.session,
                    output_locale=eff_locale,
                    presentation_locale=eff_locale,
                )

                duration = time.time() - started_at
                metrics.export_duration.labels(export_type="full_deal_export").observe(duration)

                refs = result.get("refs", {})

                logger.info(
                    "Экспорт завершён",
                    run_id=run_id,
                    deal_id=deal_id,
                    duration_sec=round(duration, 2),
                    files_generated=len(refs),
                    locale=eff_locale,
                )

                await audit_repo.log(
                    tenant_id=tenant_uuid,
                    deal_id=deal_uuid,
                    action="EXPORT_COMPLETED",
                    actor="system",
                    actor_role="worker",
                    details={
                        "run_id": run_id,
                        "export_type": "full_deal_export",
                        "files_generated": len(refs),
                        "duration_sec": round(duration, 2),
                        "refs_keys": sorted(refs.keys()),
                        "locale": eff_locale,
                    },
                )
                await uow.session.commit()

                return result

            except Exception as e:
                logger.error(
                    "Экспорт завершился с ошибкой",
                    run_id=run_id,
                    deal_id=deal_id,
                    error=str(e),
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

                try:
                    await audit_repo.log(
                        tenant_id=tenant_uuid,
                        deal_id=deal_uuid,
                        action="EXPORT_FAILED",
                        actor="system",
                        actor_role="worker",
                        details={
                            "run_id": run_id,
                            "export_type": "full_deal_export",
                            "error": str(e)[:500],
                            "locale": eff_locale,
                        },
                    )
                    await uow.session.commit()
                except Exception:
                    logger.warning(
                        "Не удалось записать аудит для EXPORT_FAILED",
                        run_id=run_id,
                    )

                raise

    return run_async(_run())


# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательная функция выбора основного файла из словаря refs
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


# ──────────────────────────────────────────────────────────────────────────────
# Таска UI-инициированного экспорта по ID
# ──────────────────────────────────────────────────────────────────────────────


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.export_by_id",
    track_job=False,
    queue="default",
)
def export_by_id(
    self,
    export_id: str,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    output_locale: str | None = None,
    presentation_locale: str = "en",
    **kwargs: Any,
) -> dict:
    """
    Синхронная Celery-таска UI-инициированного экспорта.

    Принимает export_id и параметры локали.
    """
    eff_locale = (
        output_locale 
        or presentation_locale 
        or kwargs.get("output_locale") 
        or kwargs.get("presentation_locale", "en")
    )

    logger.info(
        "Export by id task received",
        export_id=export_id,
        celery_task_id=self.request.id,
        output_locale=output_locale,
        presentation_locale=presentation_locale,
        effective_locale=eff_locale,
    )

    started_at = time.time()
    metrics = get_metrics()

    async def _run() -> dict:
        async with db_uow() as uow:
            export_repo = ExportRepository(uow.session)
            audit_repo = AuditRepository(uow.session)
            export_uuid = uuid.UUID(export_id)

            export = await export_repo.get_by_id(export_uuid)
            if not export:
                raise ValueError(f"Export not found: {export_id}")

            run_id = str(export.run_id)
            deal_id = str(export.deal_id)
            export_type = export.export_type
            requested_by = export.requested_by or "unknown"
            requester_role = export.requester_role or "user"

            deal_uuid = uuid.UUID(deal_id)

            run_repo = RunRepository(uow.session)
            run_obj = await run_repo.get_by_id(export.run_id)
            if run_obj is None:
                raise ValueError(f"Run not found for export {export_id}: {export.run_id}")

            if getattr(run_obj, "tenant_id", None) is None:
                raise ValueError(
                    f"Run {run_obj.id} has no tenant_id while processing export {export_id}"
                )

            tenant_uuid = run_obj.tenant_id

            logger.info(
                "Export job started",
                export_id=export_id,
                run_id=run_id,
                deal_id=deal_id,
                export_type=export_type,
                locale=eff_locale,
            )

            # ── Переход: pending → processing ────────────────────────────────
            await export_repo.update(export_uuid, {"status": "processing"})

            await audit_repo.log(
                tenant_id=tenant_uuid,
                deal_id=deal_uuid,
                action="EXPORT_STARTED",
                actor=requested_by,
                actor_role=requester_role,
                details={
                    "export_id": export_id,
                    "run_id": run_id,
                    "export_type": export_type,
                    "locale": eff_locale,
                },
            )
            await uow.session.commit()

            logger.info(
                "Export status changed",
                export_id=export_id,
                from_status="pending",
                to_status="processing",
            )

            try:
                result = await export_core(
                    run_id=run_id,
                    deal_id=deal_id,
                    tenant_id=str(tenant_uuid),
                    db=uow.session,
                    output_locale=eff_locale,
                    presentation_locale=eff_locale,
                )

                refs = result.get("refs", {}) if isinstance(result, dict) else {}

                logger.info(
                    "Export core returned refs",
                    export_id=export_id,
                    run_id=run_id,
                    export_type=export_type,
                    refs_keys=sorted(refs.keys()) if isinstance(refs, dict) else [],
                    refs=refs,
                    locale=eff_locale,
                )

                file_ref = _pick_file_ref(export_type, refs)

                if not file_ref:
                    refs_keys = sorted(refs.keys()) if isinstance(refs, dict) else []
                    message = (
                        f"Export completed without primary artifact for "
                        f"export_type={export_type}. "
                        f"Available refs keys: {refs_keys}"
                    )

                    logger.error(
                        "Primary export artifact was not found",
                        export_id=export_id,
                        run_id=run_id,
                        deal_id=deal_id,
                        export_type=export_type,
                        refs_keys=refs_keys,
                    )

                    await export_repo.update(
                        export_uuid,
                        {
                            "status": "failed",
                            "file_refs": refs or None,
                            "error_message": message[:2000],
                        },
                    )

                    await audit_repo.log(
                        tenant_id=tenant_uuid,
                        deal_id=deal_uuid,
                        action="EXPORT_FAILED",
                        actor=requested_by,
                        actor_role=requester_role,
                        details={
                            "export_id": export_id,
                            "run_id": run_id,
                            "export_type": export_type,
                            "reason": "primary_artifact_missing",
                            "refs_keys": refs_keys,
                            "error": message[:500],
                            "locale": eff_locale,
                        },
                    )
                    await uow.session.commit()
                    raise RuntimeError(message)

                # ── Переход: processing → completed ──────────────────────────
                await export_repo.update(
                    export_uuid,
                    {
                        "status": "completed",
                        "file_ref": file_ref,
                        "file_refs": refs or None,
                        "error_message": None,
                    },
                )

                duration = time.time() - started_at
                metrics.export_duration.labels(export_type=export_type).observe(duration)

                await audit_repo.log(
                    tenant_id=tenant_uuid,
                    deal_id=deal_uuid,
                    action="EXPORT_COMPLETED",
                    actor=requested_by,
                    actor_role=requester_role,
                    details={
                        "export_id": export_id,
                        "run_id": run_id,
                        "export_type": export_type,
                        "file_ref": file_ref,
                        "files_generated": len(refs),
                        "duration_sec": round(duration, 2),
                        "locale": eff_locale,
                    },
                )
                await uow.session.commit()

                logger.info(
                    "Export completed",
                    export_id=export_id,
                    run_id=run_id,
                    export_type=export_type,
                    file_ref=file_ref,
                    duration_sec=round(duration, 2),
                    files_generated=len(refs),
                    locale=eff_locale,
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
                    export_id=export_id,
                    run_id=run_id,
                    export_type=export_type,
                    error=str(e),
                )

                await export_repo.update(
                    export_uuid,
                    {
                        "status": "failed",
                        "error_message": str(e)[:2000],
                    },
                )

                try:
                    await audit_repo.log(
                        tenant_id=tenant_uuid,
                        deal_id=deal_uuid,
                        action="EXPORT_FAILED",
                        actor=requested_by,
                        actor_role=requester_role,
                        details={
                            "export_id": export_id,
                            "run_id": run_id,
                            "export_type": export_type,
                            "reason": "exception",
                            "error": str(e)[:500],
                            "locale": eff_locale,
                        },
                    )
                    await uow.session.commit()
                except Exception:
                    logger.warning(
                        "Не удалось записать аудит для EXPORT_FAILED",
                        export_id=export_id,
                    )

                raise

    return run_async(_run())


    