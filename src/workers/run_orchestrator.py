"""
Run Orchestrator Worker.

Назначение:
- Единый центр оркестрации document-level пайплайна для конкретного Run.
- По статусу документа и наличию артефактов решает, какую ИМЕННО одну следующую
  stage-task нужно поставить в очередь.
- Не вызывает downstream-воркеры напрямую и не полагается на chaining внутри воркеров.
  Stage-воркеры после фиксации результата могут только заново будить оркестратор
  тем же run_id.

Актуальная последовательность стадий:
- PENDING          -> workers.convert_to_pdf (для конвертируемых типов без PDF)
                     -> workers.build_primary_language_source
- PRIMARY_READY    -> workers.extract_document
- EXTRACTED        -> pii.sanitize_document
- SANITIZED        -> workers.build_structure
- STRUCTURED       -> workers.build_chunks
- CHUNKED          -> workers.classify_document
- CLASSIFIED/COMPLETED -> reuse или reclassify по стратегии Run

Ключевой принцип:
- Каждый stage-worker отвечает только за свою стадию и фиксацию её результата.
- Только run_orchestrator решает, что запускать дальше.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStatus, RunStatus
from core.logging import get_logger
from db.models.run import Run
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_checks_auto_starter import maybe_start_run_checks

logger = get_logger(__name__)

# Типы файлов, которые поддерживает LibreOffice-конвертер (office-converter)
CONVERTIBLE_TO_PDF: set[str] = {
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "rtf",
    "csv",
    "html",
    "htm",
}


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
    Sync Celery entrypoint для оркестрации Run.

    Шаги:
    1) по run_id находим Run и его deal_id;
    2) при первом входе стартуем Run из PENDING в RUNNING;
    3) обходим все документы сделки;
    4) для каждого документа по статусу и артефактам выбираем следующую стадию;
    5) после планирования вызываем maybe_start_run_checks().
    """

    async def _wrapper() -> dict:
        async with db_uow() as uow:
            return await _start_run_pipeline_async(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                force_reclassify=force_reclassify,
                db=uow.session,
            )

    return run_async(_wrapper())


