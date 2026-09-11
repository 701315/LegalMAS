# src/workers/classifier.py

"""
Classifier Worker — каскадная классификация документов (Stage 6/7).

Позиция в пайплайне:
- import → extract → pii → structure → chunked → classify → run_deal_checks.
- На вход получает структурированный документ (есть chunked / structure artifacts).

Что делает:
- Запускает 3‑уровневый каскад классификации + L4-fallback внутри HybridClassifier:
  L1 (filename) → L2 (header) → L3 (semantic) → опционально L4 (LLM-fallback).
- Обновляет документ полями:
  - doc_type, language, jurisdiction, classification_confidence,
    classification_level, classification_details, applicable_triggers.
- Подбирает и привязывает подходящий playbook_version_id по сделке.
- Обновляет статус документа: chunked → classified.

Архитектура:
- Внешняя Celery‑таска classify_document — синхронная (def), её вызывает Celery.
- Внутри один раз выполняется переход sync → async через run_async
  в _classify_document_async.
- Вся работа с БД выполняется под db_uow().
- Экземпляр HybridClassifier кэшируется на процесс воркера только если
  его можно безопасно перепривязать к текущему UoW / AsyncSession.

Audit trail:
- На успешном завершении пишет CLASSIFY_COMPLETED.
- На PermanentError переводит документ в FAILED через отдельный UoW
  и пишет CLASSIFY_FAILED.
- Audit logging best-effort: проблемы аудита не должны ломать бизнес-стадию.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from classifiers.stage8.hybrid_classifier import HybridClassifier
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from core.stage_trace import build_stage_trace_fragment
from db.repositories import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.uow import UnitOfWork, db_uow
from engine.content.document_content_service import (
    ClauseTreeStorageClient,
    DocumentContentService,
)
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from ops.metrics import get_metrics
from services.run_orchestrator_trigger import retrigger_run_pipeline
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)

_classifier_instance: HybridClassifier | None = None


def _bind_classifier_runtime(
    classifier: HybridClassifier,
    *,
    uow: UnitOfWork,
) -> HybridClassifier:
    """
    Перепривязать runtime-зависимости классификатора к текущему UoW/Session.

    Важно:
    - нельзя держать в singleton'е DocumentContentService с первой попавшейся
      AsyncSession, потому что эта сессия будет закрыта после завершения UoW;
    - поэтому на каждый вызов создаём fresh DocumentContentService на текущей
      session и перепривязываем fetcher/content path к новому service instance.
    """
    content_service = DocumentContentService(
        session=uow.session,
        storage_client=ClauseTreeStorageClient(),
    )

    if hasattr(classifier, "uow"):
        classifier.uow = uow

    # Legacy/optional direct attribute rebind, if such attribute appears later.
    if hasattr(classifier, "content_service"):
        classifier.content_service = content_service

    # Critical audited rebind:
    # HybridClassifier stores content service inside self._fetcher, not as
    # top-level classifier.content_service attribute.
    if hasattr(classifier, "_fetcher"):
        try:
            classifier._fetcher.content_service = content_service
        except Exception:
            logger.exception(
                "classifier: failed to rebind content_service on classifier fetcher"
            )

    return classifier


def _get_classifier(uow: UnitOfWork) -> HybridClassifier:
    """
    Lazy singleton для тяжёлой части классификатора.

    Правило:
    - singleton допустим только для process-level кэша модели;
    - runtime-зависимости (UoW, AsyncSession, content_service) должны
      перепривязываться на каждый вызов.
    """
    global _classifier_instance

    if _classifier_instance is None:
        _classifier_instance = HybridClassifier(
            uow=uow,
            content_service=DocumentContentService(
                session=uow.session,
                storage_client=ClauseTreeStorageClient(),
            ),
        )
        return _classifier_instance

    return _bind_classifier_runtime(_classifier_instance, uow=uow)


def _extract_decided_by(details: dict[str, Any] | None) -> str | None:
    """
    Компактное извлечение decision strategy для worker-level summary log.

    Приоритет:
    1. details["decision_summary"]["decided_by"] — целевой нормализованный контракт
    2. details["voting"]["strategy"]             — текущий/legacy voting path
    3. details["L4"]                            — L4 fallback path
    4. details["MASTERCOPY"]                    — duplicate/master-copy path
    5. confidence_zone == "unknown"             — fallback unknown path
    """
    if not isinstance(details, dict):
        return None

    decision_summary = details.get("decision_summary") or {}
    if isinstance(decision_summary, dict):
        decided_by = decision_summary.get("decided_by")
        if decided_by:
            return str(decided_by)

    voting = details.get("voting") or {}
    if isinstance(voting, dict):
        strategy = voting.get("strategy")
        if strategy:
            return str(strategy)

    if details.get("L4"):
        return "L4_LLM"

    if details.get("MASTERCOPY"):
        return "COPIED"

    if details.get("confidence_zone") == "unknown":
        return "FALLBACK_UNKNOWN"

    return None


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.classify_document",
    queue="default",
)
def classify_document(self, document_id: str, **kwargs: Any) -> dict[str, Any]:
    """
    Sync Celery entry point: обёртка над асинхронным ядром.

    Паттерн:
    - Celery вызывает синхронную функцию.
    - Внутри один раз передаём управление в async‑мир через run_async.
    - После успешного commit retrigger-им run_orchestrator, чтобы он
      запланировал следующую formal stage.
    """

    async def _wrapper() -> dict[str, Any]:
        return await _classify_document_async(self, document_id, kwargs)

    result = run_async(_wrapper())

    run_id = kwargs.get("run_id")
    deal_id = kwargs.get("deal_id")
    tenant_id = kwargs.get("tenant_id")

    if run_id and result.get("committed") is True:
        logger.info(
            "Classification committed, retriggering run pipeline",
            document_id=document_id,
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            status=result.get("status"),
            doctype=result.get("doctype"),
        )
        try:
            retrigger_run_pipeline(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
            )
        except Exception:
            logger.warning(
                "Classifier: failed to retrigger run_orchestrator (non-fatal)",
                document_id=document_id,
                run_id=run_id,
            )

    return result


async def _classify_document_async(
    task: MASBaseTask,
    document_id: str,
    extra_args: dict[str, Any],
) -> dict[str, Any]:
    """
    Асинхронное ядро классификации одного документа.
    """
    _ = task

    start_time = time.time()
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
    metrics = get_metrics()

    from contextlib import nullcontext  # noqa: PLC0415
    from core.tracing import get_stage_tracer  # noqa: PLC0415
    _stage_tracer = get_stage_tracer()
    _stage_span_ctx = (
        _stage_tracer.start_as_current_span(
            "stage.classify_document",
            attributes={
                "document_id": document_id,
                "run_id": extra_args.get("run_id") or "",
                "deal_id": extra_args.get("deal_id") or "",
            },
        )
        if _stage_tracer else nullcontext()
    )

    run_id_str = extra_args.get("run_id")
    run_uuid = uuid.UUID(run_id_str) if run_id_str else None

    playbook = None
    playbook_id_value = None
    playbook_id_str = None
    classification_result: dict[str, Any] | None = None
    classification_requires_review: bool | None = None

    with _stage_span_ctx:

        try:
            async with db_uow() as uow:
                doc_repo = DocumentRepository(uow.session)
                ver_repo = DocumentVersionRepository(uow.session)
                playbook_repo = PlaybookRepository(uow.session)
                audit_repo = AuditRepository(uow.session)

                doc = await doc_repo.get_by_id(doc_uuid)
                if not doc:
                    raise PermanentError(f"Document {document_id} not found")

                # Снимаем scalar snapshot сразу после загрузки ORM-объекта.
                doc_id_value = doc.id
                doc_id_str = str(doc.id)
                deal_id_value = doc.deal_id
                deal_id_str = str(doc.deal_id) if doc.deal_id else None

                if doc.status in (
                    DocumentStatus.CLASSIFIED.value,
                    DocumentStatus.ANALYZING.value,
                ):
                    logger.info(
                        "Already classified or analyzing, skipping",
                        document_id=document_id,
                        status=doc.status,
                    )
                    return {
                        "document_id": document_id,
                        "status": doc.status,
                        "skipped": True,
                        "committed": False,
                    }

                allowed_statuses = {
                    DocumentStatus.CHUNKED.value,
                    DocumentStatus.COMPLETED.value,
                }
                if doc.status not in allowed_statuses:
                    logger.warning(
                        "Document in unexpected status for classification, skipping",
                        document_id=document_id,
                        status=doc.status,
                        allowed_statuses=sorted(allowed_statuses),
                    )
                    return {
                        "document_id": document_id,
                        "status": doc.status,
                        "skipped": True,
                        "reason": "unexpected_status",
                        "committed": False,
                    }

                version = await ver_repo.get_latest(doc_id_value)
                if not version:
                    raise PermanentError(f"No version found for document {document_id}")

                version_id_str = str(version.id)

                # ── FIX #1: Защита от перезаписи + поддержка force_reclassify ─
                existing_doc_type = getattr(doc, "doc_type", None)
                existing_requires_review = getattr(doc, "classification_requires_review", True)
                force_reclassify = extra_args.get("force_reclassify", False) or extra_args.get("force", False)
                
                if (existing_doc_type is not None 
                        and not existing_requires_review 
                        and not force_reclassify):
                    logger.info(
                        "Document already classified, skipping classification worker",
                        document_id=document_id,
                        doc_type=existing_doc_type,
                        classification_level=getattr(doc, "classification_level", None),
                    )
                    
                    run_id_str = extra_args.get("run_id")
                    deal_id_str = str(doc.deal_id) if doc.deal_id else None
                    tenant_id_str = extra_args.get("tenant_id")
                    if run_id_str and deal_id_str and tenant_id_str:
                        try:
                            from services.run_orchestrator_trigger import retrigger_run_pipeline
                            retrigger_run_pipeline(
                                run_id=run_id_str,
                                deal_id=deal_id_str,
                                tenant_id=tenant_id_str,
                            )
                        except Exception as trig_exc:
                            logger.warning("Classifier skip: non-fatal retrigger failure", error=str(trig_exc))

                    if doc.status != DocumentStatus.CLASSIFIED.value:
                        await doc_repo.update_status(
                            doc_id_value,
                            DocumentStatus.CLASSIFIED.value,
                            processing_error_details=None,
                        )

                    return {
                        "document_id": document_id,
                        "status": DocumentStatus.CLASSIFIED.value,
                        "skipped": True,
                        "reason": "already_classified",
                        "doc_type": existing_doc_type,
                        "committed": True,
                    }
                # ── КОНЕЦ FIX #1 ──────────────────────────────────────────────

                classifier = _get_classifier(uow)
                classification_result = await classifier.classify_document(doc_id_str)

                _details = classification_result.get("details") or {}
                decided_by = _extract_decided_by(_details)

                logger.info(
                    "worker_classification_done",
                    doc_id=doc_id_str,
                    deal_id=deal_id_str,
                    final_type=classification_result.get("final_type"),
                    final_confidence=classification_result.get("final_confidence"),
                    decided_by=decided_by,
                    levels_tried=classification_result.get("levels_tried", []),
                    requires_manual_review=_details.get("requires_manual_review", False),
                    applicable_triggers_count=len(
                        classification_result.get("applicable_triggers") or []
                    ),
                )

                raw_final_type = classification_result.get("final_type") or "UNKNOWN"
                final_conf = float(classification_result.get("final_confidence") or 0.0)
                level = classification_result.get("level")
                language = classification_result.get("language")
                jurisdiction = classification_result.get("jurisdiction")
                applicable_triggers = classification_result.get("applicable_triggers", [])
                details = classification_result.get("details", {}) or {}

                classification_requires_review = bool(details.get("requires_manual_review", False))

                # Обогатить span результатом классификации.
                try:
                    from opentelemetry import trace as _otel_trace  # noqa: PLC0415
                    _cur = _otel_trace.get_current_span()
                    if _cur and _cur.is_recording():
                        _cur.set_attribute("classification.doc_type", raw_final_type or "UNKNOWN")
                        _cur.set_attribute(
                            "classification.confidence",
                            float(classification_result.get("final_confidence") or 0.0),
                        )
                        _cur.set_attribute("classification.level", level or "UNKNOWN")
                except Exception:  # noqa: BLE001
                    pass

                final_type: str | None
                if isinstance(raw_final_type, str) and raw_final_type.upper() == "UNKNOWN":
                    final_type = None
                elif isinstance(raw_final_type, str) and raw_final_type.strip():
                    final_type = raw_final_type.strip()
                else:
                    final_type = None

                # ВАЖНО: НЕ обнуляем level при UNKNOWN final_type.
                # level — диагностическое поле (на каком уровне принято решение).
                # На document-level pipeline не ломается из-за Document.status = CLASSIFIED,
                # но обнуление level концептуально неверно и убирается для консистентности.

                playbook = await playbook_repo.get_for_deal(deal_id_value)
                playbook_id_value = playbook.id if playbook else None
                playbook_id_str = str(playbook_id_value) if playbook_id_value else None

                await doc_repo.update_classification(
                    doc_id=doc_id_value,
                    doc_type=final_type,
                    classification_confidence=final_conf,
                    classification_level=level,
                    classification_details=details,
                    applicable_triggers=applicable_triggers,
                    classification_requires_review=classification_requires_review,
                    language=language,
                    jurisdiction=jurisdiction,
                    playbook_version_id=playbook_id_value,
                )

                try:
                    metrics.classification_level_distribution.labels(
                        level=level or "UNKNOWN",
                        doc_type=final_type or "UNKNOWN",
                    ).inc()
                except Exception:
                    logger.exception("classify_document: failed to update classification metrics")

                updated_doc = await doc_repo.update_status(
                    doc_id_value,
                    DocumentStatus.CLASSIFIED.value,
                    processing_error_details=None,
                )
                if not updated_doc:
                    raise PermanentError(
                        f"Document {document_id} not found during CLASSIFIED status update"
                    )

                try:
                    resolved_tenant_id = await resolve_artifact_tenant_id(
                        session=uow.session,
                        deal_id=deal_id_value,
                    )

                    # ── LLM Usage Ledger: L4 classification ───────────────────
                    try:
                        _l4_details = (
                            (classification_result.get("details") or {})
                            .get("L4") or {}
                        )
                        _l4_raw = _l4_details.get("raw") or {}
                        _l4_level = classification_result.get("level")

                        if _l4_level == "L4" or _l4_raw.get("method") == "llm":
                            from services.llm_usage_recorder import (
                                LLMUsageRecorder,
                                STAGE_CLASSIFICATION_L4,
                            )

                            await LLMUsageRecorder.record_event_isolated(
                                tenant_id=resolved_tenant_id,
                                deal_id=deal_id_value,
                                run_id=run_uuid,
                                document_id=doc_id_value,
                                stage=STAGE_CLASSIFICATION_L4,
                                provider=str(
                                    _l4_raw.get("provider") or "ollama"
                                ),
                                model=str(_l4_raw.get("model") or ""),
                                prompt_tokens=_l4_raw.get("prompt_tokens"),
                                completion_tokens=_l4_raw.get(
                                    "completion_tokens"
                                ),
                                llm_attempts=_l4_raw.get("llm_attempts"),
                                parse_success=_l4_raw.get("parse_success"),
                                error_type=_l4_raw.get("error_type"),
                            )
                    except Exception:
                        logger.warning(
                            "classifier: failed to record L4 LLM usage (non-fatal)",
                            document_id=document_id,
                            run_id=run_id_str,
                        )
                    # ── конец LLM Usage Ledger ────────────────────────────────

                    await audit_repo.log(
                        tenant_id=resolved_tenant_id,
                        deal_id=deal_id_value,
                        action="CLASSIFY_COMPLETED",
                        actor="system",
                        actor_role="worker",
                        details={
                            "document_id": doc_id_str,
                            "document_version_id": version_id_str,
                            "doc_type": final_type,
                            "classification_outcome": "typed" if final_type else "unknown",
                            "classification_confidence": final_conf,
                            "classification_level": level,
                            "classification_requires_review": classification_requires_review,
                            "language": language,
                            "jurisdiction": jurisdiction,
                            "applicable_triggers": applicable_triggers,
                            "playbook_version_id": playbook_id_str,
                            "run_id": str(run_uuid) if run_uuid else None,
                        },
                    )
                except Exception:
                    logger.warning(
                        "Classifier: failed to write audit log for CLASSIFY_COMPLETED",
                        document_id=doc_id_str,
                    )

        except PermanentError as e:
            logger.error(
                "Permanent error during classification",
                document_id=document_id,
                error=str(e),
            )
            async with db_uow() as uow_status:
                await _mark_failed(
                    uow_status,
                    doc_uuid,
                    message=str(e),
                    run_id=run_uuid,
                )
            return {
                "document_id": document_id,
                "status": DocumentStatus.FAILED.value,
                "classification_outcome": "failed",
                "error": str(e),
                "committed": False,
            }

        duration_ms = int((time.time() - start_time) * 1000)

        # Вычисляем outcome для return value (для логов и мониторинга).
        # В БД outcome уже записан внутри save_classification_result().
        _final = classification_result.get("final_type") if classification_result else None
        _return_outcome = "typed" if (_final and str(_final).strip()) else "unknown"

        _candidates = []
        if classification_result:
            _raw_candidates = classification_result.get("candidates") or []
            _candidates = _raw_candidates[:10]  # ограничим размер

        _trace = build_stage_trace_fragment(
            strategy="hybrid_classifier_stage8",
            input_summary={
                "document_id": document_id,
                "previous_status": "chunked",
            },
            output_summary={
                "classification_outcome": _return_outcome,
                "doc_type": classification_result.get("final_type") if classification_result else None,
                "confidence": classification_result.get("final_confidence") if classification_result else 0.0,
                "language": classification_result.get("language") if classification_result else None,
                "jurisdiction": classification_result.get("jurisdiction") if classification_result else None,
                "requires_manual_review": bool(classification_requires_review),
                "duration_ms": duration_ms,
            },
            warnings=(
                ["requires_manual_review"] if classification_requires_review else []
            ),
            artifact_refs={
                "playbook_version_id": playbook_id_str,
            },
            decision_details={
                "decided_by": decided_by,
                "levels_tried": classification_result.get("levels_tried", []) if classification_result else [],
                "applicable_triggers": applicable_triggers,
                "confidence_zone": details.get("confidence_zone") if details else None,
                "candidates": _candidates,
            },
        )

        return {
            "document_id": document_id,
            "status": DocumentStatus.CLASSIFIED.value,
            "classification_outcome": _return_outcome,
            "doctype": classification_result.get("final_type") if classification_result else None,
            "confidence": classification_result.get("final_confidence")
            if classification_result
            else 0.0,
            "language": classification_result.get("language") if classification_result else None,
            "jurisdiction": classification_result.get("jurisdiction")
            if classification_result
            else None,
            "playbook_found": playbook is not None,
            "duration_ms": duration_ms,
            "classification_requires_review": classification_requires_review,
            "committed": True,
            "stage_execution_result_details": _trace,
        }


async def _mark_failed(
    uow: UnitOfWork,
    doc_id: uuid.UUID,
    *,
    message: str,
    run_id: uuid.UUID | None,
) -> None:
    """
    Отдельный простой UoW для перевода документа в статус FAILED
    с заполнением processing_error_details.
    """
    repo = DocumentRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    await repo.set_failed(
        doc_id,
        stage="classify",
        message=message,
        reason="classification_error",
        run_id=run_id,
    )

    # Явно ставим business outcome = failed.
    # set_failed() выше ставит pipeline stage (document.status = failed),
    # а здесь ставим business outcome classification.
    try:
        await repo.set_classification_outcome_failed(doc_id)
    except Exception:
        logger.warning(
            "Classifier: failed to persist classification_outcome=failed",
            document_id=str(doc_id),
        )

    document = await repo.get_by_id(doc_id)
    if not document:
        logger.warning(
            "Classifier: document not found after set_failed",
            document_id=str(doc_id),
        )
        return

    try:
        resolved_tenant_id = await resolve_artifact_tenant_id(
            session=uow.session,
            deal_id=document.deal_id,
        )

        await audit_repo.log(
            tenant_id=resolved_tenant_id,
            deal_id=document.deal_id,
            action="CLASSIFY_FAILED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(doc_id),
                "stage": "classify",
                "reason": "classification_error",
                "message": message,
                "classification_outcome": "failed",
                "run_id": str(run_id) if run_id else None,
            },
        )
    except Exception:
        logger.warning(
            "Classifier: failed to write audit log for CLASSIFY_FAILED",
            document_id=str(doc_id),
        )
