# src/workers/run_orchestrator.py

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
- PENDING           -> workers.convert_to_pdf (для конвертируемых типов без PDF)
                      -> workers.build_primary_language_source
- PRIMARY_READY     -> workers.extract_document
- EXTRACTED         -> pii.sanitize_document
- SANITIZED         -> workers.build_structure
- STRUCTURED        -> workers.build_chunks
- CHUNKED           -> workers.classify_document
- CLASSIFIED/COMPLETED -> reuse или reclassify по стратегии Run

Ключевой принцип:
- Каждый stage-worker отвечает только за свою стадию и фиксацию её результата.
- Только run_orchestrator решает, что запускать дальше.

Дополнительно (после введения document_stage_executions):
- Для каждой постановки stage-task создаётся execution-запись.
- Активный execution (planned / dispatched / started) блокирует
  повторное планирование той же стадии для той же версии.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStatus, RunStatus
from core.logging import get_logger
from db.models.run import Run
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_checks_auto_starter import maybe_start_run_checks

logger = get_logger(__name__)

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


ORCHESTRATION_STRATEGY_V2_ONLY = "V2_ONLY"


@dataclass(slots=True)
class TaskPlan:
    task_name: str
    kwargs: dict[str, Any]
    reason: str
    stage: str


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
    5) для выбранной стадии пытаемся создать execution-запись и поставить задачу;
    6) после планирования вызываем maybe_start_run_checks().
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

    После введения document_stage_executions:
    - перед постановкой задачи мы пытаемся создать execution-запись;
    - если активная запись уже есть, задачу повторно не ставим.
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
    dse_repo = DocumentStageExecutionRepository(db)

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
            "documents_with_plan": 0,
        }

    current_status = run_obj.status

    if current_status == RunStatus.PENDING.value:
        started = await run_repo.try_start_run(run_uuid)
        if not started:
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
                    "documents_with_plan": 0,
                }
            logger.info(
                "Run transitioned to RUNNING concurrently, continuing orchestration",
                extra={"run_id": run_id},
            )

    elif current_status == RunStatus.RUNNING.value:
        logger.info(
            "Run already RUNNING, continuing orchestration pass",
            extra={"run_id": run_id},
        )

    elif current_status in {
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    }:
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
            "documents_with_plan": 0,
        }

    else:
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
            "documents_with_plan": 0,
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
            "documents_with_plan": 0,
        }

    deal_id_str = str(deal_uuid)

    if tenant_id is None:
        if hasattr(run_obj, "deal") and run_obj.deal and hasattr(run_obj.deal, "tenant_id"):
            tenant_id_str = str(run_obj.deal.tenant_id)
        else:
            await run_repo.update_status(
                run_uuid,
                RunStatus.FAILED.value,
                error_details={
                    "stage": "orchestrator",
                    "type": "config_error",
                    "reason": "tenant_not_resolved",
                    "message": (
                        "Run has no explicit tenant_id and deal.tenant_id is not available; "
                        "refusing to guess tenant from deal_id string"
                    ),
                },
            )
            logger.error(
                "Cannot resolve tenant_id for run, stopping orchestration",
                extra={"run_id": run_id, "deal_id": deal_id_str},
            )
            return {
                "run_id": run_id,
                "deal_id": deal_id_str,
                "tenant_id": None,
                "documents_total": 0,
                "tasks_scheduled": 0,
                "documents_with_plan": 0,
            }
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
            "documents_with_plan": 0,
        }

    tasks_scheduled = 0
    documents_with_plan = 0

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

        seg_repo = DocumentSegmentRepository(db)

        plan = await _build_document_task_plan(
            doc=doc,
            version=version,
            status=status,
            run_id=run_id,
            deal_id_str=deal_id_str,
            tenant_id_str=tenant_id_str,
            is_full_rerun=is_full_rerun,
            force_reclassify=force_reclassify,
            seg_repo=seg_repo,
        )

        if not plan:
            logger.info(
                "No next task scheduled for document",
                extra={
                    "run_id": run_id,
                    "document_id": doc_id_str,
                    "status": status,
                },
            )
            continue

        if not version:
            logger.warning(
                "Task plan produced for document without version, skipping execution scheduling",
                extra={"run_id": run_id, "document_id": doc_id_str, "status": status},
            )
            continue

        # Для V2_ONLY мира orchestration_strategy фиксируем явно.
        orchestration_strategy = ORCHESTRATION_STRATEGY_V2_ONLY

        # Пытаемся создать execution-запись для этой стадии.
        execution = await dse_repo.create_planned_or_none_on_conflict(
            run_id=run_uuid,
            document_id=doc.id,
            document_version_id=version.id,
            from_status=status,
            to_status=_target_status_for_stage(plan.stage),
            orchestration_strategy=orchestration_strategy,
            task_name=plan.task_name,
        )

        if execution is None:
            logger.info(
                "Active execution already exists for this stage, skipping duplicate scheduling",
                extra={
                    "run_id": run_id,
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "status": status,
                    "task_name": plan.task_name,
                    "stage": plan.stage,
                    "reason": plan.reason,
                    "orchestration_strategy": orchestration_strategy,
                },
            )
            continue

        logger.info(
            "Scheduling next document stage",
            extra={
                "run_id": run_id,
                "document_id": doc_id_str,
                "document_version_id": str(version.id),
                "status": status,
                "task_name": plan.task_name,
                "stage": plan.stage,
                "reason": plan.reason,
                "orchestration_strategy": orchestration_strategy,
                "stage_execution_id": str(execution.id),
            },
        )

        _send_task(
            plan=plan,
            stage_execution_id=str(execution.id),
            run_id=run_id,
            deal_id=deal_id_str,
            tenant_id=tenant_id_str,
            document_id=doc_id_str,
            document_version_id=str(version.id),
            orchestration_strategy=orchestration_strategy,
        )
        tasks_scheduled += 1
        documents_with_plan += 1

    logger.info(
        "Run pipeline documents evaluation complete",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": len(docs),
            "tasks_scheduled": tasks_scheduled,
            "documents_with_plan": documents_with_plan,
        },
    )

    await maybe_start_run_checks(db=db, run_id=run_uuid)

    logger.info(
        "Run pipeline scheduling complete",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": len(docs),
            "tasks_scheduled": tasks_scheduled,
            "documents_with_plan": documents_with_plan,
        },
    )

    return {
        "run_id": run_id,
        "deal_id": deal_id_str,
        "tenant_id": tenant_id_str,
        "documents_total": len(docs),
        "tasks_scheduled": tasks_scheduled,
        "documents_with_plan": documents_with_plan,
    }


