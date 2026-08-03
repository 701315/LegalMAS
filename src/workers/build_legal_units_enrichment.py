# src/workers/build_legal_units_enrichment.py

"""
Воркер семантического обогащения правовых единиц.

Формальная стадия пайплайна: семантическое обогащение базового набора legal units.

Позиция в пайплайне:
    build_chunks → classify_document → [classify_document_segments]
    → build_legal_units_enrichment  ← этот воркер
    → run_deal_checks / YAML-анализ рисков

Контракт:
- Читает legal_units_v1.json (базовый набор) для каждого сегмента из MinIO.
- Обогащает правовые единицы каждого подходящего сегмента через LLM.
- Записывает sidecar-файл legal_units_enrichment_v1.json для каждого сегмента.
- Обновляет segment_meta["legal_units_enrichment_ref"].
- Всегда завершается DocumentStatus.ENRICHED вне зависимости от результата LLM.
- Терминальные исходы:
    completed   — все кандидат-сегменты успешно обогащены
    degraded    — частичный успех (часть обогащена, часть провалилась/таймаут)
    skipped     — нет кандидатов или функция отключена
    timed_out   — бюджет документа исчерпан, ни один сегмент не обогащён
    unavailable — LLM недоступен в момент старта стадии
- После терминального исхода: перезапускает run_orchestrator для оценки gate проверок.

Изоляция отказов:
- Таймаут сегмента → warning + continue (не блокирует остальные сегменты)
- Исчерпание бюджета документа → остановка обогащения, переход к commit
- LLM недоступен → немедленный терминальный исход UNAVAILABLE
- Некорректный payload legal_units → warning + пропуск сегмента
- Ошибка commit → PermanentError (будет retry)

Очередь: heavy_llm
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import (
    DocumentStageExecutionStatus,
    DocumentStatus,
    RunStatus,
    SemanticEnrichmentStageOutcome,
)
from core.semantic_enrichment_degradation import derive_semantic_enrichment_degradation
from core.exceptions import PermanentError
from core.logging import get_logger
from core.stage_trace import build_stage_trace_fragment
from db.repositories import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_orchestrator_trigger import retrigger_run_pipeline
from services.structure.legal_unit_models import LegalUnitsSnapshot
from services.structure.semantic_enrichment import (
    enrich_legal_units_async,
    is_semantic_enrichment_llm_available,
    make_policy_from_settings,
)
from services.structure.semantic_enrichment._budget import (
    build_document_enrichment_deadline,
    is_enrichment_budget_exhausted,
    resolve_segment_enrichment_timeout,
)
from services.structure.semantic_enrichment._types import (
    LegalUnitEnrichment,
    LegalUnitsEnrichmentResult,
    SemanticEnrichmentPolicy,
)
from storage.artifact_store import ArtifactPath, ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_legal_units_enrichment",
    track_job=False,
    queue="heavy_llm_enrichment",
)
def build_legal_units_enrichment(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Синхронная точка входа Celery для формальной стадии семантического обогащения.

    Архитектура разбита на три фазы, чтобы не держать DB-транзакцию открытой
    во время долгой LLM-работы:

    Фаза 1 (preflight) — короткая DB-транзакция:
      - resolve tenant, stale guards, загрузить сегменты, mark_started, commit.

    Фаза 2 (LLM) — без открытой DB-транзакции:
      - enrich legal units через LLM, записать sidecar в S3.
      - Результаты накапливаются в памяти как {segment_id: sidecar_ref}.

    Фаза 3 (finalize) — короткая DB-транзакция:
      - обновить segment_meta, Document.status=ENRICHED, mark_succeeded, commit.

    После завершения перезапускает run_orchestrator, чтобы gate проверок
    мог оценить готовность документа.
    """
    _ = self

    # ── Фаза 1: preflight — короткая DB-транзакция ────────────────────────────
    async def _preflight() -> dict[str, Any]:
        async with db_uow() as uow:
            resolved_tenant_id = await resolve_artifact_tenant_id(
                session=uow.session,
                deal_id=deal_id,
                document_id=document_id,
                payload_tenant_id=tenant_id,
            )
            return await _enrichment_preflight(
                document_version_id=document_version_id,
                document_id=document_id,
                deal_id=deal_id,
                tenant_id=resolved_tenant_id,
                db=uow.session,
                run_id=run_id,
                stage_execution_id=stage_execution_id,
            )

    preflight_result = run_async(_preflight())

    # Если preflight вернул stale replay или early terminal — сразу выходим.
    if preflight_result.get("skip_llm"):
        result = preflight_result.get("early_result", {})
        if run_id and result.get("committed"):
            retrigger_run_pipeline(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=result.get("tenant_id", tenant_id),
            )
        return result

    resolved_tenant_id: str = preflight_result["tenant_id"]
    segments_snapshot: list[dict[str, Any]] = preflight_result["segments_snapshot"]
    started_monotonic: float = preflight_result["started_monotonic"]

    # ── Фаза 2: LLM-работа — БЕЗ открытой DB-транзакции ─────────────────────
    async def _llm_phase() -> dict[str, Any]:
        return await _enrichment_llm_phase(
            document_version_id=document_version_id,
            document_id=document_id,
            deal_id=deal_id,
            tenant_id=resolved_tenant_id,
            run_id=run_id,
            segments_snapshot=segments_snapshot,
            started_monotonic=started_monotonic,
            stage_execution_id=stage_execution_id,
        )

    llm_result = run_async(_llm_phase())

    # ── Фаза 3: finalize — короткая DB-транзакция ────────────────────────────
    async def _finalize() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _enrichment_finalize(
                document_version_id=document_version_id,
                document_id=document_id,
                deal_id=deal_id,
                tenant_id=resolved_tenant_id,
                db=uow.session,
                run_id=run_id,
                stage_execution_id=stage_execution_id,
                llm_result=llm_result,
            )

    result = run_async(_finalize())

    if run_id and result.get("committed"):
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", resolved_tenant_id),
        )

    return result


