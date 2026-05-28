# src/workers/run_orchestrator.py

"""
Run Orchestrator Worker.

Назначение:
- Единый центр оркестрации document-level пайплайна для конкретного Run.
- По текущему статусу документа и наличию артефактов версии решает, какую
  ИМЕННО одну следующую stage-task нужно поставить в очередь.
- Не вызывает downstream-воркеры напрямую и не полагается на chaining внутри воркеров.
  Stage-воркеры после фиксации результата могут только повторно будить оркестратор
  с тем же run_id.

Архитектурный инвариант:
- Этот orchestrator работает только в post-selection фазе.
- К моменту запуска Run у сделки уже должны быть завершены:
  1) document language discovery;
  2) aggregation в Deal.languages;
  3) выбор Deal.primary_language пользователем (если он required).
- Поэтому run_orchestrator не должен инициировать deal-level language discovery,
  не должен строить UI-waiting flow вокруг LANGUAGE_SELECTION_REQUIRED
  и не должен считаться источником истины для выбора языка сделки.

Роль build_primary_language_source в этой модели:
- Это stage-worker построения primary source для УЖЕ выбранного target_language.
- Он получает target_language из Deal.primary_language.
- В нормальном happy-path run flow он не используется как fallback-механизм
  language discovery / language selection.
- Если target language отсутствует к моменту orchestration, это считается
  нарушением pre-run контракта, а не штатным сценарием document pipeline.

Актуальная последовательность стадий:
- PENDING
    -> workers.convert_to_pdf
       (для конвертируемых типов, если ещё нет converted_pdf_ref)
    -> workers.build_primary_language_source
       (только при уже выбранном Deal.primary_language)
- PRIMARY_READY
    -> workers.extract_document
- EXTRACTED
    -> pii.sanitize_document
- SANITIZED
    -> workers.build_structure
- STRUCTURED
    -> workers.build_chunks
- CHUNKED
    -> workers.classify_document
- CLASSIFIED
    -> reuse classification
    -> либо workers.classify_document при reclassify strategy
    -> либо workers.classify_document_segments для multi-document,
       если segment-level классификация ещё не завершена
- COMPLETED
    -> reuse
    -> либо workers.classify_document при explicit rerun / reclassification

Ключевой принцип orchestration:
- Каждый stage-worker отвечает только за свою стадию и за фиксацию её результата.
- Только run_orchestrator решает, что запускать дальше.
- На один проход orchestrator для одного документа ставится не более одной
  следующей стадии.
- Решение принимается по status + readiness артефактов версии.
- Отсутствие необходимых артефактов трактуется как "ждём commit предыдущей стадии",
  а не как повод перескочить дальше.

Execution model:
- Для каждой постановки stage-task создаётся execution-запись
  в document_stage_executions.
- Активный execution (planned / dispatched / started) блокирует
  повторное планирование той же стадии для той же версии документа.
- Это делает orchestration re-entrant и защищает от duplicate scheduling
  при повторных пробуждениях orchestrator.

Run lifecycle semantics:
- При первом входе Run переводится из PENDING в RUNNING.
- Повторный вход для RUNNING допустим и используется как штатный re-entry механизм.
- Для terminal statuses (COMPLETED / FAILED / CANCELLED) orchestration не выполняется.
- После прохода orchestrator может запускать maybe_start_run_checks(),
  но только если выполнен пред-гейт готовности, включая segment-level readiness
  для multi-document кейсов.

Границы ответственности:
- Pre-run flow отвечает за:
  - import completion;
  - language discovery;
  - deal language aggregation;
  - выбор primary language;
  - run gating до выполнения этих условий.
- Этот файл отвечает только за post-run-start document pipeline orchestration.

Важное правило работы с ORM (snapshot architecture):
- SQLAlchemy asyncpg не допускает синхронный lazy reload атрибутов ORM-объектов
  после await-границы (MissingGreenlet).
- Кроме того, session.rollback() (даже внутри savepoint-recovery) помечает все
  ORM-объекты сессии как expired, после чего любое обращение к атрибуту
  провоцирует lazy reload.
- Поэтому orchestration-слой работает по принципу:
  1) READ PHASE — загрузить ORM-объекты (Run, Deal, Documents, Version);
  2) SNAPSHOT — немедленно снять все нужные поля в snapshot/dataclass/примитивы;
  3) DECISION PHASE — строить планы только на snapshot-данных;
  4) WRITE PHASE — создавать execution / dispatch;
  5) POST PHASE — checks gate и maybe_start_run_checks только на snapshot-данных.
- Живые ORM-объекты не передаются в helper-функции и не используются
  после первого await.
- Shared snapshot-контракты для pipeline/orchestration слоя живут в
  core.pipeline_snapshots и переиспользуются всеми orchestration/worker файлами.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStatus, RunStatus
from core.logging import get_logger
from core.pipeline_snapshots import (
    DocumentSnapshot,
    RunSnapshot,
    VersionSnapshot,
    snapshot_document,
    snapshot_run,
    snapshot_version,
)
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository
from db.repositories.document_version_repo import DocumentVersionRepository
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


# ─── TaskPlan ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class TaskPlan:
    task_name: str
    kwargs: dict[str, Any]
    reason: str
    stage: str


# ─── Segment helpers ──────────────────────────────────────────────────────────


def _is_multi_document_snapshot(snap: VersionSnapshot) -> bool:
    """Multi-document критерий по snapshot: segments_count > 1."""
    return bool(snap.segments_count and snap.segments_count > 1)


async def _count_relevant_segments(
    seg_repo: DocumentSegmentRepository,
    version_id: uuid.UUID,
) -> int:
    """
    Считает сегменты версии, которые реально участвуют в segment-level пайплайне.

    Здесь считаем релевантными сегменты, у которых есть segment_id.
    Если позже появится явный флаг "is_logical_document", критерий лучше перенести сюда.
    """
    return await seg_repo.count_by_version_and_has_segment_id(version_id)


async def _count_unclassified_segments(
    seg_repo: DocumentSegmentRepository,
    version_id: uuid.UUID,
) -> int:
    """
    Считает релевантные сегменты версии, для которых segment-level классификация ещё не завершена.

    Критерий "классифицирован" сознательно мягкий: достаточно наличия segment_doc_type
    или segment_classification_level. Этого хватает, чтобы checks могли выбрать правильный doc_type.
    """
    return await seg_repo.count_unclassified_for_version(version_id)


async def _are_all_segments_classified(
    seg_repo: DocumentSegmentRepository,
    snap: VersionSnapshot,
) -> bool:
    """
    Readiness-предикат для segment-level классификации.

    - для single-document всегда False (segment path не нужен);
    - для multi-document возвращает True только если:
      1) есть хотя бы один релевантный сегмент;
      2) для всех релевантных сегментов заполнен segment-level результат.
    """
    if not _is_multi_document_snapshot(snap):
        return False

    total = await _count_relevant_segments(seg_repo, snap.version_id)
    if total == 0:
        return False

    unclassified = await _count_unclassified_segments(seg_repo, snap.version_id)
    return unclassified == 0


async def _can_start_checks_for_run(
    run_snap: RunSnapshot,
    doc_snaps: list[DocumentSnapshot],
    ver_repo: DocumentVersionRepository,
    seg_repo: DocumentSegmentRepository,
) -> bool:
    """
    Пред-гейт для maybe_start_run_checks.

    Важно:
    - orchestration helper работает только с snapshot/примитивами, а не с живыми ORM;
    - это защищает от MissingGreenlet после длинной await-цепочки
      и после savepoint rollback path в create_planned_or_none_on_conflict.

    Логика:
    - для single-document документов: условий дополнительных нет;
    - для multi-document документов: хотя бы один документ run'a с сегментами
      ещё не имеет завершённой segment-level классификации — checks не запускаем.
    """
    for doc_snap in doc_snaps:
        version = await ver_repo.get_latest(doc_snap.document_id)
        if version is None:
            continue

        # Снимаем snapshot сразу — дальше segment-запросы через await
        snap = snapshot_version(version)

        if _is_multi_document_snapshot(snap):
            all_segments_classified = await _are_all_segments_classified(seg_repo, snap)
            if not all_segments_classified:
                logger.info(
                    "Run checks postponed: multi-document has unclassified segments",
                    extra={
                        "run_id": run_snap.run_id_str,
                        "document_id": doc_snap.document_id_str,
                        "document_version_id": snap.version_id_str,
                        "segments_count": snap.segments_count,
                    },
                )
                return False

    return True


# ─── Celery task entrypoint ───────────────────────────────────────────────────


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


# ─── Tenant resolver ──────────────────────────────────────────────────────────


async def _resolve_tenant_id(
    tenant_id: str | None,
    deal_uuid: uuid.UUID,
    db: AsyncSession,
) -> str:
    """
    Резолвит tenant_id для оркестратора.
    Приоритет:
    1) явный tenant_id из kwargs (не None, не нулевой UUID);
    2) tenant_id из deals (явный DB-запрос, не lazy-load);
    3) deal_id как surrogate — допустимо только в dev/single-tenant окружении,
       когда deals.tenant_id = NULL или нулевой UUID.
    """
    if tenant_id:
        return tenant_id

    deal_repo = DealRepository(db)
    deal_obj = await deal_repo.get_by_id(deal_uuid)
    if deal_obj is not None and deal_obj.tenant_id:
        resolved = str(deal_obj.tenant_id)
        logger.info(
            "tenant_id resolved from deal",
            extra={"deal_id": str(deal_uuid), "tenant_id": resolved},
        )
        return resolved

    surrogate = str(deal_uuid)
    logger.warning(
        "tenant_id not resolvable, using deal_id as surrogate tenant",
        extra={"deal_id": surrogate},
    )
    return surrogate


# ─── Async core ───────────────────────────────────────────────────────────────


async def _start_run_pipeline_async(
    run_id: str,
    deal_id: str | None,
    tenant_id: str | None,
    force_reclassify: bool,
    db: AsyncSession,
) -> dict:
    """
    Async-ядро оркестрации Run.

    Архитектура read / snapshot / decision / write / post:
    - READ:     загружаем ORM-объекты (Run, Deal, Documents);
    - SNAPSHOT: немедленно снимаем snapshots в dataclass/примитивы;
    - DECISION: строим TaskPlan для каждого документа по snapshot-данным;
    - WRITE:    создаём execution-записи и dispatch Celery tasks;
    - POST:     проверяем segment readiness и вызываем maybe_start_run_checks.

    Правила:
    - на один проход оркестратора для одного документа ставим не более ОДНОЙ
      следующей стадии;
    - решение принимается по status + наличию артефактов версии;
    - RUNNING run допускает повторный вход (re-entry) оркестратора;
    - после snapshot-фазы живые ORM-объекты не используются;
    - helper-функции принимают только snapshots / примитивы, не ORM.
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
    audit_repo = AuditRepository(db)

    # ── READ + SNAPSHOT: Run ──────────────────────────────────────────────────

    run_uuid = uuid.UUID(run_id)
    run_obj = await run_repo.get_by_id(run_uuid)

    if run_obj is None:
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
        logger.error("Run not found for orchestrator", extra={"run_id": run_id})
        return {
            "run_id": run_id,
            "deal_id": None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    # Снимаем snapshot сразу после загрузки ORM-объекта Run.
    # Дальше orchestration работает только с run_snap, а не с run_obj.
    run_snap = snapshot_run(run_obj)
    current_status = run_snap.status

    # ── Run lifecycle gate ────────────────────────────────────────────────────

    if current_status == RunStatus.PENDING.value:
        started = await run_repo.try_start_run(run_uuid)
        if not started:
            run_obj = await run_repo.get_by_id(run_uuid)
            if run_obj is not None:
                run_snap = snapshot_run(run_obj)
                current_status = run_snap.status
            else:
                current_status = None

            if current_status != RunStatus.RUNNING.value:
                logger.info(
                    "Run pipeline cannot be started from non-pending state, skipping orchestration",
                    extra={"run_id": run_id, "status": current_status},
                )
                return {
                    "run_id": run_id,
                    "deal_id": run_snap.deal_id_str,
                    "tenant_id": tenant_id,
                    "documents_total": 0,
                    "tasks_scheduled": 0,
                    "documents_with_plan": 0,
                }
            logger.info(
                "Run transitioned to RUNNING concurrently, continuing orchestration",
                extra={"run_id": run_id},
            )
        else:
            try:
                await audit_repo.log(
                    tenant_id=uuid.UUID(tenant_id) if tenant_id else uuid.UUID(int=0),
                    deal_id=run_snap.deal_id,
                    action="ANALYSIS_STARTED",
                    actor="system",
                    actor_role="worker",
                    details={
                        "run_id": run_id,
                        "deal_id": run_snap.deal_id_str,
                        "pipeline_strategy": run_snap.pipeline_strategy,
                        "force_reclassify": force_reclassify,
                    },
                )
            except Exception:
                logger.warning(
                    "Failed to write audit log for ANALYSIS_STARTED",
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
            "deal_id": run_snap.deal_id_str,
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
            "deal_id": run_snap.deal_id_str,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    pipeline_strategy = run_snap.pipeline_strategy or "REUSE_STRUCTURE"
    is_full_rerun = pipeline_strategy == "FULL_RERUN"

    logger.info(
        "Resolved run pipeline strategy",
        extra={
            "run_id": run_id,
            "pipeline_strategy": pipeline_strategy,
            "force_reclassify": force_reclassify,
        },
    )

    # ── Resolve deal ──────────────────────────────────────────────────────────

    deal_uuid = run_snap.deal_id if run_snap.deal_id else (uuid.UUID(deal_id) if deal_id else None)
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

    tenant_id_str = await _resolve_tenant_id(
        tenant_id=tenant_id,
        deal_uuid=deal_uuid,
        db=db,
    )

    # ── READ + SNAPSHOT: Deal ─────────────────────────────────────────────────

    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_uuid)

    if deal is None:
        await run_repo.update_status(
            run_uuid,
            RunStatus.FAILED.value,
            error_details={
                "stage": "orchestrator",
                "type": "config_error",
                "reason": "deal_not_found",
                "message": f"Deal {deal_id_str} not found for run {run_id}",
            },
        )
        logger.error(
            "Deal not found for run",
            extra={"run_id": run_id, "deal_id": deal_id_str},
        )
        return {
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    # Снимаем нужные deal-поля в примитивы сразу после загрузки ORM-объекта.
    deal_primary_language: str | None = getattr(deal, "primary_language", None)
    deal_language_discovery_status: str | None = getattr(deal, "language_discovery_status", None)
    deal_languages: list[str] | None = getattr(deal, "languages", None)

    if not deal_primary_language:
        logger.warning(
            "Run pipeline blocked: deal.primary_language is not selected",
            extra={
                "run_id": run_id,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "language_discovery_status": deal_language_discovery_status,
                "deal_languages": deal_languages,
            },
        )
        return {
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
            "blocked_reason": "primary_language_not_selected",
        }

    # ── READ + SNAPSHOT: Documents ────────────────────────────────────────────

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

    # Снимаем snapshots документов сразу после batch-read.
    # Дальше orchestration работает только с doc_snaps, а не с live ORM Document.
    doc_snaps: list[DocumentSnapshot] = [snapshot_document(doc) for doc in docs]
    documents_total = len(doc_snaps)

    # ── DECISION + WRITE: per-document loop ───────────────────────────────────

    tasks_scheduled = 0
    documents_with_plan = 0
    seg_repo = DocumentSegmentRepository(db)

    for doc_snap in doc_snaps:
        doc_id: uuid.UUID = doc_snap.document_id
        doc_id_str = doc_snap.document_id_str
        status: str = doc_snap.status

        logger.info(
            "Evaluating document for run pipeline",
            extra={
                "run_id": run_id,
                "document_id": doc_id_str,
                "status": status,
                "doc_type": doc_snap.doc_type,
                "classification_level": doc_snap.classification_level,
                "deal_primary_language": deal_primary_language,
            },
        )

        version = await ver_repo.get_latest(doc_id)

        # ── КРИТИЧЕСКИ ВАЖНО ──────────────────────────────────────────────────
        # Снимаем snapshot СРАЗУ после загрузки version, до любого следующего
        # await-вызова. Это предотвращает MissingGreenlet: после await SQLAlchemy
        # может пометить ORM-объект expired, и при следующем обращении к атрибуту
        # попытается сделать синхронный lazy reload — что в asyncpg запрещено.
        # ─────────────────────────────────────────────────────────────────────
        ver_snap: VersionSnapshot | None = (
            snapshot_version(version) if version is not None else None
        )

        plan = await _build_document_task_plan(
            doc_id_str=doc_id_str,
            snap=ver_snap,
            status=status,
            run_id=run_id,
            deal_id_str=deal_id_str,
            tenant_id_str=tenant_id_str,
            is_full_rerun=is_full_rerun,
            force_reclassify=force_reclassify,
            seg_repo=seg_repo,
            deal_primary_language=deal_primary_language,
        )

        if plan is None:
            logger.info(
                "No next task scheduled for document",
                extra={
                    "run_id": run_id,
                    "document_id": doc_id_str,
                    "status": status,
                },
            )
            continue

        if ver_snap is None:
            logger.warning(
                "Task plan produced for document without version, skipping execution scheduling",
                extra={"run_id": run_id, "document_id": doc_id_str, "status": status},
            )
            continue

        orchestration_strategy = ORCHESTRATION_STRATEGY_V2_ONLY

        execution = await dse_repo.create_planned_or_none_on_conflict(
            run_id=run_uuid,
            document_id=doc_id,
            document_version_id=ver_snap.version_id,
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
                    "document_version_id": ver_snap.version_id_str,
                    "status": status,
                    "task_name": plan.task_name,
                    "stage": plan.stage,
                    "reason": plan.reason,
                    "orchestration_strategy": orchestration_strategy,
                },
            )
            continue

        # Снимаем execution.id до следующего await
        execution_id: uuid.UUID = execution.id
        execution_id_str = str(execution_id)

        logger.info(
            "Scheduling next document stage",
            extra={
                "run_id": run_id,
                "document_id": doc_id_str,
                "document_version_id": ver_snap.version_id_str,
                "status": status,
                "task_name": plan.task_name,
                "stage": plan.stage,
                "reason": plan.reason,
                "orchestration_strategy": orchestration_strategy,
                "stage_execution_id": execution_id_str,
            },
        )

        celery_task_id = _send_task(
            plan=plan,
            stage_execution_id=execution_id_str,
            run_id=run_id,
            deal_id=deal_id_str,
            tenant_id=tenant_id_str,
            document_id=doc_id_str,
            document_version_id=ver_snap.version_id_str,
            orchestration_strategy=orchestration_strategy,
        )

        await dse_repo.mark_dispatched(execution_id, celery_task_id=celery_task_id)

        tasks_scheduled += 1
        documents_with_plan += 1

    logger.info(
        "Run pipeline documents evaluation complete",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": documents_total,
            "tasks_scheduled": tasks_scheduled,
            "documents_with_plan": documents_with_plan,
        },
    )

    # ── POST PHASE: segment readiness gate + maybe_start_run_checks ───────────

    seg_repo_for_checks = DocumentSegmentRepository(db)
    can_start_checks = await _can_start_checks_for_run(
        run_snap=run_snap,
        doc_snaps=doc_snaps,
        ver_repo=ver_repo,
        seg_repo=seg_repo_for_checks,
    )
    if not can_start_checks:
        logger.info(
            "Run checks auto-start postponed due to incomplete segment-level classification",
            extra={"run_id": run_id},
        )
    else:
        await maybe_start_run_checks(db=db, run_id=run_snap.run_id)

    logger.info(
        "Run pipeline scheduling complete",
        extra={
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": documents_total,
            "tasks_scheduled": tasks_scheduled,
            "documents_with_plan": documents_with_plan,
        },
    )

    return {
        "run_id": run_id,
        "deal_id": deal_id_str,
        "tenant_id": tenant_id_str,
        "documents_total": documents_total,
        "tasks_scheduled": tasks_scheduled,
        "documents_with_plan": documents_with_plan,
    }


