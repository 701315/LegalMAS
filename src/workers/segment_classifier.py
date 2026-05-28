# src/workers/segment_classifier.py

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

Архитектура:
- Внешняя Celery-таска sync (def), как и в других worker'ах.
- Внутри один переход sync → async через run_async.
- Вся работа с БД идёт через db_uow().
- HybridClassifier используется тот же, что и для document-level,
  но вызывается через отдельный метод classify_segment(...).

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
from mas_queue.celery_app import celery_app
from ops.metrics import get_metrics

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


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.classify_document_segments",
    queue="default",
)
def classify_document_segments(self, document_id: str, **kwargs) -> dict:
    """
    Sync Celery entry point для segment-level классификации.
    """
    _ = self

    async def _wrapper() -> dict:
        return await _classify_document_segments_async(document_id, kwargs)

    return run_async(_wrapper())


async def _classify_document_segments_async(
    document_id: str,
    extra_args: dict,
) -> dict:
    """
    Асинхронное ядро segment-level классификации по всем сегментам документа.
    """
    _ = extra_args
    start_time = time.time()
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    metrics = get_metrics()

    processed_segments: list[dict[str, Any]] = []
    skipped_segments: list[dict[str, Any]] = []
    total_segments = 0
    classified_segments = 0
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
                str(getattr(doc, "tenant_id", None)) if getattr(doc, "tenant_id", None) else None
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
                    "classified_segments": 0,
                    "skipped_count": 0,
                    "processed_segments": [],
                    "skipped_segments": [],
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
                                "classified_segments": 0,
                                "skipped_count": 0,
                                "duration_ms": result["duration_ms"],
                            },
                        )
                    except Exception:
                        logger.warning(
                            "Segment classifier: failed to write audit log for skipped no-segments result",
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
                        requires_manual_review=_seg_details.get("requires_manual_review", False),
                    )

                    details = _safe_json_dict(result.get("details"))
                    final_type = _normalize_final_type(result.get("final_type"))
                    final_conf = float(result.get("final_confidence") or 0.0)
                    level = result.get("level")
                    language = result.get("language")
                    jurisdiction = result.get("jurisdiction")
                    applicable_triggers = result.get("applicable_triggers", []) or []

                    if final_type is None:
                        level = None

                    segment_confidence_zone = _normalize_confidence_zone(
                        details.get("confidence_zone")
                    )

                    await seg_repo.update_classification_for_segment(
                        document_version_id=version.id,
                        segment_id=segment_id,
                        segment_doc_type=final_type,
                        segment_confidence=final_conf,
                        segment_level=level,
                        segment_confidence_zone=segment_confidence_zone,
                        segment_applicable_triggers=list(applicable_triggers),
                        segment_details=details,
                    )

                    classified_segments += 1
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
                        }
                    )

                    try:
                        metrics.classification_level_distribution.labels(
                            level=level or "UNKNOWN",
                            doc_type=final_type or "UNKNOWN",
                        ).inc()
                    except Exception:
                        logger.exception(
                            "classify_document_segments: failed to update classification metrics"
                        )

                except Exception as e:
                    logger.exception(
                        "Segment classification failed",
                        document_id=document_id,
                        document_version_id=document_version_id,
                        segment_id=segment_id,
                        error=str(e),
                    )
                    skipped_segments.append(
                        {
                            "segment_id": segment_id,
                            "segment_order": getattr(segment, "segment_order", None),
                            "reason": "segment_classification_error",
                            "error": str(e),
                        }
                    )
                    continue

            duration_ms = int((time.time() - start_time) * 1000)

            final_result = {
                "document_id": document_id,
                "document_version_id": document_version_id,
                "status": "completed",
                "total_segments": total_segments,
                "classified_segments": classified_segments,
                "skipped_count": len(skipped_segments),
                "processed_segments": processed_segments,
                "skipped_segments": skipped_segments,
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
                            "classified_segments": classified_segments,
                            "skipped_count": len(skipped_segments),
                            "processed_segments": processed_segments,
                            "skipped_segments": skipped_segments,
                            "duration_ms": duration_ms,
                        },
                    )
                except Exception:
                    logger.warning(
                        "Segment classifier: failed to write audit log for SEGMENT_CLASSIFICATION_COMPLETED",
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
                    "Segment classifier: failed to write audit log for SEGMENT_CLASSIFICATION_FAILED",
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