def _build_stale_replay_result(
    *,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    reason: str,
    retrigger_orchestrator: bool,
) -> dict[str, Any]:
    """
    Стандартизованный результат stale replay short-circuit.

    Параметры:
    - reason: машинный код причины skip (для логирования и диагностики).
    - retrigger_orchestrator: True если sync wrapper должен разбудить orchestrator.
      Используется как значение поля "committed" в результате, чтобы
      build_legal_units_enrichment() автоматически вызвал retrigger_run_pipeline().

    Для непрофессионального программиста:
    Если задача оказалась "устаревшей" (enrichment уже был выполнен ранее),
    мы не делаем тяжёлую LLM-работу повторно.
    Но если pipeline ещё не завершился — разбудим оркестратор,
    чтобы он проверил, что делать дальше.
    """
    _stale_trace = build_stage_trace_fragment(
        strategy="semantic_enrichment_llm",
        input_summary={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "stale_replay": True,
        },
        output_summary={
            "terminal_outcome": SemanticEnrichmentStageOutcome.SKIPPED.value,
            "segments_total": 0,
            "segments_with_legal_units_ref": 0,
            "segments_enriched": 0,
            "segments_timed_out": 0,
            "segments_failed": 0,
            "segments_skipped_budget": 0,
            "budget_exhausted": False,
        },
        warnings=["stale_replay"],
        artifact_refs={},
        decision_details={
            "stale_replay": True,
            "stale_replay_reason": reason,
        },
    )

    return {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "terminal_outcome": SemanticEnrichmentStageOutcome.SKIPPED.value,
        "stale_replay": True,
        "stale_replay_reason": reason,
        "committed": retrigger_orchestrator,
        "segments_total": 0,
        "segments_with_legal_units_ref": 0,
        "segments_enriched": 0,
        "segments_timed_out": 0,
        "segments_failed": 0,
        "segments_skipped_budget": 0,
        "budget_exhausted": False,
        "stage_execution_trace_status": "skipped",
        "stage_execution_result_details": _stale_trace,
    }

