# src/workers/segment_classifier.py

"""
Segment Classifier Worker — segment-level классификация логических документов.

Позиция в пайплайне:
- import → extract → pii → structure → chunked → classify → segment_classify → run_deal_checks
  или
- import → extract → pii → structure → chunked → segment_classify
  (в зависимости от orchestration strategy).

Что делает:
- Для последней версии документа загружает все DocumentSegment.
- Для каждого сегмента получает текст сегмента.
- Вызывает HybridClassifier.classify_segment(...).
- Сохраняет результат в DocumentSegment:
  - segment_doc_type
  - segment_classification_confidence
  - segment_classification_level
  - segment_confidence_zone
  - segment_applicable_triggers
  - segment_classification_details
  - segment_classification_status

Архитектура:
- Внешняя Celery-таска sync (def), как и в других worker'ах.
- Внутри один переход sync → async через run_async.
- Вся работа с БД идёт через db_uow().
- HybridClassifier используется тот же, что и для document-level,
  но вызывается через отдельный метод classify_segment(...).
- После полной успешной segment-level классификации retrigger-им
  run_orchestrator, чтобы он запланировал следующую formal stage
  (build_legal_units_enrichment).

Orchestration contract:
- Retrigger делается ТОЛЬКО если:
  - terminal_segments == total_segments
  - failed_segments == 0
- Terminal statuses:
  - classified
  - unknown
  - skipped
- Partial result / no-segments / errors не retrigger-им orchestrator,
  чтобы не создать бесконечный orchestration loop.
- По образцу classifier.py: retrigger — best-effort, ошибка retrigger
  не ломает результат классификации.

Audit trail:
- На успешном завершении пишет SEGMENT_CLASSIFICATION_COMPLETED.
- При PermanentError пишет SEGMENT_CLASSIFICATION_FAILED.
- Audit logging best-effort: проблемы аудита не должны ломать бизнес-стадию.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from classifiers.stage8._duplicate_handler import DuplicateHandler
from classifiers.stage8.hybrid_classifier import HybridClassifier
from core.exceptions import PermanentError
from core.constants import SegmentClassificationStatus
from core.logging import get_logger
from db.repositories import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.runner_repo import RunnerRepository
from db.uow import UnitOfWork, db_uow
from engine.content.document_content_service import (
    ClauseTreeStorageClient,
    DocumentContentService,
)
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import (
    QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
    celery_app,
)
from ops.metrics import get_metrics
from services.run_orchestrator_trigger import retrigger_run_pipeline

logger = get_logger(__name__)

_segment_classifier_instance: HybridClassifier | None = None


def _build_content_service(uow: UnitOfWork) -> DocumentContentService:
    """
    Создать свежий content service на текущую session/UoW.
    """
    return DocumentContentService(
        session=uow.session,
        storage_client=ClauseTreeStorageClient(),
    )


def _bind_classifier_runtime(
    classifier: HybridClassifier,
    *,
    uow: UnitOfWork,
) -> HybridClassifier:
    """
    Перепривязать runtime-зависимости классификатора к текущему UoW/Session.

    Важно:
    - singleton может хранить только тяжёлые process-level объекты;
    - session / uow / content_service должны быть свежими на каждый вызов.
    """
    content_service = _build_content_service(uow)

    if hasattr(classifier, "uow"):
        classifier.uow = uow

    if hasattr(classifier, "_repo"):
        classifier._repo = RunnerRepository(uow.session)

    if hasattr(classifier, "_duplicates"):
        classifier._duplicates = DuplicateHandler(classifier._repo)

    if hasattr(classifier, "_fetcher"):
        try:
            classifier._fetcher.content_service = content_service
        except Exception:
            logger.exception(
                "segment_classifier: failed to rebind content_service on classifier fetcher"
            )

    return classifier


def _get_segment_classifier(uow: UnitOfWork) -> HybridClassifier:
    """
    Lazy singleton для тяжёлой части классификатора сегментов.
    """
    global _segment_classifier_instance

    if _segment_classifier_instance is None:
        _segment_classifier_instance = HybridClassifier(
            uow=uow,
            content_service=_build_content_service(uow),
        )
        return _segment_classifier_instance

    return _bind_classifier_runtime(_segment_classifier_instance, uow=uow)


def _safe_json_dict(value: Any) -> dict[str, Any]:
    """
    Гарантировать, что details безопасно сериализуется в JSONB.

    Если в details случайно попадут не-JSON-serializable объекты, превращаем
    значение в безопасный словарь с текстовым представлением.
    """
    if isinstance(value, dict):
        try:
            json.dumps(value)
            return value
        except Exception:
            return {"raw_details_repr": repr(value)}

    if value is None:
        return {}

    return {"raw_details_repr": repr(value)}


def _normalize_final_type(raw_final_type: Any) -> str | None:
    """
    Нормализовать финальный тип сегмента.

    UNKNOWN/null/пустые строки превращаем в None, чтобы БД хранила семантически
    пустое значение, а не строковый маркер.
    """
    if not isinstance(raw_final_type, str):
        return None

    cleaned = raw_final_type.strip()
    if not cleaned:
        return None

    if cleaned.upper() == "UNKNOWN":
        return None

    return cleaned


def _normalize_confidence_zone(value: Any) -> str | None:
    """
    Нормализовать confidence_zone.
    """
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    return cleaned or None


def _extract_decided_by(details: dict[str, Any] | None) -> str | None:
    """
    Компактное извлечение decision strategy для worker-level summary log сегмента.
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


