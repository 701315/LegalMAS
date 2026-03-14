# src/workers/run_orchestrator.py

"""
Run Orchestrator Worker.

Назначение:
- Оркестрация пайплайна анализа для конкретного Run:
  extract -> pii -> structure -> classify -> run_checks.
- Находит все документы сделки и по их статусу решает, какие задачи поставить:
  - PENDING     -> workers.extract_document
  - EXTRACTED   -> pii.sanitize_document
  - SANITIZED   -> workers.build_structure
  - STRUCTURED  -> workers.classify_document
- Обновляет метаданные Run:
  - total_checks — сколько документов должны дойти до стадии checks;
  - completed_checks — сколько документов уже успешно прошли checks;
  - статус Run (pending/running/completed/completed_with_errors/failed).

Как это выглядит для юриста:

- Он запускает Run по сделке (через HTTP‑эндпоинт).
- Оркестратор:
  - переводит Run в статус "running";
  - проходит по всем документам сделки;
  - по статусу каждого документа решает, какие следующие этапы запускаются;
  - считает, для скольких документов будет выполнен stage "checks" (total_checks).
- Дальше отдельные воркеры (extract/pii/structure/classify/run_checks) делают свою работу.
- Когда все документы прошли checks, Runner:
  - завершает Run как "completed", если ни один документ не в FAILED/QUARANTINE;
  - или как "completed_with_errors", если есть проблемные документы.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.constants import DocumentStatus, RunStatus
from db.models.run import Run
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async  # единый мост sync → async

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.start_run_pipeline",
    track_job=False,
    queue="default",
)
def start_run_pipeline(
    self,
    run_id: str,
    deal_id: str | None = None,
    tenant_id: str | None = None,
    force_reclassify: bool = False,
) -> dict:
    """
    Sync Celery entrypoint для оркестрации пайплайна Run.

    Шаги:
    1) по run_id находим Run и его deal_id (если не передан);
    2) по deal_id и tenant_id (из сделки) обходим все документы;
    3) для каждого документа по статусу решаем, какие стадии запускать;
    4) устанавливаем total_checks и сбрасываем completed_checks в 0;
    5) переводим Run в статус "running" (если он ещё не в финальном состоянии).

    ВАЖНО:
    - здесь мы не создаём свой event loop напрямую;
    - весь async‑код выполняется через общий helper run_async().
    """

    async def _wrapper() -> dict:
        # db_uow создаёт отдельную AsyncSession и управляет commit/rollback/close.
        async with db_uow() as uow:
            return await _start_run_pipeline_async(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                force_reclassify=force_reclassify,
                db=uow.session,
            )

    # Запускаем асинхронный код через единый мост run_async
    return run_async(_wrapper())


async def _start_run_pipeline_async(
    run_id: str,
    deal_id: str | None,
    tenant_id: str | None,
    force_reclassify: bool,
    db: AsyncSession,
) -> dict:
    """
    Async‑ядро оркестрации Run.

    Все операции с БД выполняются через переданную AsyncSession (db).

    Важные моменты с точки зрения статусов Run:

    - если Run или deal_id не найдены — бросаем исключение (внешний код может
      пометить Run как failed и записать error_details);
    - если документов по сделке нет — Run сразу помечается как "completed"
      (анализ ничего не делал, но запуск корректен);
    - для нормального сценария:
      * считаем expected_checks_docs (total_checks);
      * ставим задачи по пайплайну;
      * переводим Run в "running" с total_checks и completed_checks=0.
    """
    logger.info(
        "Starting run pipeline",
        extra={
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "force_reclassify": force_reclassify,
        },
    )

    run_repo = RunRepository(db)
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)

    run_uuid = uuid.UUID(run_id)
    run_obj: Run | None = await run_repo.get_by_id(run_uuid)
    if not run_obj:
        # Конфигурационная ошибка: указанный Run не существует.
        await run_repo.update_status(
            run_uuid,
            RunStatus.FAILED.value,
            error_details={
                "stage": "orchestrator",
                "type": "config_error",
                "reason": "run_not_found",
                "message": f"Run {run_id} not found",
            },
        )
        logger.error(
            "Run not found for orchestrator",
            extra={"run_id": run_id},
        )
        return {
            "run_id": run_id,
            "deal_id": None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "expected_checks_docs": 0,
        }

    # Определяем стратегию пайплайна для этого Run.
    # Пока поддерживаем только REUSE_STRUCTURE (по сути, текущее поведение).
    pipeline_strategy = getattr(run_obj, "pipeline_strategy", "REUSE_STRUCTURE")
    is_full_rerun = pipeline_strategy == "FULL_RERUN"

    logger.info(
        "Resolved run pipeline strategy",
        extra={
            "run_id": run_id,
            "pipeline_strategy": pipeline_strategy,
            "force_reclassify": force_reclassify,
        },
    )

    # deal_id / tenant_id берём из Run / связанной сделки, если не переданы явно.

    deal_uuid = (
        run_obj.deal_id
        if run_obj.deal_id
        else uuid.UUID(deal_id) if deal_id else None
    )
    if deal_uuid is None:
        await run_repo.update_status(
            run_uuid,
            RunStatus.FAILED.value,
            error_details={
                "stage": "orchestrator",
                "type": "config_error",
                "reason": "deal_not_bound",
                "message": f"Run {run_id} has no deal_id",
            },
        )
        logger.error(
            "Run has no deal_id",
            extra={"run_id": run_id},
        )
        return {
            "run_id": run_id,
            "deal_id": None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "expected_checks_docs": 0,
        }

    deal_id_str = str(deal_uuid)

    # tenant_id: предполагаем, что Run связан с Deal через ORM (deal.tenant_id),
    # либо в репозитории RunRepository.get_by_id подгружается deal.
    # Если нет — используем fallback.
    if tenant_id is None:
        if hasattr(run_obj, "deal") and run_obj.deal and hasattr(run_obj.deal, "tenant_id"):
            tenant_id_str = str(run_obj.deal.tenant_id)
        else:
            # fallback: для dev‑режима используем deal_id как tenant_id
            tenant_id_str = deal_id_str
    else:
        tenant_id_str = tenant_id

    # Загружаем все документы сделки.
    docs = await doc_repo.get_by_deal(deal_uuid)
    if not docs:
        logger.info(
            "No documents for deal, nothing to process",
            extra={"run_id": run_id, "deal_id": deal_id_str},
        )
        # Если документов нет, считаем Run сразу завершённым:
        # для юриста это «анализ ничего не делал, но запуск завершился без ошибок».
        await run_repo.update_status(run_uuid, RunStatus.COMPLETED.value)


        return {
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "expected_checks_docs": 0,
        }

    tasks_scheduled = 0
    expected_checks_docs = 0  # сколько документов должны пройти run_checks

    for doc in docs:
        doc_id_str = str(doc.id)
        status = doc.status or ""

        # Берём последнюю версию для понимания, есть ли layout_raw и т.п.
        version = await ver_repo.get_latest(doc.id)

        logger.info(
            "Evaluating document for run pipeline",
            extra={
                "run_id": run_id,
                "document_id": doc_id_str,
                "status": status,
            },
        )

        # Документ участвует в Run (будет иметь run_checks), если:
        # - он ещё в одном из рабочих статусов, ведущих к классификации,
        #   или
        # - уже classified, но мы явно просим force_reclassify.

        participates = False

        if is_full_rerun:
            # В режиме полного перерасчёта все «живые» документы участвуют в Run,
            # даже если уже были COMPLETED или CLASSIFIED.
            participates = status in (
                DocumentStatus.PENDING.value,
                DocumentStatus.EXTRACTED.value,
                DocumentStatus.SANITIZED.value,
                DocumentStatus.STRUCTURED.value,
                DocumentStatus.CLASSIFIED.value,
                DocumentStatus.COMPLETED.value,
            )
        else:
            # Старое поведение: только не-дошедшие до конца + опционально CLASSIFIED
            # при force_reclassify.
            participates = status in (
                DocumentStatus.PENDING.value,
                DocumentStatus.EXTRACTED.value,
                DocumentStatus.SANITIZED.value,
                DocumentStatus.STRUCTURED.value,
            ) or (status == DocumentStatus.CLASSIFIED.value and force_reclassify)

        if participates:
            expected_checks_docs += 1

        # PENDING (ещё не прошёл extract)
        if status == DocumentStatus.PENDING.value:
            if not version:
                logger.warning(
                    "Document has PENDING status but no version, skipping extract",
                    extra={"document_id": doc_id_str},
                )
                continue

            celery_app.send_task(
                "workers.extract_document",
                kwargs={
                    "document_version_id": str(version.id),
                    "document_id": doc_id_str,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                    "run_id": run_id,
                },
            )
            tasks_scheduled += 1
            continue

        # EXTRACTED: есть raw layout, но ещё не sanitiz'или
        if status == DocumentStatus.EXTRACTED.value:
            if not version or not version.text_layout_raw_ref:
                logger.warning(
                    "EXTRACTED document without text_layout_raw_ref, skipping pii",
                    extra={"document_id": doc_id_str},
                )
                continue

            celery_app.send_task(
                "pii.sanitize_document",
                kwargs={
                    "document_version_id": str(version.id),
                },
            )
            tasks_scheduled += 1
            continue

        # SANITIZED: PII уже отработал, но нет структуры
        if status == DocumentStatus.SANITIZED.value:
            if not version or not version.text_layout_raw_ref:
                logger.warning(
                    "Sanitized document without text_layout_raw_ref, skipping structure",
                    extra={"document_id": doc_id_str},
                )
                continue

            celery_app.send_task(
                "workers.build_structure",
                kwargs={
                    "document_version_id": str(version.id),
                    "run_id": run_id,
                },
            )
            tasks_scheduled += 1
            continue

        # STRUCTURED: есть clause_tree, но ещё не классифицирован
        if status == DocumentStatus.STRUCTURED.value:
            celery_app.send_task(
                "workers.classify_document",
                kwargs={
                    "document_id": doc_id_str,
                    "run_id": run_id,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                },
            )
            tasks_scheduled += 1
            continue

        # CLASSIFIED: уже классифицирован; решаем, нужно ли ещё раз запускать checks.
        if status == DocumentStatus.CLASSIFIED.value:
            if is_full_rerun or force_reclassify:
                # При полном перерасчёте или принудительной переклассификации
                # запускаем классификацию ещё раз (run_checks внутри неё).
                celery_app.send_task(
                    "workers.classify_document",
                    kwargs={
                        "document_id": doc_id_str,
                        "run_id": run_id,
                        "deal_id": deal_id_str,
                        "tenant_id": tenant_id_str,
                    },
                )
                tasks_scheduled += 1
            else:
                logger.info(
                    "Document already classified, not re-running checks without force_reclassify",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
            continue

        # COMPLETED: документ уже прошёл полный пайплайн.
        # Runner и другие воркеры уже обновили статусы и результаты.
        if status == DocumentStatus.COMPLETED.value:
            if is_full_rerun:
                # В полном режиме считаем, что документ нужно прогнать ещё раз,
                # начиная с классификации (структура и layout уже есть).
                celery_app.send_task(
                    "workers.classify_document",
                    kwargs={
                        "document_id": doc_id_str,
                        "run_id": run_id,
                        "deal_id": deal_id_str,
                        "tenant_id": tenant_id_str,
                    },
                )
                tasks_scheduled += 1
            else:
                logger.info(
                    "Document already completed, skipping in run pipeline",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
            continue

        # FAILED / QUARANTINE / другие статусы:
        # на уровне оркестратора мы их не трогаем, просто логируем.
        logger.info(
            "Document in unsupported status for run pipeline, skipping",
            extra={"document_id": doc_id_str, "status": status, "run_id": run_id},
        )

    # Обновляем total_checks / completed_checks для Run.
    # total_checks = количество документов, которые должны пройти run_checks в рамках этого Run.
    # completed_checks сбрасываем в 0 — Runner будет инкрементировать по мере завершения checks.
    await run_repo.update_status(
        run_uuid,
        RunStatus.RUNNING.value,
        total_checks=expected_checks_docs,
        completed_checks=0,
    )

    logger.info(
        "Run pipeline scheduling complete",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": len(docs),
            "tasks_scheduled": tasks_scheduled,
            "expected_checks_docs": expected_checks_docs,
        },
    )

    return {
        "run_id": run_id,
        "deal_id": deal_id_str,
        "tenant_id": tenant_id_str,
        "documents_total": len(docs),
        "tasks_scheduled": tasks_scheduled,
        "expected_checks_docs": expected_checks_docs,
    }
