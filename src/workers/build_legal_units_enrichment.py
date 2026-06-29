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
    DocumentStatus,
    DocumentStageExecutionStatus,
    RunStatus,
    SemanticEnrichmentStageOutcome,
)
from core.exceptions import PermanentError

from core.logging import get_logger
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
from workers._tenant_resolver import resolve_artifact_tenant_id

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

    Всегда завершается DocumentStatus.ENRICHED после достижения терминального
    исхода (completed / degraded / skipped / timed_out / unavailable).
    После завершения перезапускает run_orchestrator, чтобы gate проверок
    мог оценить готовность документа.
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            resolved_tenant_id = await resolve_artifact_tenant_id(
                session=uow.session,
                deal_id=deal_id,
                document_id=document_id,
                payload_tenant_id=tenant_id,
            )
            return await _build_legal_units_enrichment_async(
                document_version_id=document_version_id,
                document_id=document_id,
                deal_id=deal_id,
                tenant_id=resolved_tenant_id,
                db=uow.session,
                run_id=run_id,
                stage_execution_id=stage_execution_id,
            )

    # LLM выполняется через общий LLMClient (multi-provider).
    # Поддерживаемые провайдеры: ollama (prod) | openai | llamacpp (legacy embedded).
    #
    # Per-task reset_local_runtime_state() намеренно не вызывается:
    # - для ollama/openai (HTTP path) это полный no-op — нет shared in-process state;
    # - для llamacpp (embedded) — aggressive reset во время active inference
    #   приводил к SIGSEGV; cancellation-safe path внутри LLMClient уже
    #   обеспечивает корректный cleanup через asyncio.shield + in-flight guard
    #   в reset_local_runtime_state().
    result = run_async(_wrapper())

    if run_id and result.get("committed"):
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
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
    return {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "terminal_outcome": SemanticEnrichmentStageOutcome.SKIPPED.value,
        "stale_replay": True,
        "stale_replay_reason": reason,
        # committed=True сигнализирует sync wrapper-у вызвать retrigger_run_pipeline().
        # Для terminal run это False — orchestrator будить не нужно.
        "committed": retrigger_orchestrator,
        "segments_total": 0,
        "segments_with_legal_units_ref": 0,
        "segments_enriched": 0,
        "segments_timed_out": 0,
        "segments_failed": 0,
        "segments_skipped_budget": 0,
        "budget_exhausted": False,
        "stage_execution_result_details": {
            "terminal_outcome": SemanticEnrichmentStageOutcome.SKIPPED.value,
            "stale_replay": True,
            "stale_replay_reason": reason,
        },
    }



