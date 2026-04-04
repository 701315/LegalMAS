# src/workers/run_orchestrator.py

"""
Run Orchestrator Worker.

Назначение:
- Оркестрация пайплайна анализа для конкретного Run:
  primary_source -> extract -> pii -> structure
  -> (далее цепочка продолжается из самих воркеров: build_structure -> build_chunks -> classify).
- Находит все документы сделки и по их статусу решает, какие задачи поставить:
  - PENDING        -> workers.build_primary_language_source
  - PRIMARY_READY  -> workers.extract_document
  - EXTRACTED      -> pii.sanitize_document
  - SANITIZED      -> workers.build_structure
  - STRUCTURED     -> не трогаем, ждём chain из build_structure
  - CHUNKED        -> не трогаем, ждём chain из build_chunks
- Переводит Run в статус RUNNING и запоминает,
  для скольких документов будут запущены последующие стадии.
"""


import uuid

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
from services.run_checks_auto_starter import maybe_start_run_checks


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
    4) переводим Run в статус "running".
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

    Для непрофессионального программиста:
    - Здесь мы решаем, какие задачи по документам надо запустить.
    - Если документ уже дошёл до нужного статуса, мы можем переиспользовать результат.
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
        }

    # Пытаемся атомарно стартовать Run.
    # Если Run уже кто‑то запустил (или он уже завершён),
    # мы не должны повторно ставить задачи по документам.
    started = await run_repo.try_start_run(run_uuid)
    if not started:
        logger.info(
            "Run pipeline already started or finished, skipping orchestration",
            extra={"run_id": run_id},
        )
        return {
            "run_id": run_id,
            "deal_id": str(run_obj.deal_id) if run_obj and run_obj.deal_id else None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
        }

    # Определяем стратегию пайплайна для этого Run.
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
        }

    deal_id_str = str(deal_uuid)

    if tenant_id is None:
        if hasattr(run_obj, "deal") and run_obj.deal and hasattr(run_obj.deal, "tenant_id"):
            tenant_id_str = str(run_obj.deal.tenant_id)
        else:
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
        await run_repo.update_status(run_uuid, RunStatus.COMPLETED.value)

        return {
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": 0,
            "tasks_scheduled": 0,
        }

    tasks_scheduled = 0

    for doc in docs:
        doc_id_str = str(doc.id)
        status = doc.status or ""

        # Берём последнюю версию, чтобы проверить наличие артефактов
        # единого pipeline-контракта (layout_primary / layout_primary_sanitized и т.д.).
        version = await ver_repo.get_latest(doc.id)

        logger.info(
            "Evaluating document for run pipeline",
            extra={
                "run_id": run_id,
                "document_id": doc_id_str,
                "status": status,
                "doc_type": getattr(doc, "doctype", None),
                "classification_level": getattr(doc, "classification_level", None),
            },
        )

        # PENDING: только что импортированный/сконвертированный документ.
        # На этом шаге мы готовим основной источник по выбранному языку.
        if status == DocumentStatus.PENDING.value:
            if not version:
                logger.warning(
                    "Document has PENDING status but no version, skipping primary_source build",
                    extra={"document_id": doc_id_str},
                )
                continue

            celery_app.send_task(
                "workers.build_primary_language_source",
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

        # PRIMARY_READY: основной источник (primary_source_ref) уже построен.
        # Теперь можно извлекать текст и строить layout.
        if status == DocumentStatus.PRIMARY_READY.value:
            if not version:
                logger.warning(
                    "PRIMARY_READY document without version, skipping extract",
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

        # EXTRACTED
        if status == DocumentStatus.EXTRACTED.value:
            if not version or not getattr(version, "layout_primary_ref", None):
                logger.warning(
                    "EXTRACTED document without layout_primary_ref, skipping pii",
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

        # SANITIZED
        if status == DocumentStatus.SANITIZED.value:
            if not version:
                logger.warning(
                    "SANITIZED document without version, skipping structure",
                    extra={"document_id": doc_id_str},
                )
                continue

            has_sanitized = bool(
                getattr(version, "layout_primary_sanitized_ref", None)
            )
            has_primary = bool(getattr(version, "layout_primary_ref", None))

            # Для непрофессионального программиста:
            # - Нормальный путь: есть layout_primary_sanitized_ref (после PII).
            # - Recovery-путь: если по какой-то причине PII не сохранил sanitized layout,
            #   но есть layout_primary_ref, StructureBuilder по контракту умеет
            #   использовать и его.
            if not has_sanitized and not has_primary:
                logger.warning(
                    "SANITIZED document without layout_primary_sanitized_ref "
                    "or layout_primary_ref, skipping structure",
                    extra={"document_id": doc_id_str},
                )
                continue

            if not has_sanitized and has_primary:
                logger.warning(
                    "SANITIZED document without sanitized layout, "
                    "falling back to layout_primary_ref for structure building",
                    extra={"document_id": doc_id_str},
                )

            celery_app.send_task(
                "workers.build_structure",
                kwargs={
                    "document_version_id": str(version.id),
                    "run_id": run_id,
                },
            )
            tasks_scheduled += 1
            continue

        # STRUCTURED: структура уже построена.
        # Дальше цепочку ведёт сам workers.build_structure -> workers.build_chunks.
        if status == DocumentStatus.STRUCTURED.value:
            logger.info(
                "Document already structured, relying on downstream chaining "
                "from workers.build_structure to workers.build_chunks",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            continue

        # CHUNKED: чанки уже построены.
        # Дальше цепочку ведёт сам workers.build_chunks -> workers.classify_document.
        if status == DocumentStatus.CHUNKED.value:
            logger.info(
                "Document already chunked, relying on downstream chaining "
                "from workers.build_chunks to workers.classify_document",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            continue

        # CLASSIFIED: уже классифицирован
        if status == DocumentStatus.CLASSIFIED.value:
            if is_full_rerun or force_reclassify:
                # Вариант "полного прогона" — заново запускаем классификацию.
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
                    "Document already classified, reusing classification for this run",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
            continue

        # COMPLETED: документ уже прошёл полный пайплайн в прошлом Run.
        if status == DocumentStatus.COMPLETED.value:
            if is_full_rerun:
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
                    "Document already completed, reusing for this run",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
            continue

        # FAILED / QUARANTINE / другие статусы
        # ВАЖНО:
        # - Документы в статусах FAILED / QUARANTINE мы здесь не трогаем.
        # - Они не участвуют в дальнейших стадиях и не блокируют запуск checks,
        #   потому что maybe_start_run_checks учитывает только "живые" документы.
        # - Если оставить документ навсегда в промежуточном статусе
        #   (например, structured), но не перевести в FAILED/QUARANTINE
        #   при перманентной ошибке, Run может зависнуть в RUNNING.
        logger.info(
            "Document in unsupported status for run pipeline, skipping",
            extra={"document_id": doc_id_str, "status": status, "run_id": run_id},
        )

    logger.info(
        "Run pipeline documents evaluation complete",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": len(docs),
            "tasks_scheduled": tasks_scheduled,
        },
    )

    logger.info(
        "Run marked as RUNNING, calling maybe_start_run_checks",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
        },
    )

    # После того как Run стал RUNNING (в начале функции через try_start_run),
    # даём сигнал авто-стартеру checks.
    # Для непрофессионального программиста:
    # - maybe_start_run_checks сам посмотрит все документы сделки;
    # - если все "живые" документы уже CLASSIFIED/COMPLETED и
    #   ещё не запускались checks, он один раз поставит задачу
    #   workers.run_deal_checks.
    await maybe_start_run_checks(db=db, run_id=run_uuid)

    logger.info(
        "Run pipeline scheduling complete",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": len(docs),
            "tasks_scheduled": tasks_scheduled,
        },
    )

    return {
        "run_id": run_id,
        "deal_id": deal_id_str,
        "tenant_id": tenant_id_str,
        "documents_total": len(docs),
        "tasks_scheduled": tasks_scheduled,
    }