async def _enrichment_preflight(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None,
    stage_execution_id: str | None,
) -> dict[str, Any]:
    """
    Фаза 1: preflight.

    Выполняется в короткой DB-транзакции.
    Задачи:
    - stale replay guard (по run / execution / document status)
    - загрузить document / version / segments из БД
    - mark_started для stage_execution
    - ранние терминальные исходы (feature disabled, LLM unavailable)
    - commit и отпустить транзакцию

    Возвращает один из двух вариантов:
    1. {"skip_llm": True, "early_result": {...}} — если нужен skip/stale
    2. {"skip_llm": False, "tenant_id": ..., "segments_snapshot": [...], "started_monotonic": ...}
       — если нужна LLM-фаза
    """
    started_monotonic = time.monotonic()

    log_base = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
    }

    logger.info("Semantic enrichment stage: starting", **log_base)

    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)
    seg_repo = DocumentSegmentRepository(db)
    dse_repo = DocumentStageExecutionRepository(db)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)

    # ── Stale replay guard ────────────────────────────────────────────────────

    _stale_run_terminal_statuses = frozenset({
        RunStatus.COMPLETED.value,
        RunStatus.COMPLETED_WITH_ERRORS.value,
        RunStatus.FAILED.value,
    })
    _stale_execution_terminal_statuses = frozenset({
        DocumentStageExecutionStatus.SUCCEEDED.value,
        DocumentStageExecutionStatus.FAILED.value,
        DocumentStageExecutionStatus.CANCELLED.value,
    })
    _stale_document_downstream_statuses = frozenset({
        DocumentStatus.ENRICHED.value,
        DocumentStatus.ANALYZING.value,
        DocumentStatus.COMPLETED.value,
    })

    current_execution = None
    if stage_execution_id:
        try:
            current_execution = await dse_repo.get_by_id(uuid.UUID(stage_execution_id))
        except Exception as exc:
            logger.warning(
                "Semantic enrichment stage: failed to load stage_execution for stale check",
                **log_base,
                error=str(exc),
            )

    current_run = None
    if run_id:
        try:
            run_repo = RunRepository(db)
            current_run = await run_repo.get_by_id(uuid.UUID(run_id))
        except Exception as exc:
            logger.warning(
                "Semantic enrichment stage: failed to load run for stale check",
                **log_base,
                error=str(exc),
            )

    # Guard 1: run уже terminal
    if current_run is not None and current_run.status in _stale_run_terminal_statuses:
        logger.warning(
            "Semantic enrichment stage: stale replay detected — run already terminal, skipping",
            **log_base,
            run_status=current_run.status,
        )
        return {
            "skip_llm": True,
            "early_result": _build_stale_replay_result(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                reason="stale_replay_run_terminal",
                retrigger_orchestrator=False,
            ),
        }

    # Guard 2: stage_execution уже terminal
    if current_execution is not None and current_execution.status in _stale_execution_terminal_statuses:
        run_not_terminal = (
            current_run is None
            or current_run.status not in _stale_run_terminal_statuses
        )
        should_retrigger = (
            current_execution.status == DocumentStageExecutionStatus.SUCCEEDED.value
            and run_not_terminal
        )
        logger.warning(
            "Semantic enrichment stage: stale replay detected — stage execution already terminal, skipping",
            **log_base,
            execution_status=current_execution.status,
        )
        return {
            "skip_llm": True,
            "early_result": _build_stale_replay_result(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                reason=f"stale_replay_execution_{current_execution.status}",
                retrigger_orchestrator=should_retrigger,
            ),
        }

    version = await ver_repo.get_by_id(version_uuid)
    if version is None:
        raise PermanentError(
            f"DocumentVersion {document_version_id} not found for enrichment stage"
        )

    document = await doc_repo.get_by_id(doc_uuid)
    if document is None:
        raise PermanentError(
            f"Document {document_id} not found for enrichment stage"
        )

    # Guard 3: документ уже downstream от enrichment
    if document.status in _stale_document_downstream_statuses:
        run_not_terminal = (
            current_run is None
            or current_run.status not in _stale_run_terminal_statuses
        )
        logger.warning(
            "Semantic enrichment stage: stale replay detected — document already downstream of enrichment, skipping",
            **log_base,
            document_status=document.status,
        )
        return {
            "skip_llm": True,
            "early_result": _build_stale_replay_result(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                reason="stale_replay_document_already_enriched",
                retrigger_orchestrator=run_not_terminal,
            ),
        }

    segments = await seg_repo.list_by_version(version_uuid)

    # ── mark_started ──────────────────────────────────────────────────────────
    if stage_execution_id and current_execution is not None:
        if current_execution.status not in _stale_execution_terminal_statuses:
            started_execution = await dse_repo.mark_started(uuid.UUID(stage_execution_id))
            if started_execution is None:
                raise PermanentError(
                    f"Stage execution {stage_execution_id} not found while marking STARTED "
                    f"for document {document_id}"
                )
    elif stage_execution_id and current_execution is None:
        raise PermanentError(
            f"Stage execution {stage_execution_id} is missing before enrichment start "
            f"for document {document_id}"
        )

    # ── Ранние терминальные исходы ────────────────────────────────────────────
    if not settings.SEMANTIC_ENRICHMENT_ENABLED:
        logger.info(
            "Semantic enrichment stage: feature disabled, terminal outcome=skipped",
            **log_base,
        )
        early_result = await _finalize_enrichment_stage(
            db=db,
            doc_repo=doc_repo,
            dse_repo=dse_repo,
            audit_repo=AuditRepository(db),
            doc_uuid=doc_uuid,
            stage_execution_id=stage_execution_id,
            tenant_id=tenant_id,
            run_id=run_id,
            outcome=SemanticEnrichmentStageOutcome.SKIPPED,
            segments_total=len(segments),
            segments_with_legal_units_ref=0,
            segments_enriched=0,
            segments_timed_out=0,
            segments_failed=0,
            segments_skipped_budget=0,
            budget_exhausted=False,
            log_base=log_base,
        )
        return {"skip_llm": True, "early_result": early_result}

    llm_available = is_semantic_enrichment_llm_available()
    if not llm_available:
        logger.warning(
            "Semantic enrichment stage: LLM unavailable, terminal outcome=unavailable",
            **log_base,
        )
        early_result = await _finalize_enrichment_stage(
            db=db,
            doc_repo=doc_repo,
            dse_repo=dse_repo,
            audit_repo=AuditRepository(db),
            doc_uuid=doc_uuid,
            stage_execution_id=stage_execution_id,
            tenant_id=tenant_id,
            run_id=run_id,
            outcome=SemanticEnrichmentStageOutcome.UNAVAILABLE,
            segments_total=len(segments),
            segments_with_legal_units_ref=0,
            segments_enriched=0,
            segments_timed_out=0,
            segments_failed=0,
            segments_skipped_budget=0,
            budget_exhausted=False,
            log_base=log_base,
        )
        return {"skip_llm": True, "early_result": early_result}

    # ── Снимаем snapshot сегментов в примитивы — до закрытия сессии ──────────
    # После закрытия db_uow() ORM-объекты становятся expired/detached.
    # Передаём в LLM-фазу только примитивы.
    segments_snapshot: list[dict[str, Any]] = [
        {
            "segment_id": seg.segment_id,
            "segment_order": seg.segment_order,
            "is_primary": bool(getattr(seg, "is_primary", False)),
            "segment_meta": dict(seg.segment_meta or {}),
        }
        for seg in segments
    ]

    return {
        "skip_llm": False,
        "tenant_id": tenant_id,
        "segments_snapshot": segments_snapshot,
        "started_monotonic": started_monotonic,
    }