async def _build_legal_units_enrichment_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,
    stage_execution_id: str | None = None,
) -> dict[str, Any]:
    """
    Асинхронное ядро стадии семантического обогащения.

    Оркестрирует LLM-обогащение с ограничениями по времени:
    - таймаут на сегмент
    - бюджет на весь документ
    - graceful degradation при отказах и таймаутах
    - всегда завершается статусом документа ENRICHED
    """
    started_monotonic = time.monotonic()

    log_base = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
    }

    logger.info("Semantic enrichment stage: starting", extra=log_base)

    store = ArtifactStore(settings)
    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)
    seg_repo = DocumentSegmentRepository(db)
    dse_repo = DocumentStageExecutionRepository(db)
    audit_repo = AuditRepository(db)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)

    # ── Stale replay guard ────────────────────────────────────────────────────
    #
    # Проблема:
    # При падении worker-а с SIGSEGV или kill задача может остаться
    # не-ACK-нутой в Redis (acks_late=True). После рестарта брокер
    # редоставит её, даже если enrichment уже был успешно выполнен.
    #
    # Решение:
    # Проверяем состояние run / stage_execution / document ДО начала тяжёлой
    # LLM-работы. Если видим признаки stale replay — short-circuit без ошибки.
    #
    # Почему не просто return None:
    # - sync wrapper build_legal_units_enrichment() смотрит на result["committed"]
    #   чтобы решить, нужен ли retrigger_run_pipeline();
    # - для stale replay мы хотим: тяжёлую работу пропустить, но orchestrator
    #   разбудить если run ещё не завершён (recovery mechanism).

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

    # Загружаем stage_execution для guard-а (если есть).
    current_execution = None
    if stage_execution_id:
        try:
            current_execution = await dse_repo.get_by_id(uuid.UUID(stage_execution_id))
        except Exception as exc:
            logger.warning(
                "Semantic enrichment stage: failed to load stage_execution for stale check",
                extra={**log_base, "error": str(exc)},
            )

    # Загружаем run для guard-а (если есть run_id).
    current_run = None
    if run_id:
        try:
            run_repo = RunRepository(db)
            current_run = await run_repo.get_by_id(uuid.UUID(run_id))
        except Exception as exc:
            logger.warning(
                "Semantic enrichment stage: failed to load run for stale check",
                extra={**log_base, "error": str(exc)},
            )

    # Guard 1: run уже terminal.
    # Если run уже завершён, нет смысла ни делать enrichment, ни будить orchestrator.
    if current_run is not None and current_run.status in _stale_run_terminal_statuses:
        logger.warning(
            "Semantic enrichment stage: stale replay detected — run already terminal, skipping",
            extra={
                **log_base,
                "run_status": current_run.status,
                "stage_execution_id": stage_execution_id,
                "retrigger_orchestrator": False,
            },
        )
        return _build_stale_replay_result(
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            reason="stale_replay_run_terminal",
            retrigger_orchestrator=False,
        )

    # Guard 2: stage_execution уже terminal.
    if current_execution is not None and current_execution.status in _stale_execution_terminal_statuses:
        run_not_terminal = (
            current_run is None
            or current_run.status not in _stale_run_terminal_statuses
        )
        # Для уже успешно выполненного execution — retrigger orchestrator как recovery,
        # если run ещё не завершён. Для failed/cancelled — не prodвигаем pipeline.
        should_retrigger = (
            current_execution.status == DocumentStageExecutionStatus.SUCCEEDED.value
            and run_not_terminal
        )
        logger.warning(
            "Semantic enrichment stage: stale replay detected — stage execution already terminal, skipping",
            extra={
                **log_base,
                "execution_status": current_execution.status,
                "run_status": current_run.status if current_run else None,
                "stage_execution_id": stage_execution_id,
                "retrigger_orchestrator": should_retrigger,
            },
        )
        return _build_stale_replay_result(
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            reason=f"stale_replay_execution_{current_execution.status}",
            retrigger_orchestrator=should_retrigger,
        )

    # ── Загрузить документ / версию / сегменты ────────────────────────────────
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

    # Guard 3: документ уже downstream от enrichment.
    # Это дополнительная защита: даже если stage_execution не найден (например,
    # был удалён или не создавался), document status говорит нам правду.
    if document.status in _stale_document_downstream_statuses:
        run_not_terminal = (
            current_run is None
            or current_run.status not in _stale_run_terminal_statuses
        )
        logger.warning(
            "Semantic enrichment stage: stale replay detected — document already downstream of enrichment, skipping",
            extra={
                **log_base,
                "document_status": document.status,
                "run_status": current_run.status if current_run else None,
                "stage_execution_id": stage_execution_id,
                "retrigger_orchestrator": run_not_terminal,
            },
        )
        return _build_stale_replay_result(
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            reason="stale_replay_document_already_enriched",
            retrigger_orchestrator=run_not_terminal,
        )

    segments = await seg_repo.list_by_version(version_uuid)

    # ── Пометить execution как STARTED ───────────────────────────────────────
    # После фикса orchestrator (commit PLANNED execution до send_task)
    # отсутствие stage_execution в БД здесь является нарушением контракта,
    # а не допустимой ситуацией.
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
            extra=log_base,
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

    llm_available = is_semantic_enrichment_llm_available()
    if not llm_available:
        logger.warning(
            "Semantic enrichment stage: LLM unavailable, terminal outcome=unavailable",
            extra=log_base,
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

    # ── Вычислить дедлайн документа ───────────────────────────────────────────
    document_deadline = build_document_enrichment_deadline(
        started_monotonic=started_monotonic,
        settings=settings,
    )

    # ── Упорядочить сегменты: сначала primary, затем по segment_order ─────────
    ordered_segments = _ordered_segments_for_enrichment(segments)

    enrichment_policy = make_policy_from_settings()

    # ── Счётчики по сегментам ─────────────────────────────────────────────────
    segments_with_legal_units_ref = 0
    segments_enriched = 0
    segments_timed_out = 0
    segments_failed = 0
    segments_skipped_budget = 0
    budget_exhausted = False

    # ── Обход сегментов ───────────────────────────────────────────────────────
    for seg in ordered_segments:
        legal_units_ref = _extract_legal_units_ref(seg.segment_meta)

        if not legal_units_ref:
            logger.debug(
                "Semantic enrichment stage: segment has no legal_units_ref, skipping",
                extra={
                    **log_base,
                    "segment_id": seg.segment_id,
                },
            )
            continue

        segments_with_legal_units_ref += 1

        # Проверить бюджет документа перед обработкой сегмента
        if is_enrichment_budget_exhausted(deadline_monotonic=document_deadline):
            budget_exhausted = True
            segments_skipped_budget += 1
            logger.info(
                "Semantic enrichment stage: document budget exhausted, skipping segment",
                extra={
                    **log_base,
                    "segment_id": seg.segment_id,
                    "segments_remaining_skipped": (
                        segments_with_legal_units_ref
                        - segments_enriched
                        - segments_failed
                        - segments_timed_out
                        - segments_skipped_budget
                    ),
                },
            )
            continue

        # Загрузить базовый набор legal units
        try:
            baseline_payload = store.get_json(legal_units_ref)
            legal_units_snapshot = LegalUnitsSnapshot.from_dict(baseline_payload)
        except Exception as load_exc:
            logger.warning(
                "Semantic enrichment stage: failed to load baseline legal units, skipping segment",
                extra={
                    **log_base,
                    "segment_id": seg.segment_id,
                    "legal_units_ref": legal_units_ref,
                    "error": str(load_exc),
                },
            )
            segments_failed += 1
            continue

        if not legal_units_snapshot.units:
            logger.debug(
                "Semantic enrichment stage: segment has zero legal units, skipping",
                extra={**log_base, "segment_id": seg.segment_id},
            )
            continue

        # Вычислить таймаут сегмента (может быть обрезан до остатка бюджета).
        # Primary segment получает гарантированный минимальный таймаут,
        # независимый от остатка бюджета. Это критично потому что:
        # - primary contract segment обычно самый большой,
        # - без его enrichment retrieval не получает clause_function/unit_type,
        # - дефолт из settings позволяет конфигурировать без деплоя кода.
        seg_timeout = resolve_segment_enrichment_timeout(
            deadline_monotonic=document_deadline,
            settings=settings,
        )

        is_primary_seg = bool(getattr(seg, "is_primary", False))

        if is_primary_seg:
            primary_min_timeout = float(
                getattr(
                    settings,
                    "SEMANTIC_ENRICHMENT_PRIMARY_SEGMENT_MIN_TIMEOUT_SECONDS",
                    600,
                )
            )
            if seg_timeout < primary_min_timeout:
                logger.info(
                    "Semantic enrichment stage: extending timeout for primary segment",
                    extra={
                        **log_base,
                        "segment_id": seg.segment_id,
                        "original_timeout": seg_timeout,
                        "extended_timeout": primary_min_timeout,
                    },
                )
                seg_timeout = primary_min_timeout

        if seg_timeout <= 0:
            budget_exhausted = True
            segments_skipped_budget += 1
            continue

        # Запустить обогащение с ограничением по времени.
        # on_unit_enriched callback накапливает обработанные units для partial persistence:
        # при segment timeout уже готовые units не теряются.
        _partial_enrichments: list[LegalUnitEnrichment] = []

        def _on_unit_enriched(enrichment: LegalUnitEnrichment) -> None:
            _partial_enrichments.append(enrichment)

        try:
            enrichment_result = await asyncio.wait_for(
                enrich_legal_units_async(
                    legal_units_snapshot,
                    policy=enrichment_policy,
                    collector=None,
                    segment_timeout_seconds=seg_timeout,
                    on_unit_enriched=_on_unit_enriched,
                ),
                timeout=seg_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Semantic enrichment stage: segment enrichment timed out",
                extra={
                    **log_base,
                    "segment_id": seg.segment_id,
                    "timeout_seconds": seg_timeout,
                    "partial_units_completed": len(_partial_enrichments),
                    "total_units": len(legal_units_snapshot.units),
                },
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
                    extra={
                        **log_base,
                        "segment_id": seg.segment_id,
                        "partial_units": len(_partial_enrichments),
                        "total_units": len(legal_units_snapshot.units),
                        "status_counts": enrichment_result.status_counts,
                    },
                )
                # Fall through to sidecar save below.
            else:
                segments_timed_out += 1
                continue
        except Exception as enrich_exc:
            logger.warning(
                "Semantic enrichment stage: segment enrichment failed",
                extra={
                    **log_base,
                    "segment_id": seg.segment_id,
                    "error": str(enrich_exc),
                },
            )
            segments_failed += 1
            continue

        # Сохранить sidecar и обновить segment_meta
        try:
            sidecar_path = ArtifactPath.legal_units_enrichment_v1(
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=document_id,
                segment_id=seg.segment_id,
            )
            sidecar_ref = store.put_json(sidecar_path, enrichment_result.to_dict())

            # Обновить segment_meta ссылкой на новый sidecar
            existing_meta = dict(seg.segment_meta or {})
            existing_meta["legal_units_enrichment_ref"] = sidecar_ref
            seg.segment_meta = existing_meta

            segments_enriched += 1

            logger.info(
                "Semantic enrichment stage: segment enriched",
                extra={
                    **log_base,
                    "segment_id": seg.segment_id,
                    "sidecar_ref": sidecar_ref,
                    "status_counts": enrichment_result.status_counts,
                },
            )
        except Exception as store_exc:
            logger.warning(
                "Semantic enrichment stage: failed to store enrichment sidecar",
                extra={
                    **log_base,
                    "segment_id": seg.segment_id,
                    "error": str(store_exc),
                },
            )
            segments_failed += 1

    # ── Определить терминальный исход ─────────────────────────────────────────
    outcome = _derive_terminal_outcome(
        segments_with_legal_units_ref=segments_with_legal_units_ref,
        segments_enriched=segments_enriched,
        segments_timed_out=segments_timed_out,
        segments_failed=segments_failed,
        segments_skipped_budget=segments_skipped_budget,
    )

    # Проверить, получил ли primary segment enrichment.
    # Отсутствие enrichment для primary = retrieval degradation для checks.
    primary_segments_with_legal_units = [
        seg for seg in ordered_segments
        if bool(getattr(seg, "is_primary", False))
        and _extract_legal_units_ref(seg.segment_meta)
    ]
    primary_segments_without_enrichment = [
        seg for seg in primary_segments_with_legal_units
        if not dict(seg.segment_meta or {}).get("legal_units_enrichment_ref")
    ]
    if primary_segments_without_enrichment:
        missing_ids = [s.segment_id for s in primary_segments_without_enrichment]
        logger.warning(
            "Semantic enrichment stage: primary segment(s) missing enrichment — "
            "retrieval will degrade to unknown clause_function for these segments",
            extra={
                **log_base,
                "primary_segments_without_enrichment": missing_ids,
                "outcome": outcome.value,
            },
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
        segments_total=len(segments),
        segments_with_legal_units_ref=segments_with_legal_units_ref,
        segments_enriched=segments_enriched,
        segments_timed_out=segments_timed_out,
        segments_failed=segments_failed,
        segments_skipped_budget=segments_skipped_budget,
        budget_exhausted=budget_exhausted,
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
    result_details: dict[str, Any] = {
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
    }

    logger.info(
        "Semantic enrichment stage: terminal outcome reached",
        extra={
            **log_base,
            **result_details,
        },
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
                **result_details,
                "document_id": log_base["document_id"],
                "document_version_id": log_base["document_version_id"],
                "run_id": run_id,
            },
        )
    except Exception as audit_exc:
        logger.warning(
            "Semantic enrichment stage: failed to write audit log",
            extra={**log_base, "error": str(audit_exc)},
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
        # Подхватывается MASBaseTask.on_success() → mark_succeeded с result_details,
        # если worker-level mark_succeeded выше был пропущен или завершился с ошибкой.
        "stage_execution_result_details": result_details,
    }


# ── Приватные helpers ─────────────────────────────────────────────────────────


def _ordered_segments_for_enrichment(segments: list[Any]) -> list[Any]:
    """
    Упорядочить сегменты для обогащения: сначала primary, затем по segment_order.
    """
    def _sort_key(seg: Any) -> tuple[int, int]:
        is_primary = 0 if bool(getattr(seg, "is_primary", False)) else 1
        order = int(getattr(seg, "segment_order", 0) or 0)
        return (is_primary, order)

    return sorted(segments, key=_sort_key)


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
    