async def _start_run_pipeline_async(
    run_id: str,
    deal_id: str | None,
    tenant_id: str | None,
    force_reclassify: bool,
    db: AsyncSession,
) -> dict:
    """
    Async-ядро оркестрации Run.

    Правило:
    - на один проход оркестратора для одного документа ставим не более ОДНОЙ
      следующей стадии;
    - решение принимается по status + наличию артефактов версии;
    - RUNNING run допускает повторный вход (re-entry) оркестратора.
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

    # Обработка статуса Run: первый запуск vs re-entry vs терминальные состояния
    current_status = run_obj.status

    if current_status == RunStatus.PENDING.value:
        # Первый вход — пытаемся атомарно стартовать Run
        started = await run_repo.try_start_run(run_uuid)
        if not started:
            # Перечитываем Run, чтобы понять текущий статус
            run_obj = await run_repo.get_by_id(run_uuid)
            current_status = run_obj.status if run_obj else None
            if current_status not in {RunStatus.RUNNING.value}:
                logger.info(
                    "Run pipeline cannot be started from non-pending state, skipping orchestration",
                    extra={"run_id": run_id, "status": current_status},
                )
                return {
                    "run_id": run_id,
                    "deal_id": str(run_obj.deal_id) if run_obj and run_obj.deal_id else None,
                    "tenant_id": tenant_id,
                    "documents_total": 0,
                    "tasks_scheduled": 0,
                }
            logger.info(
                "Run transitioned to RUNNING concurrently, continuing orchestration",
                extra={"run_id": run_id},
            )

    elif current_status == RunStatus.RUNNING.value:
        # Нормальный re-entry во время идущего Run
        logger.info(
            "Run already RUNNING, continuing orchestration pass",
            extra={"run_id": run_id},
        )

    elif current_status in {
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    }:
        # Терминальные состояния — оркестратор больше не вмешивается
        logger.info(
            "Run already in terminal status, skipping orchestration",
            extra={"run_id": run_id, "status": current_status},
        )
        return {
            "run_id": run_id,
            "deal_id": str(run_obj.deal_id) if run_obj and run_obj.deal_id else None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
        }
    else:
        # Неподдерживаемый/неизвестный статус
        logger.warning(
            "Run in unsupported status for orchestration, skipping",
            extra={"run_id": run_id, "status": current_status},
        )
        return {
            "run_id": run_id,
            "deal_id": str(run_obj.deal_id) if run_obj and run_obj.deal_id else None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
        }

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

    deal_uuid = run_obj.deal_id if run_obj.deal_id else (uuid.UUID(deal_id) if deal_id else None)
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
        logger.error("Run has no deal_id", extra={"run_id": run_id})
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
        version = await ver_repo.get_latest(doc.id)

        logger.info(
            "Evaluating document for run pipeline",
            extra={
                "run_id": run_id,
                "document_id": doc_id_str,
                "status": status,
                "doc_type": getattr(doc, "doc_type", None),
                "classification_level": getattr(doc, "classification_level", None),
            },
        )

        # PENDING -> convert_to_pdf (для конвертируемых типов без PDF)
        #         -> build_primary_language_source
        if status == DocumentStatus.PENDING.value:
            if not version:
                logger.warning(
                    "Document has PENDING status but no version, skipping next stage",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
                continue

            origin_filetype = str(getattr(version, "origin_filetype", "") or "").lower()
            has_converted_pdf = bool(getattr(version, "converted_pdf_ref", None))

            # Сначала конвертация в PDF, если тип поддерживается и PDF ещё нет
            if origin_filetype in CONVERTIBLE_TO_PDF and not has_converted_pdf:
                logger.info(
                    "PENDING document requires conversion to PDF before primary source build",
                    extra={
                        "document_id": doc_id_str,
                        "document_version_id": str(version.id),
                        "origin_filetype": origin_filetype,
                        "run_id": run_id,
                    },
                )
                celery_app.send_task(
                    "workers.convert_to_pdf",
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

            # Если это уже PDF или для конвертируемого типа уже есть converted_pdf_ref,
            # можно строить primary language source
            logger.info(
                "PENDING document ready for primary source build",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "origin_filetype": origin_filetype,
                    "has_converted_pdf": has_converted_pdf,
                    "run_id": run_id,
                },
            )
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

        # PRIMARY_READY -> extract_document
        if status == DocumentStatus.PRIMARY_READY.value:
            if not version:
                logger.warning(
                    "PRIMARY_READY document without version, skipping extract",
                    extra={"document_id": doc_id_str, "run_id": run_id},
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

        # EXTRACTED -> pii.sanitize_document
        if status == DocumentStatus.EXTRACTED.value:
            if not version or not getattr(version, "layout_primary_ref", None):
                logger.warning(
                    "EXTRACTED document without layout_primary_ref, skipping pii",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
                continue

            celery_app.send_task(
                "pii.sanitize_document",
                kwargs={
                    "document_version_id": str(version.id),
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                    "run_id": run_id,
                },
            )
            tasks_scheduled += 1
            continue

        # SANITIZED -> build_structure
        if status == DocumentStatus.SANITIZED.value:
            if not version:
                logger.warning(
                    "SANITIZED document without version, skipping structure",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
                continue

            has_sanitized = bool(getattr(version, "layout_primary_sanitized_ref", None))
            has_primary = bool(getattr(version, "layout_primary_ref", None))

            if not has_sanitized and not has_primary:
                logger.warning(
                    "SANITIZED document without layout_primary_sanitized_ref or layout_primary_ref, skipping structure",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
                continue

            if not has_sanitized and has_primary:
                logger.warning(
                    "SANITIZED document without sanitized layout, "
                    "falling back to layout_primary_ref for structure building",
                    extra={"document_id": doc_id_str, "run_id": run_id},
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

        # STRUCTURED -> build_chunks
        if status == DocumentStatus.STRUCTURED.value:
            if not version:
                logger.warning(
                    "STRUCTURED document without version, skipping",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
                continue

            has_clause_tree = bool(getattr(version, "clause_tree_ref", None))
            if not has_clause_tree:
                logger.warning(
                    "STRUCTURED document without clause_tree_ref, cannot continue",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
                continue

            celery_app.send_task(
                "workers.build_chunks",
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

        # CHUNKED -> classify_document
        if status == DocumentStatus.CHUNKED.value:
            if not version:
                logger.warning(
                    "CHUNKED document without version, skipping classify",
                    extra={"document_id": doc_id_str, "run_id": run_id},
                )
                continue

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

        # CLASSIFIED: reuse или reclassify
        if status == DocumentStatus.CLASSIFIED.value:
            if is_full_rerun or force_reclassify:
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

        # COMPLETED: reuse или reclassify по стратегии
        if status == DocumentStatus.COMPLETED.value:
            if is_full_rerun or force_reclassify:
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

        # FAILED / QUARANTINE / DUPLICATE / DELETED / ANALYZING и прочие терминальные/неподдерживаемые
        logger.info(
            "Document in unsupported or terminal status for run pipeline, skipping",
            extra={
                "document_id": doc_id_str,
                "status": status,
                "run_id": run_id,
            },
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

    # Даём сигнал авто-стартеру checks
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