async def _enrichment_llm_phase(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    segments_snapshot: list[dict[str, Any]],
    started_monotonic: float,
    stage_execution_id: str | None = None,
) -> dict[str, Any]:
    """
    Фаза 2: долгая LLM-работа.

    Выполняется БЕЗ открытой DB-транзакции.
    Задачи:
    - enrich legal units через LLM для каждого сегмента
    - записать sidecar artifacts в S3
    - накопить в памяти {segment_id: sidecar_ref}

    Возвращает:
    {
        "enriched_refs": {segment_id: sidecar_ref},  # для finalize
        "segments_total": int,
        "segments_with_legal_units_ref": int,
        "segments_enriched": int,
        "segments_timed_out": int,
        "segments_failed": int,
        "segments_skipped_budget": int,
        "budget_exhausted": bool,
    }
    """
    log_base = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
    }

    store = ArtifactStore(settings)

    document_deadline = build_document_enrichment_deadline(
        started_monotonic=started_monotonic,
        settings=settings,
    )

    ordered_snapshots = _ordered_segments_for_enrichment_snapshots(segments_snapshot)
    enrichment_policy = make_policy_from_settings()

    segments_with_legal_units_ref = 0
    segments_enriched = 0
    segments_timed_out = 0
    segments_failed = 0
    segments_skipped_budget = 0
    budget_exhausted = False

    # {segment_id: sidecar_ref} — собираем в памяти, запишем в finalize-фазе
    enriched_refs: dict[str, str] = {}

    # ── LLM telemetry накопитель ───────────────────────────────────────────────
    # Собирает telemetry unit-level LLM вызовов внутри одного сегмента.
    # Сбрасывается после каждого сегмента.
    _segment_llm_telemetry: list[dict] = []

    def _collect_unit_llm_telemetry(telemetry: dict) -> None:
        if isinstance(telemetry, dict):
            _segment_llm_telemetry.append(telemetry)

    for seg_snap in ordered_snapshots:
        # Очищаем накопитель в начале каждого сегмента.
        # Гарантирует что telemetry от предыдущего сегмента
        # никогда не попадёт в ledger текущего.
        _segment_llm_telemetry.clear()

        segment_id: str = seg_snap["segment_id"]
        segment_meta: dict = seg_snap["segment_meta"]
        is_primary_seg: bool = seg_snap["is_primary"]

        legal_units_ref = _extract_legal_units_ref(segment_meta)

        if not legal_units_ref:
            logger.debug(
                "Semantic enrichment stage: segment has no legal_units_ref, skipping",
                **log_base,
                segment_id=segment_id,
            )
            continue

        segments_with_legal_units_ref += 1

        if is_enrichment_budget_exhausted(deadline_monotonic=document_deadline):
            budget_exhausted = True
            segments_skipped_budget += 1
            logger.info(
                "Semantic enrichment stage: document budget exhausted, skipping segment",
                **log_base,
                segment_id=segment_id,
            )
            continue

        try:
            baseline_payload = store.get_json(legal_units_ref)
            legal_units_snapshot = LegalUnitsSnapshot.from_dict(baseline_payload)
        except Exception as load_exc:
            logger.warning(
                "Semantic enrichment stage: failed to load baseline legal units, skipping segment",
                **log_base,
                segment_id=segment_id,
                error=str(load_exc),
            )
            segments_failed += 1
            continue

        if not legal_units_snapshot.units:
            logger.debug(
                "Semantic enrichment stage: segment has zero legal units, skipping",
                **log_base,
                segment_id=segment_id,
            )
            continue

        seg_timeout = resolve_segment_enrichment_timeout(
            deadline_monotonic=document_deadline,
            settings=settings,
        )

        if is_primary_seg:
            primary_min_timeout = float(
                getattr(settings, "SEMANTIC_ENRICHMENT_PRIMARY_SEGMENT_MIN_TIMEOUT_SECONDS", 600)
            )
            if seg_timeout < primary_min_timeout:
                logger.info(
                    "Semantic enrichment stage: extending timeout for primary segment",
                    **log_base,
                    segment_id=segment_id,
                    original_timeout=seg_timeout,
                    extended_timeout=primary_min_timeout,
                )
                seg_timeout = primary_min_timeout

        if seg_timeout <= 0:
            budget_exhausted = True
            segments_skipped_budget += 1
            continue

        _partial_enrichments: list[LegalUnitEnrichment] = []
        _last_unit_label: list[str] = []

        def _on_unit_enriched(enrichment: LegalUnitEnrichment) -> None:
            _partial_enrichments.append(enrichment)
            unit_id = getattr(enrichment, "unit_id", None)
            if unit_id:
                _last_unit_label.clear()
                _last_unit_label.append(str(unit_id))

        try:
            enrichment_result = await asyncio.wait_for(
                enrich_legal_units_async(
                    legal_units_snapshot,
                    policy=enrichment_policy,
                    collector=None,
                    segment_timeout_seconds=seg_timeout,
                    on_unit_enriched=_on_unit_enriched,
                    on_llm_telemetry=_collect_unit_llm_telemetry,
                ),
                timeout=seg_timeout,
            )
        except TimeoutError:
            logger.warning(
                "Semantic enrichment stage: segment enrichment timed out",
                **log_base,
                segment_id=segment_id,
                timeout_seconds=seg_timeout,
                partial_units_completed=len(_partial_enrichments),
                total_units=len(legal_units_snapshot.units),
            )
            if _partial_enrichments:
                llm_provider_for_partial, llm_model_for_partial = _resolve_llm_info_for_partial()
                enrichment_result = _build_partial_enrichment_result(
                    snapshot=legal_units_snapshot,
                    partial_enrichments=_partial_enrichments,
                    policy=enrichment_policy,
                    llm_provider=llm_provider_for_partial,
                    llm_model=llm_model_for_partial,
                )
                logger.info(
                    "Semantic enrichment stage: saving partial enrichment sidecar after timeout",
                    **log_base,
                    segment_id=segment_id,
                    partial_units=len(_partial_enrichments),
                    total_units=len(legal_units_snapshot.units),
                    status_counts=enrichment_result.status_counts,
                )
            else:
                segments_timed_out += 1
                _segment_llm_telemetry.clear()
                continue
        except Exception as enrich_exc:
            logger.warning(
                "Semantic enrichment stage: segment enrichment failed",
                **log_base,
                segment_id=segment_id,
                error=str(enrich_exc),
            )
            segments_failed += 1
            _segment_llm_telemetry.clear()
            continue

        try:
            sidecar_path = ArtifactPath.legal_units_enrichment_v1(
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=document_id,
                segment_id=segment_id,
            )
            sidecar_ref = store.put_json(sidecar_path, enrichment_result.to_dict())

            # Не обновляем ORM-объект — только записываем sidecar_ref в память.
            # Финальный update в БД будет в отдельной finalize-фазе.
            enriched_refs[segment_id] = sidecar_ref
            segments_enriched += 1

            # ── LLM Usage Ledger ───────────────────────────────────────────────
            # Пишем ОДНУ ledger-запись на КАЖДЫЙ реальный unit-level LLM вызов.
            # 1 LLM call = 1 immutable event.
            # request_uid детерминирован: повторный Celery retry не создаст дубль.
            if _segment_llm_telemetry:
                try:
                    from services.llm_usage_recorder import (
                        LLMUsageRecorder,
                        STAGE_STRUCTURE_SEMANTIC_ENRICHMENT,
                    )

                    async with db_uow() as _ledger_uow:
                        _recorder = LLMUsageRecorder(_ledger_uow.session)

                        for _tel in _segment_llm_telemetry:
                            _unit_id = str(_tel.get("unit_id") or "unknown")
                            # Детерминированный request_uid:
                            # при Celery retry тот же unit не создаст дубль
                            # благодаря UniqueConstraint на request_uid.
                            _request_uid = (
                                f"enrichment"
                                f":{run_id or 'none'}"
                                f":{document_id}"
                                f":{segment_id}"
                                f":{_unit_id}"
                            )

                            await _recorder.record_event(
                                tenant_id=uuid.UUID(tenant_id),
                                deal_id=uuid.UUID(deal_id),
                                run_id=uuid.UUID(run_id) if run_id else None,
                                document_id=uuid.UUID(document_id),
                                stage=STAGE_STRUCTURE_SEMANTIC_ENRICHMENT,
                                provider=str(_tel.get("provider") or "ollama"),
                                model=str(_tel.get("model") or ""),
                                prompt_tokens=_tel.get("prompt_tokens"),
                                completion_tokens=_tel.get("completion_tokens"),
                                duration_ms=_tel.get("duration_ms"),
                                llm_attempts=_tel.get("llm_attempts"),
                                parse_success=_tel.get("parse_success"),
                                error_type=_tel.get("error_type"),
                                request_uid=_request_uid,
                            )

                except Exception:
                    logger.warning(
                        "Semantic enrichment: failed to record LLM usage (non-fatal)",
                        document_id=document_id,
                        segment_id=segment_id,
                        run_id=run_id,
                    )
                finally:
                    _segment_llm_telemetry.clear()

            logger.info(
                "Semantic enrichment stage: segment enriched",
                **log_base,
                segment_id=segment_id,
                sidecar_ref=sidecar_ref,
                status_counts=enrichment_result.status_counts,
            )

            # ── Best-effort: progress write после успешной записи sidecar ──
            await _write_enrichment_progress_safe(
                stage_execution_id=stage_execution_id,
                current=segments_enriched,
                total_segment_units=len(legal_units_snapshot.units),
                total_units_in_document=None,
                document_id=document_id,
                document_name=None,
                segment_id=segment_id,
                segment_title=segment_meta.get("segment_title") or None,
                last_unit_label=_last_unit_label[0] if _last_unit_label else None,
                log_base=log_base,
            )

        except Exception as store_exc:
            logger.warning(
                "Semantic enrichment stage: failed to store enrichment sidecar",
                **log_base,
                segment_id=segment_id,
                error=str(store_exc),
            )
            segments_failed += 1
            _segment_llm_telemetry.clear()

    return {
        "enriched_refs": enriched_refs,
        "segments_total": len(segments_snapshot),
        "segments_with_legal_units_ref": segments_with_legal_units_ref,
        "segments_enriched": segments_enriched,
        "segments_timed_out": segments_timed_out,
        "segments_failed": segments_failed,
        "segments_skipped_budget": segments_skipped_budget,
        "budget_exhausted": budget_exhausted,
    }


