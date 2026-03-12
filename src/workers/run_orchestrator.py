# src/workers/run_orchestrator.py

"""
Run Orchestrator Worker.

Назначение:
- Оркестрация пайплайна анализа для конкретного Run:
  extract -> pii -> structure -> classify -> run_checks.
- Находит все документы сделки и по их статусу решает, какие следующие задачи поставить.
- Обновляет метаданные Run (total_checks / completed_checks, статус).

Контракт:
- Таска запускается по run_id (и опционально deal_id/tenant_id).
- Для каждого документа сделки:
  * если документ ещё не прошёл нужные стадии — ставит соответствующие таски:
    - pending      -> workers.extract_document
    - extracted    -> pii.sanitize_document
    - sanitized    -> workers.build_structure
    - structured   -> workers.classify_document
  * если документ уже классифицирован:
    - при force_reclassify=True повторно ставит classify_document;
    - иначе не трогает run_checks напрямую (их запускает classify_document).

Архитектура:
- Внешняя Celery‑таска синхронная (def), чтобы Celery мог сериализовать результат.
- Вся работа с БД и логика оркестрации находятся в _start_run_pipeline_async()
  и вызываются из таски через безопасный переход sync → async (run_async).
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.constants import DocumentStatus
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
    4) обновляем метаданные Run (total_checks / completed_checks, статус).

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
        raise RuntimeError(f"Run {run_id} not found")

    # deal_id / tenant_id берём из Run / связанной сделки, если не переданы явно
    deal_uuid = run_obj.deal_id if run_obj.deal_id else uuid.UUID(deal_id) if deal_id else None
    if deal_uuid is None:
        raise RuntimeError(f"Run {run_id} has no deal_id")

    # Переводим Run в статус "running", если он ещё не запущен.
    # RunRepository.update_status сам проставит started_at, если нужно.
    if run_obj.status not in ("running", "completed", "failed"):
        await run_repo.update_status(run_uuid, "running")

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

    # Загружаем все документы сделки
    docs = await doc_repo.get_by_deal(deal_uuid)
    if not docs:
        logger.info(
            "No documents for deal, nothing to process",
            extra={"run_id": run_id, "deal_id": deal_id_str},
        )
        # Если документов нет, считаем Run сразу завершённым.
        await run_repo.update_status(run_uuid, "completed")

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
        if status in (
            DocumentStatus.PENDING.value,
            DocumentStatus.EXTRACTED.value,
            DocumentStatus.SANITIZED.value,
            DocumentStatus.STRUCTURED.value,
        ) or (status == DocumentStatus.CLASSIFIED.value and force_reclassify):
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

        # CLASSIFIED: уже классифицирован; решаем, нужно ли ещё раз запускать checks
        if status == DocumentStatus.CLASSIFIED.value:
            if force_reclassify:
                # Принудительная переклассификация + запуск run_checks
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
                # Статус уже CLASSIFIED → можно было бы сразу запускать run_checks,
                # но по контракту это делает только classify_document.
                logger.info(
                    "Document already classified, not re-running checks without force_reclassify",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
            continue

        # COMPLETED: документ уже прошёл полный пайплайн
        if status == DocumentStatus.COMPLETED.value:
            logger.info(
                "Document already completed, skipping in run pipeline",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            continue

        # Любые другие статусы пока просто логируем
        logger.info(
            "Document in unsupported status for run pipeline, skipping",
            extra={"document_id": doc_id_str, "status": status, "run_id": run_id},
        )

    # Обновляем total_checks / completed_checks для Run.
    # total_checks = количество документов, которые должны пройти run_checks в рамках этого Run.
    await run_repo.update_status(
        run_uuid,
        "running",
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