def _target_status_for_stage(stage: str) -> str:
    """
    Map internal stage name to target DocumentStatus.

    Это нужно, чтобы execution-запись знала, какой статус документа
    ожидается после успешного выполнения этой стадии.
    """
    if stage == "convert_to_pdf":
        return DocumentStatus.PENDING.value
    if stage == "build_primary_language_source":
        return DocumentStatus.PRIMARY_READY.value
    if stage == "extract_document":
        return DocumentStatus.EXTRACTED.value
    if stage == "sanitize_document":
        return DocumentStatus.SANITIZED.value
    if stage == "build_structure":
        return DocumentStatus.STRUCTURED.value
    if stage == "build_chunks":
        return DocumentStatus.CHUNKED.value
    if stage == "classify_document":
        # Документ может остаться CLASSIFIED или перейти в COMPLETED,
        # но для purposes execution достаточно понимать, что это стадия классификации.
        return DocumentStatus.CLASSIFIED.value
    return stage


async def _build_document_task_plan(
    *,
    doc,
    version,
    status: str,
    run_id: str,
    deal_id_str: str,
    tenant_id_str: str,
    is_full_rerun: bool,
    force_reclassify: bool,
    seg_repo: DocumentSegmentRepository,
) -> TaskPlan | None:
    doc_id_str = str(doc.id)

    if status == DocumentStatus.PENDING.value:
        if not version:
            logger.warning(
                "Document has PENDING status but no version, skipping next stage",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        origin_filetype = str(getattr(version, "origin_filetype", "") or "").lower()
        has_converted_pdf = bool(getattr(version, "converted_pdf_ref", None))
        original_ref = getattr(version, "original_ref", None)

        if origin_filetype in CONVERTIBLE_TO_PDF and not has_converted_pdf:
            logger.info(
                "PENDING document requires office-to-PDF conversion before primary source build",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "origin_filetype": origin_filetype,
                    "has_converted_pdf": has_converted_pdf,
                    "original_ref": original_ref,
                    "run_id": run_id,
                },
            )
            return TaskPlan(
                task_name="workers.convert_to_pdf",
                stage="convert_to_pdf",
                reason="convertible_type_without_converted_pdf",
                kwargs={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                    "run_id": run_id,
                },
            )

        source_kind = "converted_pdf_ref" if has_converted_pdf else "original_ref"
        logger.info(
            "PENDING document ready for primary source build",
            extra={
                "document_id": doc_id_str,
                "document_version_id": str(version.id),
                "origin_filetype": origin_filetype,
                "has_converted_pdf": has_converted_pdf,
                "source_kind": source_kind,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.build_primary_language_source",
            stage="build_primary_language_source",
            reason="pending_document_has_pdf_source",
            kwargs={
                "document_version_id": str(version.id),
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    if status == DocumentStatus.PRIMARY_READY.value:
        if not version:
            logger.warning(
                "PRIMARY_READY document without version, skipping extract",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        primary_ref = getattr(version, "primary_source_ref", None)
        if not primary_ref:
            logger.warning(
                "PRIMARY_READY document without primary_source_ref, waiting for primary source commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "PRIMARY_READY document ready for extract",
            extra={
                "document_id": doc_id_str,
                "document_version_id": str(version.id),
                "primary_source_ref": primary_ref,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.extract_document",
            stage="extract_document",
            reason="primary_source_is_ready",
            kwargs={
                "document_version_id": str(version.id),
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    if status == DocumentStatus.EXTRACTED.value:
        if not version:
            logger.warning(
                "EXTRACTED document without version, skipping pii",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        layout_primary_ref = getattr(version, "layout_primary_ref", None)
        if not layout_primary_ref:
            logger.warning(
                "EXTRACTED document without layout_primary_ref, waiting for extract commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "EXTRACTED document ready for PII sanitization",
            extra={
                "document_id": doc_id_str,
                "document_version_id": str(version.id),
                "layout_primary_ref": layout_primary_ref,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="pii.sanitize_document",
            stage="sanitize_document",
            reason="layout_primary_ready",
            kwargs={
                "document_version_id": str(version.id),
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    if status == DocumentStatus.SANITIZED.value:
        if not version:
            logger.warning(
                "SANITIZED document without version, skipping structure",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        layout_primary_sanitized_ref = getattr(
            version, "layout_primary_sanitized_ref", None
        )
        if not layout_primary_sanitized_ref:
            logger.warning(
                "SANITIZED document without layout_primary_sanitized_ref, waiting for PII commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "SANITIZED document ready for structure build",
            extra={
                "document_id": doc_id_str,
                "document_version_id": str(version.id),
                "layout_primary_sanitized_ref": layout_primary_sanitized_ref,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.build_structure",
            stage="build_structure",
            reason="sanitized_layout_ready",
            kwargs={
                "document_version_id": str(version.id),
                "run_id": run_id,
            },
        )

    if status == DocumentStatus.STRUCTURED.value:
        if not version:
            logger.warning(
                "STRUCTURED document without version, skipping chunks",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        file_graph_ref = getattr(version, "file_graph_ref", None)
        segments_count = getattr(version, "segments_count", None)

        if not file_graph_ref:
            logger.warning(
                "STRUCTURED document without file_graph_ref in V2_ONLY, waiting for structure v2 commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "run_id": run_id,
                },
            )
            return None

        if not segments_count or segments_count <= 0:
            logger.warning(
                "STRUCTURED document without segments_count in V2_ONLY, waiting for structure v2 commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "segments_count": segments_count,
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "STRUCTURED document ready for chunk build (v2 structure artifacts present)",
            extra={
                "document_id": doc_id_str,
                "document_version_id": str(version.id),
                "file_graph_ref": file_graph_ref,
                "segments_count": segments_count,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.build_chunks",
            stage="build_chunks",
            reason="structure_v2_ready",
            kwargs={
                "document_version_id": str(version.id),
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    if status == DocumentStatus.CHUNKED.value:
        if not version:
            logger.warning(
                "CHUNKED document without version, skipping classify",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        chunks_manifest_v2_ref = getattr(version, "chunks_manifest_v2_ref", None)
        if not chunks_manifest_v2_ref:
            logger.warning(
                "CHUNKED document without chunks_manifest_v2_ref in V2_ONLY, waiting for chunk v2 commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "run_id": run_id,
                },
            )
            return None

        summary = await seg_repo.get_chunk_refs_summary(version.id)
        total_segments = summary["total_segments"]
        segments_with_chunks = summary["segments_with_chunks"]

        if total_segments <= 0:
            logger.warning(
                "CHUNKED document without persisted segments in V2_ONLY, cannot continue to classification",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
                    "run_id": run_id,
                },
            )
            return None

        if segments_with_chunks != total_segments:
            logger.warning(
                "CHUNKED document has incomplete segment chunk refs in V2_ONLY, waiting for full chunk contract",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": str(version.id),
                    "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
                    "total_segments": total_segments,
                    "segments_with_chunks": segments_with_chunks,
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "CHUNKED document ready for classification (v2 manifest + full segment chunk refs)",
            extra={
                "document_id": doc_id_str,
                "document_version_id": str(version.id),
                "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
                "total_segments": total_segments,
                "segments_with_chunks": segments_with_chunks,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.classify_document",
            stage="classify_document",
            reason="chunks_v2_contract_ready",
            kwargs={
                "document_id": doc_id_str,
                "run_id": run_id,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
            },
        )

    if status == DocumentStatus.CLASSIFIED.value:
        if is_full_rerun or force_reclassify:
            logger.info(
                "CLASSIFIED document scheduled for reclassification",
                extra={
                    "document_id": doc_id_str,
                    "run_id": run_id,
                    "is_full_rerun": is_full_rerun,
                    "force_reclassify": force_reclassify,
                },
            )
            return TaskPlan(
                task_name="workers.classify_document",
                stage="classify_document",
                reason="reclassify_requested",
                kwargs={
                    "document_id": doc_id_str,
                    "run_id": run_id,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                },
            )

        logger.info(
            "Document already classified, reusing classification for this run",
            extra={"document_id": doc_id_str, "run_id": run_id},
        )
        return None

    if status == DocumentStatus.COMPLETED.value:
        if is_full_rerun or force_reclassify:
            logger.info(
                "COMPLETED document scheduled for reclassification",
                extra={
                    "document_id": doc_id_str,
                    "run_id": run_id,
                    "is_full_rerun": is_full_rerun,
                    "force_reclassify": force_reclassify,
                },
            )
            return TaskPlan(
                task_name="workers.classify_document",
                stage="classify_document",
                reason="rerun_reclassification_requested",
                kwargs={
                    "document_id": doc_id_str,
                    "run_id": run_id,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                },
            )

        logger.info(
            "Document already completed, reusing for this run",
            extra={"document_id": doc_id_str, "run_id": run_id},
        )
        return None

    logger.info(
        "Document in unsupported or terminal status for run pipeline, skipping",
        extra={
            "document_id": doc_id_str,
            "status": status,
            "run_id": run_id,
        },
    )
    return None


def _send_task(
    *,
    plan: TaskPlan,
    stage_execution_id: str,
    run_id: str,
    deal_id: str,
    tenant_id: str,
    document_id: str,
    document_version_id: str,
    orchestration_strategy: str,
) -> None:
    """
    Helper для отправки Celery task с полным context envelope.

    Обязательные поля:
    - stage_execution_id: чтобы worker мог обновить execution-запись;
    - run_id, deal_id, tenant_id: контекст сделки и запуска;
    - document_id, document_version_id: привязка к документу и версии;
    - orchestration_strategy: например V2_ONLY.
    """
    kwargs = dict(plan.kwargs)
    kwargs.update(
        {
            "stage_execution_id": stage_execution_id,
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "orchestration_strategy": orchestration_strategy,
        }
    )
    celery_app.send_task(plan.task_name, kwargs=kwargs)
    

    