def _should_retrigger(result: dict) -> bool:
    """
    Predicate: стоит ли retrigger-ить orchestrator после segment classification.

    Правила:
    - status должен быть "completed";
    - должен быть хотя бы один сегмент;
    - terminal_segments должно совпадать с total_segments
      (все сегменты в terminal status: classified, unknown, skipped);
    - failed_segments должно быть равно 0.

    Важно:
    - UNKNOWN является terminal-статусом: сегмент обработан,
      тип не определён — это валидный исход, не блокирующий pipeline.
    - FAILED не является terminal: сегмент упал с ошибкой,
      retrigger НЕ делаем, чтобы не скрывать проблему.
    - Старый критерий classified_segments == total_segments был неверным:
      он не учитывал UNKNOWN и SKIPPED как завершённые состояния.
    """
    status = str(result.get("status") or "")
    total_segments = int(result.get("total_segments") or 0)
    terminal_segments = int(result.get("terminal_segments") or 0)
    failed_segments = int(result.get("failed_segments") or 0)

    return (
        status == "completed"
        and total_segments > 0
        and terminal_segments == total_segments
        and failed_segments == 0
    )


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.classify_document_segments",
    queue=QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
)

def classify_document_segments(self, document_id: str, **kwargs) -> dict:
    """
    Sync Celery entry point для segment-level классификации.

    После полной успешной segment-level классификации retrigger-им
    run_orchestrator, чтобы он запланировал следующую formal stage
    (build_legal_units_enrichment).

    Orchestration contract:
    - Retrigger только если:
      - terminal_segments == total_segments
      - failed_segments == 0
    - Terminal statuses:
      - classified
      - unknown
      - skipped
    - Partial / no-segments / errors не retrigger-им, чтобы избежать loop.
    - Retrigger best-effort: ошибка не ломает результат классификации.
    """
    _ = self

    async def _wrapper() -> dict:
        return await _classify_document_segments_async(document_id, kwargs)

    result = run_async(_wrapper())

    run_id = kwargs.get("run_id")
    deal_id = kwargs.get("deal_id")
    tenant_id = kwargs.get("tenant_id")

    total_segments = int(result.get("total_segments") or 0)
    terminal_segments = int(result.get("terminal_segments") or 0)
    classified_segments = int(result.get("classified_segments") or 0)
    unknown_segments = int(result.get("unknown_segments") or 0)
    failed_segments = int(result.get("failed_segments") or 0)
    skipped_count = int(result.get("skipped_count") or 0)
    status = str(result.get("status") or "")

    if run_id and _should_retrigger(result):
        logger.info(
            "Segment classification fully completed, retriggering run pipeline",
            extra={
                "document_id": document_id,
                "run_id": run_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "total_segments": total_segments,
                "terminal_segments": terminal_segments,
                "classified_segments": classified_segments,
                "unknown_segments": unknown_segments,
                "failed_segments": failed_segments,
                "skipped_count": skipped_count,
            },
        )
        try:
            retrigger_run_pipeline(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
            )
        except Exception:
            # Best-effort: ошибка retrigger не должна ломать результат классификации.
            logger.warning(
                "Segment classifier: failed to retrigger run_orchestrator (non-fatal)",
                extra={
                    "document_id": document_id,
                    "run_id": run_id,
                },
            )
    elif run_id and status == "completed":
        # completed, но не все сегменты достигли terminal outcome — не retrigger-им.
        logger.warning(
            "Segment classification not terminal for all segments; "
            "orchestrator not retriggered to avoid rescheduling loop",
            extra={
                "document_id": document_id,
                "run_id": run_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "total_segments": total_segments,
                "terminal_segments": terminal_segments,
                "classified_segments": classified_segments,
                "unknown_segments": unknown_segments,
                "failed_segments": failed_segments,
                "skipped_count": skipped_count,
            },
        )

    return result


