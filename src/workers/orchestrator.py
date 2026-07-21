# src/workers/orchestrator.py

"""
Pipeline Orchestrator — создаёт Run и запускает первую задачу пайплайна по сделке.

Назначение:
- Создать запись Run в БД на основе playbook'а сделки.
- Поставить в очередь первую Celery-задачу пайплайна: workers.import_bundle.
- Вернуть run_id, чтобы API / фронт могли отслеживать прогресс запуска.

Архитектура:
- Внешний интерфейс — синхронная функция start_pipeline(...), которую вызывает API.
- Внутри один раз выполняется безопасный переход sync → async через run_async(...)
  для создания Run в БД.
- Orchestrator сам не выполняет импорт/анализ документов; он только:
  1) создаёт Run;
  2) инициирует первую задачу пайплайна.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import RunStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories import DealRepository, PlaybookRepository, RunRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)


def start_pipeline(deal_id: str, tenant_id: str, source_path: str) -> dict[str, Any]:
    """
    Синхронная точка входа для запуска пайплайна по сделке.

    Делает две вещи:
      1) создаёт Run в БД;
      2) ставит в очередь первую Celery-задачу workers.import_bundle.

    Если первую задачу не удалось поставить в очередь,
    исключение пробрасывается наружу — API не должен отвечать "started",
    если фактический запуск не произошёл.

    Дополнительно:
    - если enqueue первой задачи не удался, уже созданный Run помечается как FAILED,
      чтобы в БД не оставался "висячий" запуск без реального старта.
    """
    logger.info(
        "Pipeline start requested",
        deal_id=deal_id,
        tenant_id=tenant_id,
        source_path=source_path,
    )

    run_id = run_async(create_run_async(deal_id=deal_id, tenant_id=tenant_id))

    try:
        celery_app.send_task(
            "workers.import_bundle",
            kwargs={
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "source_path": source_path,
                "run_id": run_id,
            },
        )
    except Exception as e:
        logger.exception(
            "Failed to enqueue first pipeline task",
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            source_path=source_path,
            task_name="workers.import_bundle",
            error=str(e),
        )

        try:
            run_async(
                mark_run_enqueue_failed_async(
                    run_id=run_id,
                    message=("Run was created, but failed to enqueue " "workers.import_bundle"),
                    enqueue_error=str(e),
                )
            )
        except Exception as mark_error:
            logger.exception(
                "Failed to mark run as FAILED after enqueue error",
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(mark_error),
            )

        raise PermanentError(
            f"Run {run_id} was created, but failed to enqueue workers.import_bundle"
        ) from e

    logger.info(
        "Pipeline started",
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        source_path=source_path,
        first_task="workers.import_bundle",
    )

    return {
        "status": "started",
        "run_id": run_id,
    }


async def create_run_async(*, deal_id: str, tenant_id: str) -> str:
    """
    Async entrypoint для создания Run.

    Не знает про Celery и не запускает таски —
    только про бизнес-логику создания записи Run в БД.
    """
    return await _create_run(deal_id=deal_id, tenant_id=tenant_id)


async def _create_run(*, deal_id: str, tenant_id: str) -> str:
    """
    Создать запись Run в БД для указанной сделки.

    Логика:
    - найти playbook, привязанный к сделке, либо глобальный default;
    - создать Run на базе найденного playbook;
    - вернуть run_id как строку.
    """
    async with db_uow() as uow:
        db: AsyncSession = uow.session

        deal_repo = DealRepository(db)
        playbook_repo = PlaybookRepository(db)
        run_repo = RunRepository(db)

        deal_uuid = uuid.UUID(deal_id)
        tenant_uuid = uuid.UUID(tenant_id)

        await deal_repo.assert_tenant_owns_deal(
            deal_id=deal_uuid,
            tenant_id=tenant_uuid,
        )

        playbook = await playbook_repo.get_for_deal(deal_uuid)
        if playbook is None:
            logger.error(
                "Cannot create run: no playbook found for deal",
                deal_id=deal_id,
                tenant_id=tenant_id,
            )
            raise PermanentError("No playbook found for deal and no global default")

        deal_obj = await deal_repo.internal_unsafe_get_by_id(deal_uuid)
        if deal_obj is None:
            raise PermanentError(
                "Cannot create run: deal not found",
                details={"deal_id": deal_id},
            )

        run = await run_repo.create(
            deal_id=deal_uuid,
            tenant_id=deal_obj.tenant_id,
            playbook_version_id=playbook.id,
            model_config_id=playbook.model_config_id,
            bundle_id=None,
            environment_hash=None,
            profile="full",
            checks_mode="global_and_doc_type",
        )

        logger.info(
            "Run created",
            run_id=str(run.id),
            deal_id=deal_id,
            tenant_id=tenant_id,
            playbook_id=str(playbook.id),
            model_config_id=str(playbook.model_config_id) if playbook.model_config_id else None,
            profile="full",
            checks_mode="global_and_doc_type",
        )

        return str(run.id)


async def mark_run_enqueue_failed_async(
    *,
    run_id: str,
    message: str,
    enqueue_error: str,
) -> None:
    """
    Пометить Run как FAILED, если старт пайплайна не дошёл до первой очереди задач.

    Этот helper вызывается только в compensating-path:
    - Run уже создан;
    - workers.import_bundle не удалось enqueue;
    - нужно зафиксировать run в терминальном состоянии FAILED.
    """
    async with db_uow() as uow:
        db: AsyncSession = uow.session
        run_repo = RunRepository(db)

        await run_repo.update_status(
            uuid.UUID(run_id),
            RunStatus.FAILED.value,
            error_details={
                "stage": "orchestrator",
                "type": "queue_error",
                "reason": "enqueue_failed",
                "message": message,
                "details": {
                    "task_name": "workers.import_bundle",
                    "enqueue_error": enqueue_error,
                },
            },
        )

        logger.info(
            "Run marked as FAILED after enqueue error",
            run_id=run_id,
            failed_stage="orchestrator",
            failed_reason="enqueue_failed",
            task_name="workers.import_bundle",
        )