# ─── Stage mapping ────────────────────────────────────────────────────────────


def _target_status_for_stage(stage: str) -> str:
    """
    Map internal stage name to *intended* DocumentStatus
    on successful completion of this stage.
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
    if stage in {"classify_document", "classify_document_segments"}:
        return DocumentStatus.CLASSIFIED.value
    return stage


# ─── Task plan builder ────────────────────────────────────────────────────────


async def _build_document_task_plan(
    *,
    doc_id_str: str,
    snap: VersionSnapshot | None,
    status: str,
    run_id: str,
    deal_id_str: str,
    tenant_id_str: str,
    is_full_rerun: bool,
    force_reclassify: bool,
    seg_repo: DocumentSegmentRepository,
    deal_primary_language: str | None,
) -> TaskPlan | None:
    """
    Строит план следующей document-level стадии для одного документа в рамках Run.

    Принимает VersionSnapshot вместо ORM-объекта, чтобы гарантировать
    отсутствие обращений к expired ORM-атрибутам через await-границу.
    """
    if not deal_primary_language:
        logger.error(
            "Invariant violation: _build_document_task_plan called without deal_primary_language",
            extra={
                "document_id": doc_id_str,
                "run_id": run_id,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "status": status,
            },
        )
        raise ValueError("deal_primary_language must be selected before building run task plan")

    # ── PENDING ───────────────────────────────────────────────────────────────

    if status == DocumentStatus.PENDING.value:
        if snap is None:
            logger.warning(
                "Document has PENDING status but no version, skipping next stage",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        if snap.origin_filetype in CONVERTIBLE_TO_PDF and not snap.converted_pdf_ref:
            logger.info(
                "PENDING document requires office-to-PDF conversion before primary source build",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "origin_filetype": snap.origin_filetype,
                    "has_converted_pdf": bool(snap.converted_pdf_ref),
                    "original_ref": snap.original_ref,
                    "run_id": run_id,
                },
            )
            return TaskPlan(
                task_name="workers.convert_to_pdf",
                stage="convert_to_pdf",
                reason="convertible_type_without_converted_pdf",
                kwargs={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                    "run_id": run_id,
                },
            )

        source_kind = "converted_pdf_ref" if snap.converted_pdf_ref else "original_ref"
        logger.info(
            "PENDING document ready for primary source build with preselected deal primary language",
            extra={
                "document_id": doc_id_str,
                "document_version_id": snap.version_id_str,
                "origin_filetype": snap.origin_filetype,
                "has_converted_pdf": bool(snap.converted_pdf_ref),
                "source_kind": source_kind,
                "run_id": run_id,
                "target_language": deal_primary_language,
            },
        )
        return TaskPlan(
            task_name="workers.build_primary_language_source",
            stage="build_primary_language_source",
            reason="pending_document_has_pdf_source_and_deal_primary_language_selected",
            kwargs={
                "document_version_id": snap.version_id_str,
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
                "target_language": deal_primary_language,
            },
        )

    # ── PRIMARY_READY ─────────────────────────────────────────────────────────

    if status == DocumentStatus.PRIMARY_READY.value:
        if snap is None:
            logger.warning(
                "PRIMARY_READY document without version, skipping extract",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        if not snap.primary_source_ref:
            logger.warning(
                "PRIMARY_READY document without primary_source_ref, "
                "waiting for primary source commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "PRIMARY_READY document ready for extract",
            extra={
                "document_id": doc_id_str,
                "document_version_id": snap.version_id_str,
                "primary_source_ref": snap.primary_source_ref,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.extract_document",
            stage="extract_document",
            reason="primary_source_is_ready",
            kwargs={
                "document_version_id": snap.version_id_str,
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    # ── EXTRACTED ─────────────────────────────────────────────────────────────

    if status == DocumentStatus.EXTRACTED.value:
        if snap is None:
            logger.warning(
                "EXTRACTED document without version, skipping pii",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        if not snap.layout_primary_ref:
            logger.warning(
                "EXTRACTED document without layout_primary_ref, waiting for extract commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "EXTRACTED document ready for PII sanitization",
            extra={
                "document_id": doc_id_str,
                "document_version_id": snap.version_id_str,
                "layout_primary_ref": snap.layout_primary_ref,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="pii.sanitize_document",
            stage="sanitize_document",
            reason="layout_primary_ready",
            kwargs={
                "document_version_id": snap.version_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    # ── SANITIZED ─────────────────────────────────────────────────────────────

    if status == DocumentStatus.SANITIZED.value:
        if snap is None:
            logger.warning(
                "SANITIZED document without version, skipping structure",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        if not snap.layout_primary_sanitized_ref:
            logger.warning(
                "SANITIZED document without layout_primary_sanitized_ref, "
                "waiting for PII commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "SANITIZED document ready for structure build",
            extra={
                "document_id": doc_id_str,
                "document_version_id": snap.version_id_str,
                "layout_primary_sanitized_ref": snap.layout_primary_sanitized_ref,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.build_structure",
            stage="build_structure",
            reason="sanitized_layout_ready",
            kwargs={
                "document_version_id": snap.version_id_str,
                "run_id": run_id,
            },
        )

    # ── STRUCTURED ────────────────────────────────────────────────────────────

    if status == DocumentStatus.STRUCTURED.value:
        if snap is None:
            logger.warning(
                "STRUCTURED document without version, skipping chunks",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        if not snap.file_graph_ref:
            logger.warning(
                "STRUCTURED document without file_graph_ref in V2_ONLY, "
                "waiting for structure v2 commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "run_id": run_id,
                },
            )
            return None

        if not snap.segments_count or snap.segments_count <= 0:
            logger.warning(
                "STRUCTURED document without segments_count in V2_ONLY, "
                "waiting for structure v2 commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "segments_count": snap.segments_count,
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "STRUCTURED document ready for chunk build (v2 structure artifacts present)",
            extra={
                "document_id": doc_id_str,
                "document_version_id": snap.version_id_str,
                "file_graph_ref": snap.file_graph_ref,
                "segments_count": snap.segments_count,
                "run_id": run_id,
            },
        )
        return TaskPlan(
            task_name="workers.build_chunks",
            stage="build_chunks",
            reason="structure_v2_ready",
            kwargs={
                "document_version_id": snap.version_id_str,
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    # ── CHUNKED ───────────────────────────────────────────────────────────────

    if status == DocumentStatus.CHUNKED.value:
        if snap is None:
            logger.warning(
                "CHUNKED document without version, skipping classify",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

        if not snap.chunks_manifest_v2_ref:
            logger.warning(
                "CHUNKED document without chunks_manifest_v2_ref in V2_ONLY, "
                "waiting for chunk v2 commit",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "run_id": run_id,
                },
            )
            return None

        summary = await seg_repo.get_chunk_refs_summary(snap.version_id)
        total_segments = summary["total_segments"]
        segments_with_chunks = summary["segments_with_chunks"]

        if total_segments <= 0:
            logger.warning(
                "CHUNKED document without persisted segments in V2_ONLY, "
                "cannot continue to classification",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "chunks_manifest_v2_ref": snap.chunks_manifest_v2_ref,
                    "run_id": run_id,
                },
            )
            return None

        if segments_with_chunks != total_segments:
            logger.warning(
                "CHUNKED document has incomplete segment chunk refs in V2_ONLY, "
                "waiting for full chunk contract",
                extra={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "chunks_manifest_v2_ref": snap.chunks_manifest_v2_ref,
                    "total_segments": total_segments,
                    "segments_with_chunks": segments_with_chunks,
                    "run_id": run_id,
                },
            )
            return None

        logger.info(
            "CHUNKED document ready for classification " "(v2 manifest + full segment chunk refs)",
            extra={
                "document_id": doc_id_str,
                "document_version_id": snap.version_id_str,
                "chunks_manifest_v2_ref": snap.chunks_manifest_v2_ref,
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

    # ── CLASSIFIED ────────────────────────────────────────────────────────────

    if status == DocumentStatus.CLASSIFIED.value:
        if snap is None:
            logger.warning(
                "CLASSIFIED document without version, nothing to plan",
                extra={"document_id": doc_id_str, "run_id": run_id},
            )
            return None

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

        if _is_multi_document_snapshot(snap):
            all_segments_classified = await _are_all_segments_classified(seg_repo, snap)
            if not all_segments_classified:
                logger.info(
                    "CLASSIFIED multi-document requires segment-level classification",
                    extra={
                        "document_id": doc_id_str,
                        "document_version_id": snap.version_id_str,
                        "segments_count": snap.segments_count,
                        "run_id": run_id,
                    },
                )
                return TaskPlan(
                    task_name="workers.classify_document_segments",
                    stage="classify_document_segments",
                    reason="multi_document_requires_segment_level_classification",
                    kwargs={
                        "document_id": doc_id_str,
                        "run_id": run_id,
                        "deal_id": deal_id_str,
                        "tenant_id": tenant_id_str,
                    },
                )

        logger.info(
            "Document already classified, reusing classification for this run",
            extra={
                "document_id": doc_id_str,
                "run_id": run_id,
                "segments_count": snap.segments_count,
            },
        )
        return None

    # ── COMPLETED ─────────────────────────────────────────────────────────────

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

    # ── Unknown status ────────────────────────────────────────────────────────

    logger.info(
        "Document in unsupported or terminal status for run pipeline, skipping",
        extra={
            "document_id": doc_id_str,
            "status": status,
            "run_id": run_id,
        },
    )
    return None


# ─── Celery task sender ───────────────────────────────────────────────────────


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
) -> str:
    """Поставить stage-task в Celery. Возвращает celery task id."""
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
    result = celery_app.send_task(plan.task_name, kwargs=kwargs)
    return result.id