async def _classify_document_segments_async(
    document_id: str,
    extra_args: dict,
) -> dict:
    """
    Асинхронное ядро segment-level классификации по всем сегментам документа.

    Возвращает dict с полями:
    - status: "completed" | "skipped" | "failed"
    - total_segments: int
    - terminal_segments: int
    - classified_segments: int        # только typed
    - unknown_segments: int
    - skipped_count: int
    - failed_segments: int
    - processed_segments: list
    - skipped_segments: list
    - failed_segment_details: list
    - duration_ms: int

    Не делает retrigger — это ответственность sync entrypoint
    classify_document_segments().
    """
    _ = extra_args
    start_time = time.time()
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    metrics = get_metrics()

    processed_segments: list[dict[str, Any]] = []
    skipped_segments: list[dict[str, Any]] = []
    failed_segments: list[dict[str, Any]] = []
    total_segments = 0
    classified_segments = 0     # processed by classifier (typed + unknown)
    typed_segments_count = 0    # final_type определён
    unknown_segments_count = 0  # final_type не определён (UNKNOWN)
    failed_segments_count = 0   # упали с исключением

    document_version_id: str | None = None
    tenant_id: str | None = None
    deal_id: str | None = None

    try:
        async with db_uow() as uow:
            doc_repo = DocumentRepository(uow.session)
            ver_repo = DocumentVersionRepository(uow.session)
            seg_repo = DocumentSegmentRepository(uow.session)
            audit_repo = AuditRepository(uow.session)

            doc = await doc_repo.get_by_id(doc_uuid)
            if not doc:
                raise PermanentError(f"Document {document_id} not found")

            version = await ver_repo.get_latest(doc.id)
            if not version:
                raise PermanentError(f"No version found for document {document_id}")

            document_version_id = str(version.id)
            deal_id = str(doc.deal_id) if getattr(doc, "deal_id", None) else None
            tenant_id = (
                str(getattr(doc, "tenant_id", None))
                if getattr(doc, "tenant_id", None)
                else None
            )

            segments = await seg_repo.list_by_version(version.id)
            total_segments = len(segments)

            if not segments:
                logger.info(
                    "No segments found for segment classification",
                    document_id=document_id,
                    document_version_id=document_version_id,
                )

                result = {
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                    "status": "skipped",
                    "reason": "no_segments",
                    "total_segments": 0,
                    "terminal_segments": 0,
                    "classified_segments": 0,
                    "unknown_segments": 0,
                    "skipped_count": 0,
                    "failed_segments": 0,
                    "processed_segments": [],
                    "skipped_segments": [],
                    "failed_segment_details": [],
                    "duration_ms": int((time.time() - start_time) * 1000),
                }

                if tenant_id and deal_id:
                    try:
                        await audit_repo.log(
                            tenant_id=uuid.UUID(tenant_id),
                            deal_id=uuid.UUID(deal_id),
                            action="SEGMENT_CLASSIFICATION_COMPLETED",
                            actor="system",
                            actor_role="worker",
                            details={
                                "document_id": document_id,
                                "document_version_id": document_version_id,
                                "status": "skipped",
                                "reason": "no_segments",
                                "total_segments": 0,
                                "terminal_segments": 0,
                                "classified_segments": 0,
                                "unknown_segments": 0,
                                "skipped_count": 0,
                                "failed_segments": 0,
                                "failed_segment_details": [],
                                "duration_ms": result["duration_ms"],
                            },
                        )
                    except Exception:
                        logger.warning(
                            "Segment classifier: failed to write audit log "
                            "for skipped no-segments result",
                            document_id=document_id,
                            document_version_id=document_version_id,
                        )

                return result

            classifier = _get_segment_classifier(uow)
            content_service = _build_content_service(uow)

            for segment in segments:
                segment_id = segment.segment_id

                try:
                    segment_text = await _get_segment_text(
                        content_service=content_service,
                        document_id=doc.id,
                        document_version_id=version.id,
                        segment=segment,
                    )

                    if not segment_text or not segment_text.strip():
                        skipped_segments.append(
                            {
                                "segment_id": segment_id,
                                "segment_order": getattr(segment, "segment_order", None),
                                "reason": "empty_segment_text",
                            }
                        )
                        logger.info(
                            "Segment skipped: empty text",
                            document_id=document_id,
                            document_version_id=document_version_id,
                            segment_id=segment_id,
                        )
                        # Явно помечаем как skipped в БД — terminal статус.
                        try:
                            await seg_repo.update_classification_for_segment(
                                document_version_id=version.id,
                                segment_id=segment_id,
                                segment_doc_type=None,
                                segment_confidence=None,
                                segment_level=None,
                                segment_confidence_zone=None,
                                segment_applicable_triggers=[],
                                segment_details={"skip_reason": "empty_segment_text"},
                                segment_classification_status=SegmentClassificationStatus.SKIPPED.value,
                            )
                        except Exception:
                            logger.warning(
                                "Segment classifier: failed to persist skipped status",
                                document_id=document_id,
                                segment_id=segment_id,
                            )
                        continue

                    result = await classifier.classify_segment(
                        segment_id=segment_id,
                        text=segment_text,
                        filename=getattr(doc, "filename", "") or "",
                        folder_path=getattr(doc, "folder_path", "") or "",
                    )

                    _seg_details = result.get("details") or {}
                    _seg_decided_by = _extract_decided_by(_seg_details)
                    logger.info(
                        "worker_segment_classification_done",
                        doc_id=str(doc.id),
                        segment_id=str(segment.id),
                        final_type=result.get("final_type"),
                        final_confidence=result.get("final_confidence"),
                        decided_by=_seg_decided_by,
                        levels_tried=result.get("levels_tried", []),
                        requires_manual_review=_seg_details.get(
                            "requires_manual_review", False
                        ),
                    )

                    details = _safe_json_dict(result.get("details"))
                    final_type = _normalize_final_type(result.get("final_type"))
                    final_conf = float(result.get("final_confidence") or 0.0)
                    level = result.get("level")
                    language = result.get("language")
                    jurisdiction = result.get("jurisdiction")
                    applicable_triggers = result.get("applicable_triggers", []) or []

                    # ВАЖНО: НЕ обнуляем level при UNKNOWN final_type.
                    # level — диагностическое поле (на каком уровне принято решение).
                    # Источником истины о завершённости стадии является
                    # segment_classification_status, а не level.

                    segment_confidence_zone = _normalize_confidence_zone(
                        details.get("confidence_zone")
                    )

                    # Определяем pipeline-статус этого сегмента.
                    if final_type is not None:
                        seg_status = SegmentClassificationStatus.CLASSIFIED.value
                    else:
                        # final_type = None означает UNKNOWN результат
                        seg_status = SegmentClassificationStatus.UNKNOWN.value

                    await seg_repo.update_classification_for_segment(
                        document_version_id=version.id,
                        segment_id=segment_id,
                        segment_doc_type=final_type,
                        segment_confidence=final_conf,
                        segment_level=level,
                        segment_confidence_zone=segment_confidence_zone,
                        segment_applicable_triggers=list(applicable_triggers),
                        segment_details=details,
                        segment_classification_status=seg_status,
                    )

                    classified_segments += 1
                    if seg_status == SegmentClassificationStatus.CLASSIFIED.value:
                        typed_segments_count += 1
                    else:
                        unknown_segments_count += 1

                    processed_segments.append(
                        {
                            "segment_id": segment_id,
                            "segment_order": getattr(segment, "segment_order", None),
                            "final_type": final_type,
                            "confidence": final_conf,
                            "level": level,
                            "language": language,
                            "jurisdiction": jurisdiction,
                            "confidence_zone": segment_confidence_zone,
                            "classification_status": seg_status,
                        }
                    )

                    try:
                        metrics.classification_level_distribution.labels(
                            level=level or "UNKNOWN",
                            doc_type=final_type or "UNKNOWN",
                        ).inc()
                    except Exception:
                        logger.exception(
                            "classify_document_segments: "
                            "failed to update classification metrics"
                        )

                except Exception as e:
                    logger.exception(
                        "Segment classification failed",
                        document_id=document_id,
                        document_version_id=document_version_id,
                        segment_id=segment_id,
                        error=str(e),
                    )
                    failed_segments_count += 1
                    failed_segments.append(
                        {
                            "segment_id": segment_id,
                            "segment_order": getattr(segment, "segment_order", None),
                            "reason": "segment_classification_error",
                            "error": str(e),
                        }
                    )
                    # Явно помечаем как failed в БД — non-terminal статус.
                    # Это заблокирует прогресс pipeline для этого документа.
                    try:
                        await seg_repo.update_classification_for_segment(
                            document_version_id=version.id,
                            segment_id=segment_id,
                            segment_doc_type=None,
                            segment_confidence=None,
                            segment_level=None,
                            segment_confidence_zone=None,
                            segment_applicable_triggers=[],
                            segment_details={"error": str(e)},
                            segment_classification_status=SegmentClassificationStatus.FAILED.value,
                        )
                    except Exception:
                        logger.warning(
                            "Segment classifier: failed to persist failed status",
                            document_id=document_id,
                            segment_id=segment_id,
                        )
                    continue

            duration_ms = int((time.time() - start_time) * 1000)

            terminal_segments = classified_segments + len(skipped_segments)
            # classified_segments считает все обработанные классификатором (typed + unknown)
            # typed_segments_count — только те, где тип определён
            # unknown_segments_count — где тип не определён
            # skipped — пустой текст (terminal)
            # failed — ошибка (non-terminal)

            final_result = {
                "document_id": document_id,
                "document_version_id": document_version_id,
                "status": "completed",
                "total_segments": total_segments,
                "terminal_segments": terminal_segments,
                "classified_segments": typed_segments_count,
                "unknown_segments": unknown_segments_count,
                "skipped_count": len(skipped_segments),
                "failed_segments": failed_segments_count,
                "processed_segments": processed_segments,
                "skipped_segments": skipped_segments,
                "failed_segment_details": failed_segments,
                "duration_ms": duration_ms,
            }

            if tenant_id and deal_id:
                try:
                    await audit_repo.log(
                        tenant_id=uuid.UUID(tenant_id),
                        deal_id=uuid.UUID(deal_id),
                        action="SEGMENT_CLASSIFICATION_COMPLETED",
                        actor="system",
                        actor_role="worker",
                        details={
                            "document_id": document_id,
                            "document_version_id": document_version_id,
                            "status": "completed",
                            "total_segments": total_segments,
                            "terminal_segments": terminal_segments,
                            "classified_segments": typed_segments_count,
                            "unknown_segments": unknown_segments_count,
                            "skipped_count": len(skipped_segments),
                            "failed_segments": failed_segments_count,
                            "processed_segments": processed_segments,
                            "skipped_segments": skipped_segments,
                            "failed_segment_details": failed_segments,
                            "duration_ms": duration_ms,
                        },
                    )
                except Exception:
                    logger.warning(
                        "Segment classifier: failed to write audit log "
                        "for SEGMENT_CLASSIFICATION_COMPLETED",
                        document_id=document_id,
                        document_version_id=document_version_id,
                    )

            return final_result

    except PermanentError as e:
        logger.error(
            "Permanent error during segment classification",
            document_id=document_id,
            error=str(e),
        )

        duration_ms = int((time.time() - start_time) * 1000)

        if tenant_id and deal_id:
            try:
                async with db_uow() as uow_status:
                    audit_repo = AuditRepository(uow_status.session)
                    await audit_repo.log(
                        tenant_id=uuid.UUID(tenant_id),
                        deal_id=uuid.UUID(deal_id),
                        action="SEGMENT_CLASSIFICATION_FAILED",
                        actor="system",
                        actor_role="worker",
                        details={
                            "document_id": document_id,
                            "document_version_id": document_version_id,
                            "status": "failed",
                            "error": str(e),
                            "duration_ms": duration_ms,
                        },
                    )
            except Exception:
                logger.warning(
                    "Segment classifier: failed to write audit log "
                    "for SEGMENT_CLASSIFICATION_FAILED",
                    document_id=document_id,
                    document_version_id=document_version_id,
                )

        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "status": "failed",
            "error": str(e),
            "duration_ms": duration_ms,
        }


async def _get_segment_text(
    *,
    content_service: DocumentContentService,
    document_id: uuid.UUID,
    document_version_id: uuid.UUID,
    segment,
) -> str | None:
    """
    Получить текст сегмента через DocumentContentService.

    ВАЖНО:
    - worker не знает, где хранится текст сегмента;
    - вся логика чтения сегментного текста инкапсулирована в content service;
    - ожидается, что DocumentContentService.get_segment_text(...) уже реализован.
    """
    _ = document_id

    if hasattr(content_service, "get_segment_text"):
        return await content_service.get_segment_text(
            document_version_id=document_version_id,
            segment_id=segment.segment_id,
        )

    raise NotImplementedError(
        "DocumentContentService.get_segment_text(...) is not implemented yet. "
        "Add segment-aware text extraction before enabling segment worker."
    )


    