async def _enrichment_finalize(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None,
    stage_execution_id: str | None,
    llm_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Фаза 3: finalize.

    Выполняется в короткой DB-транзакции.
    Задачи:
    - bulk JSONB patch segment_meta["legal_units_enrichment_ref"] — один SQL-запрос
    - Document.status = ENRICHED
    - mark_succeeded
    - audit log
    - commit

    Изменение vs предыдущей реализации:
    - Убран цикл N × (SELECT + UPDATE) по каждому сегменту.
    - Заменён на один UPDATE ... SET segment_meta = jsonb_set(...) WHERE ANY(...).
    - Расхождение между enriched_refs и реально обновлёнными сегментами
      логируется явно как warning с набором missing_ids.
    """
    log_base = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
    }

    doc_repo = DocumentRepository(db)
    seg_repo = DocumentSegmentRepository(db)
    dse_repo = DocumentStageExecutionRepository(db)
    audit_repo = AuditRepository(db)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)

    enriched_refs: dict[str, str] = llm_result["enriched_refs"]
    segments_total: int = llm_result["segments_total"]
    segments_with_legal_units_ref: int = llm_result["segments_with_legal_units_ref"]
    segments_enriched: int = llm_result["segments_enriched"]
    segments_timed_out: int = llm_result["segments_timed_out"]
    segments_failed: int = llm_result["segments_failed"]
    segments_skipped_budget: int = llm_result["segments_skipped_budget"]
    budget_exhausted: bool = llm_result["budget_exhausted"]

    # ── Bulk JSONB patch: один SQL-запрос вместо N×(SELECT+UPDATE) ───────────
    persist_mismatch_count = 0

    if enriched_refs:
        items: list[tuple[str, str]] = list(enriched_refs.items())
        updated_segment_ids = await seg_repo.bulk_set_enrichment_refs(
            document_version_id=version_uuid,
            items=items,
        )

        expected_segment_ids = set(enriched_refs.keys())
        missing_ids = expected_segment_ids - updated_segment_ids

        if missing_ids:
            missing_count = len(missing_ids)
            persist_mismatch_count = missing_count
            # Корректируем ОБА счётчика:
            # - segments_enriched: только реально записанные в БД
            # - segments_failed: +missing_count, чтобы terminal outcome
            #   корректно отразил DEGRADED вместо ложного COMPLETED.
            segments_enriched = len(updated_segment_ids)
            segments_failed += missing_count
            logger.warning(
                "Semantic enrichment stage: some segment_ids from LLM phase "
                "were not found in DB during finalize — sidecar refs NOT persisted",
                **log_base,
                missing_segment_ids=sorted(missing_ids),
                missing_count=missing_count,
                expected_count=len(expected_segment_ids),
                updated_count=len(updated_segment_ids),
            )
        else:
            logger.debug(
                "Semantic enrichment stage: bulk meta update complete",
                **log_base,
                updated_count=len(updated_segment_ids),
            )
    else:
        updated_segment_ids = set()

    # ── Проверить primary segments ────────────────────────────────────────────
    # list_by_version — один SELECT, допустимо.
    all_segments = await seg_repo.list_by_version(version_uuid)
    primary_missing = [
        seg for seg in all_segments
        if bool(getattr(seg, "is_primary", False))
        and _extract_legal_units_ref(dict(seg.segment_meta or {}))
        and not dict(seg.segment_meta or {}).get("legal_units_enrichment_ref")
    ]
    primary_missing_count = len(primary_missing)
    if primary_missing:
        missing_primary_ids = [s.segment_id for s in primary_missing]
        logger.warning(
            "Semantic enrichment stage: primary segment(s) missing enrichment — "
            "retrieval will degrade to unknown clause_function for these segments",
            **log_base,
            primary_segments_without_enrichment=missing_primary_ids,
        )

    # ── Определить терминальный исход ─────────────────────────────────────────
    outcome = _derive_terminal_outcome(
        segments_with_legal_units_ref=segments_with_legal_units_ref,
        segments_enriched=segments_enriched,
        segments_timed_out=segments_timed_out,
        segments_failed=segments_failed,
        segments_skipped_budget=segments_skipped_budget,
    )

    return await _finalize_enrichment_stage(
        db=db,
        doc_repo=doc_repo,
        dse_repo=dse_repo,
        audit_repo=audit_repo,
        doc_uuid=doc_uuid,
        stage_execution_id=stage_execution_id,
        tenant_id=tenant_id,
        run_id=run_id,
        outcome=outcome,
        segments_total=segments_total,
        segments_with_legal_units_ref=segments_with_legal_units_ref,
        segments_enriched=segments_enriched,
        segments_timed_out=segments_timed_out,
        segments_failed=segments_failed,
        segments_skipped_budget=segments_skipped_budget,
        budget_exhausted=budget_exhausted,
        persist_mismatch_count=persist_mismatch_count,
        primary_missing_count=primary_missing_count,
        log_base=log_base,
    )


async def _finalize_enrichment_stage(
    *,
    db: AsyncSession,
    doc_repo: DocumentRepository,
    dse_repo: DocumentStageExecutionRepository,
    audit_repo: AuditRepository,
    doc_uuid: uuid.UUID,
    stage_execution_id: str | None,
    tenant_id: str,
    run_id: str | None,
    outcome: SemanticEnrichmentStageOutcome,
    segments_total: int,
    segments_with_legal_units_ref: int,
    segments_enriched: int,
    segments_timed_out: int,
    segments_failed: int,
    segments_skipped_budget: int,
    budget_exhausted: bool,
    log_base: dict[str, Any],
    persist_mismatch_count: int = 0,
    primary_missing_count: int = 0,
) -> dict[str, Any]:
    """
    Завершить стадию семантического обогащения:
    - установить Document.status = ENRICHED
    - пометить stage execution как SUCCEEDED с result_details (best-effort)
    - flush + commit
    - записать audit log (best-effort, после commit в той же сессии)

    Порядок commit:
    - mark_succeeded() вызывается до commit, чтобы попасть в ту же транзакцию,
      что и обновление статуса ENRICHED.
    - audit log записывается после commit как best-effort; UoW context manager
      выполняет второй commit при выходе, который фиксирует запись.
    - MASBaseTask.on_success() тоже вызывает mark_succeeded через отдельный UoW
      после возврата из этой функции, но guard идемпотентности в
      _async_mark_execution_succeeded() пропустит его, если execution уже terminal.
    """
    degradation = derive_semantic_enrichment_degradation(
        outcome=outcome,
        segments_enriched=segments_enriched,
        segments_with_legal_units_ref=segments_with_legal_units_ref,
        segments_timed_out=segments_timed_out,
        segments_failed=segments_failed,
        segments_skipped_budget=segments_skipped_budget,
        persist_mismatch_count=persist_mismatch_count,
        primary_missing_count=primary_missing_count,
    )

    result_payload: dict[str, Any] = {
        "terminal_outcome": outcome.value,
        "segments_total": segments_total,
        "segments_with_legal_units_ref": segments_with_legal_units_ref,
        "segments_enriched": segments_enriched,
        "segments_timed_out": segments_timed_out,
        "segments_failed": segments_failed,
        "segments_skipped_budget": segments_skipped_budget,
        "budget_exhausted": budget_exhausted,
        "document_budget_seconds": settings.SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS,
        "segment_timeout_seconds": settings.SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS,
        # ── Degradation analysis ───────────────────────────────────────────
        **degradation,
    }

    warnings: list[str] = []
    if budget_exhausted:
        warnings.append("budget_exhausted")
    if degradation["degraded"]:
        severity = degradation["degradation_severity"]
        warnings.append(f"degraded:{severity}")

    result_details = build_stage_trace_fragment(
        strategy="semantic_enrichment_llm",
        input_summary={
            "document_id": log_base["document_id"],
            "document_version_id": log_base["document_version_id"],
            "segments_total": segments_total,
            "segments_with_legal_units_ref": segments_with_legal_units_ref,
        },
        output_summary={
            "terminal_outcome": outcome.value,
            "segments_enriched": segments_enriched,
            "segments_timed_out": segments_timed_out,
            "segments_failed": segments_failed,
            "segments_skipped_budget": segments_skipped_budget,
            "budget_exhausted": budget_exhausted,
            # ── Degradation analysis ───────────────────────────────────────
            "degraded": degradation["degraded"],
            "degradation_severity": degradation["degradation_severity"],
            "enrichment_ratio": degradation["enrichment_ratio"],
            "degraded_segments": degradation["degraded_segments"],
            "degradation_reasons": degradation["degradation_reasons"],
            "degraded_reason": degradation["degraded_reason"],
        },
        warnings=warnings,
        artifact_refs={},
        decision_details={
            "document_budget_seconds": settings.SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS,
            "segment_timeout_seconds": settings.SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS,
            "persist_mismatch_count": degradation["persist_mismatch_count"],
            "primary_missing_count": degradation["primary_missing_count"],
        },
    )

    logger.info(
        "Semantic enrichment stage: terminal outcome reached",
        **log_base,
        **result_payload,
    )

    # ── Установить Document.status = ENRICHED ─────────────────────────────────
    updated_doc = await doc_repo.update_status(
        doc_uuid,
        DocumentStatus.ENRICHED.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Document {doc_uuid} not found during ENRICHED status update"
        )

    # ── Пометить execution как SUCCEEDED (войдёт в тот же commit) ────────────
    # Это НЕ best-effort. Если execution не закрылась в SUCCEEDED,
    # stage ledger становится неконсистентным и блокирует повторное планирование.
    if stage_execution_id:
        succeeded_execution = await dse_repo.mark_succeeded(
            uuid.UUID(stage_execution_id),
            result_details=result_details,
        )
        if succeeded_execution is None:
            raise PermanentError(
                f"Stage execution {stage_execution_id} not found while marking SUCCEEDED "
                f"for document {log_base['document_id']}"
            )

    # ── Commit: статус ENRICHED + execution SUCCEEDED ─────────────────────────
    await db.flush()
    await db.commit()

    # ── Audit log (best-effort, после commit) ─────────────────────────────────
    try:
        await audit_repo.log(
            tenant_id=uuid.UUID(tenant_id),
            deal_id=uuid.UUID(log_base["deal_id"]),
            action="LEGAL_UNITS_ENRICHMENT_COMPLETED",
            actor="system",
            actor_role="worker",
            details={
                **result_payload,
                "document_id": log_base["document_id"],
                "document_version_id": log_base["document_version_id"],
                "run_id": run_id,
            },
        )
    except Exception as audit_exc:
        logger.warning(
            "Semantic enrichment stage: failed to write audit log",
            **log_base,
            error=str(audit_exc),
        )

    return {
        "document_id": log_base["document_id"],
        "document_version_id": log_base["document_version_id"],
        "deal_id": log_base["deal_id"],
        "tenant_id": tenant_id,
        "terminal_outcome": outcome.value,
        "segments_total": segments_total,
        "segments_with_legal_units_ref": segments_with_legal_units_ref,
        "segments_enriched": segments_enriched,
        "segments_timed_out": segments_timed_out,
        "segments_failed": segments_failed,
        "segments_skipped_budget": segments_skipped_budget,
        "budget_exhausted": budget_exhausted,
        "committed": True,
        "stage_execution_result_details": result_details,
        # ── Degradation analysis ───────────────────────────────────────────
        **degradation,
    }


# ── Приватные helpers ─────────────────────────────────────────────────────────


def _ordered_segments_for_enrichment(segments: list[Any]) -> list[Any]:
    """
    Упорядочить ORM-сегменты для обогащения: сначала primary, затем по segment_order.
    Используется только в preflight-фазе для построения snapshot.
    """
    def _sort_key(seg: Any) -> tuple[int, int]:
        is_primary = 0 if bool(getattr(seg, "is_primary", False)) else 1
        order = int(getattr(seg, "segment_order", 0) or 0)
        return (is_primary, order)

    return sorted(segments, key=_sort_key)


def _ordered_segments_for_enrichment_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Упорядочить snapshot-словари сегментов: сначала primary, затем по segment_order.
    Используется в LLM-фазе, которая работает только с примитивами.
    """
    def _sort_key(snap: dict[str, Any]) -> tuple[int, int]:
        is_primary = 0 if snap.get("is_primary", False) else 1
        order = int(snap.get("segment_order", 0) or 0)
        return (is_primary, order)

    return sorted(snapshots, key=_sort_key)


def _extract_legal_units_ref(segment_meta: Any) -> str | None:
    """
    Безопасно извлечь legal_units_ref из segment_meta.

    Возвращает непустую строку или None.
    """
    if not isinstance(segment_meta, dict):
        return None
    ref = segment_meta.get("legal_units_ref")
    if not ref or not isinstance(ref, str):
        return None
    return ref


def _derive_terminal_outcome(
    *,
    segments_with_legal_units_ref: int,
    segments_enriched: int,
    segments_timed_out: int,
    segments_failed: int,
    segments_skipped_budget: int,
) -> SemanticEnrichmentStageOutcome:
    """
    Определить терминальный исход по счётчикам обработки сегментов.

    Правила (в порядке приоритета):
    - нет кандидатов вообще                              → SKIPPED
    - часть обогащена, часть нет                         → DEGRADED
    - все обогащены                                      → COMPLETED
    - ничего не обогащено, причина — таймаут/бюджет      → TIMED_OUT
    - ничего не обогащено, только hard failures           → DEGRADED
    """
    if segments_with_legal_units_ref == 0:
        return SemanticEnrichmentStageOutcome.SKIPPED

    total_not_enriched = segments_timed_out + segments_failed + segments_skipped_budget

    if segments_enriched == 0:
        # Ничего не успело — различаем таймаут-причину и failure-причину
        if segments_timed_out > 0 or segments_skipped_budget > 0:
            return SemanticEnrichmentStageOutcome.TIMED_OUT
        return SemanticEnrichmentStageOutcome.DEGRADED

    if total_not_enriched == 0:
        return SemanticEnrichmentStageOutcome.COMPLETED

    return SemanticEnrichmentStageOutcome.DEGRADED

def _build_partial_enrichment_result(
    *,
    snapshot: LegalUnitsSnapshot,
    partial_enrichments: list[LegalUnitEnrichment],
    policy: SemanticEnrichmentPolicy,
    llm_provider: str | None,
    llm_model: str | None,
) -> LegalUnitsEnrichmentResult:
    """
    Build a structurally complete LegalUnitsEnrichmentResult from partial enrichments.

    When a segment times out, the enricher is cancelled before processing all units.
    This function assembles a valid sidecar artifact from:
    - units that were successfully processed (from partial_enrichments),
    - units not yet reached — marked as skipped with reason 'segment_timeout_not_reached'.

    Design invariant:
    - The sidecar artifact is always structurally complete:
      every unit in the snapshot has a corresponding enrichment entry.
    - Downstream retrieval uses whatever metadata is available.
    - Missing enrichments degrade gracefully to unknown clause_function.

    Args:
        snapshot: the original LegalUnitsSnapshot for this segment.
        partial_enrichments: enrichments collected before timeout.
        policy: the enrichment policy used for this segment.
        llm_provider: LLM provider name for metadata.
        llm_model: LLM model name for metadata.

    Returns:
        A complete LegalUnitsEnrichmentResult with all units accounted for.
    """
    from services.structure.semantic_enrichment._policy import build_skipped_enrichment

    processed_unit_ids: set[str] = {e.unit_id for e in partial_enrichments}

    result = LegalUnitsEnrichmentResult(
        document_id=snapshot.document_id,
        document_version_id=snapshot.document_version_id,
        segment_id=snapshot.segment_id,
        segment_type=snapshot.segment_type,
        segment_order=snapshot.segment_order,
        is_primary_segment=snapshot.is_primary_segment,
        schema_version="1",
        policy_version=policy.policy_version,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    result.build_warnings.append("partial_enrichment_segment_timeout")
    result.enrichments.extend(partial_enrichments)

    for unit in snapshot.units:
        if unit.unit_id not in processed_unit_ids:
            result.enrichments.append(
                build_skipped_enrichment(
                    unit,
                    policy=policy,
                    reason="segment_timeout_not_reached",
                )
            )

    return result

def _resolve_llm_info_for_partial() -> tuple[str | None, str | None]:
    """
    Resolve LLM provider and model for partial enrichment result metadata.

    Reads from shared settings — same source as enricher uses.
    Failure-isolated: returns (None, None) on any error.
    """
    try:
        provider = str(getattr(settings, "LLM_PROVIDER", "") or "").strip() or None
        model: str | None = None
        if provider == "ollama":
            model = str(getattr(settings, "LLM_OLLAMA_MODEL", "") or "").strip() or None
        elif provider == "openai":
            model = str(getattr(settings, "LLM_OPENAI_MODEL", "") or "").strip() or None
        elif provider == "llamacpp":
            raw_path = str(getattr(settings, "LLM_LOCAL_MODEL_PATH", "") or "").strip()
            if raw_path:
                model = raw_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or None
        return provider, model
    except Exception:
        return None, None

async def _write_enrichment_progress_safe(
    *,
    stage_execution_id: str | None,
    current: int,
    total_segment_units: int,
    total_units_in_document: int | None,
    document_id: str,
    document_name: str | None,
    segment_id: str,
    segment_title: str | None,
    last_unit_label: str | None,
    log_base: dict,
) -> None:
    """
    Best-effort запись live progress для semantic enrichment.

    Открывает отдельную короткоживущую DB-сессию.
    Никогда не бросает исключение — только warning в лог.
    Не меняет lifecycle status execution.
    """
    if not stage_execution_id:
        return

    from datetime import UTC, datetime

    try:
        from db.uow import db_uow
        from db.repositories.document_stage_execution_repo import (
            DocumentStageExecutionRepository,
        )

        async with db_uow() as uow:
            dse_repo = DocumentStageExecutionRepository(uow.session)
            await dse_repo.update_progress_details(
                uuid.UUID(stage_execution_id),
                {
                    "kind": "legal_units",
                    "current": current,
                    "total": total_segment_units,
                    "total_units_in_document": total_units_in_document,
                    "current_document_id": document_id,
                    "current_document_name": document_name,
                    "current_segment_id": segment_id,
                    "current_segment_title": segment_title,
                    "current_unit_label": last_unit_label,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
    except Exception as exc:
        logger.warning(
            "Semantic enrichment stage: failed to write progress_details (non-fatal)",
            **log_base,
            segment_id=segment_id,
            error=str(exc),
        )