# src/workers/classifier.py

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
from services.run_checks_auto_starter import maybe_start_run_checks

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
      session и, если возможно, подменяем classifier.uow / classifier.content_service.
    """
    content_service = DocumentContentService(
        session=uow.session,
        storage_client=ClauseTreeStorageClient(),
    )

    if hasattr(classifier, "uow"):
        classifier.uow = uow

    if hasattr(classifier, "content_service"):
        classifier.content_service = content_service

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
    """

    async def _wrapper() -> dict[str, Any]:
        return await _classify_document_async(self, document_id, kwargs)

    return run_async(_wrapper())


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
    run_id_str = extra_args.get("run_id")
    run_uuid = uuid.UUID(run_id_str) if run_id_str else None

    playbook = None
    classification_result: dict[str, Any] | None = None
    classification_requires_review: bool | None = None

    try:
        async with db_uow() as uow:
            doc_repo = DocumentRepository(uow.session)
            ver_repo = DocumentVersionRepository(uow.session)
            playbook_repo = PlaybookRepository(uow.session)
            audit_repo = AuditRepository(uow.session)

            doc = await doc_repo.get_by_id(doc_uuid)
            if not doc:
                raise PermanentError(f"Document {document_id} not found")

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

            version = await ver_repo.get_latest(doc.id)
            if not version:
                raise PermanentError(f"No version found for document {document_id}")

            classifier = _get_classifier(uow)
            classification_result = await classifier.classify_document(str(doc.id))

            raw_final_type = classification_result.get("final_type") or "UNKNOWN"
            final_conf = float(classification_result.get("final_confidence") or 0.0)
            level = classification_result.get("level")
            language = classification_result.get("language")
            jurisdiction = classification_result.get("jurisdiction")
            applicable_triggers = classification_result.get(
                "applicable_triggers", []
            )
            details = classification_result.get("details", {}) or {}

            classification_requires_review = bool(
                details.get("requires_manual_review", False)
            )

            final_type: str | None
            if isinstance(raw_final_type, str) and raw_final_type.upper() == "UNKNOWN":
                final_type = None
            elif isinstance(raw_final_type, str) and raw_final_type.strip():
                final_type = raw_final_type.strip()
            else:
                final_type = None

            if final_type is None:
                level = None

            playbook = await playbook_repo.get_for_deal(doc.deal_id)

            await doc_repo.update_classification(
                doc_id=doc.id,
                doc_type=final_type,
                classification_confidence=final_conf,
                classification_level=level,
                classification_details=details,
                applicable_triggers=applicable_triggers,
                classification_requires_review=classification_requires_review,
                language=language,
                jurisdiction=jurisdiction,
                playbook_version_id=playbook.id if playbook else None,
            )

            try:
                metrics.classification_level_distribution.labels(
                    level=level or "UNKNOWN",
                    doc_type=final_type or "UNKNOWN",
                ).inc()
            except Exception:
                logger.exception(
                    "classify_document: failed to update classification metrics"
                )

            updated_doc = await doc_repo.update_status(
                doc.id,
                DocumentStatus.CLASSIFIED.value,
                processing_error_details=None,
            )
            if not updated_doc:
                raise PermanentError(
                    f"Document {document_id} not found during CLASSIFIED status update"
                )

            if run_uuid is not None:
                await maybe_start_run_checks(
                    db=uow.session,
                    run_id=run_uuid,
                )

            try:
                tenant_id_value = None
                if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
                    tenant_id_value = doc.deal.tenant_id
                elif hasattr(doc, "tenant_id") and getattr(doc, "tenant_id", None):
                    tenant_id_value = doc.tenant_id

                await audit_repo.log(
                    tenant_id=tenant_id_value or uuid.UUID(int=0),
                    deal_id=doc.deal_id,
                    action="CLASSIFY_COMPLETED",
                    actor="system",
                    actor_role="worker",
                    details={
                        "document_id": str(doc.id),
                        "document_version_id": str(version.id),
                        "doc_type": final_type,
                        "classification_confidence": final_conf,
                        "classification_level": level,
                        "classification_requires_review": classification_requires_review,
                        "language": language,
                        "jurisdiction": jurisdiction,
                        "applicable_triggers": applicable_triggers,
                        "playbook_version_id": str(playbook.id) if playbook else None,
                        "run_id": str(run_uuid) if run_uuid else None,
                    },
                )
            except Exception:
                logger.warning(
                    "Classifier: failed to write audit log for CLASSIFY_COMPLETED",
                    document_id=str(doc.id),
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
            "error": str(e),
            "committed": False,
        }

    duration_ms = int((time.time() - start_time) * 1000)

    return {
        "document_id": document_id,
        "status": DocumentStatus.CLASSIFIED.value,
        "doctype": classification_result.get("final_type")
        if classification_result
        else None,
        "confidence": classification_result.get("final_confidence")
        if classification_result
        else 0.0,
        "language": classification_result.get("language")
        if classification_result
        else None,
        "jurisdiction": classification_result.get("jurisdiction")
        if classification_result
        else None,
        "playbook_found": playbook is not None,
        "duration_ms": duration_ms,
        "classification_requires_review": classification_requires_review,
        "committed": True,
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

    document = await repo.get_by_id(doc_id)
    if not document:
        logger.warning(
            "Classifier: document not found after set_failed",
            document_id=str(doc_id),
        )
        return

    try:
        tenant_id_value = None
        if hasattr(document, "deal") and document.deal and hasattr(
            document.deal, "tenant_id"
        ):
            tenant_id_value = document.deal.tenant_id
        elif hasattr(document, "tenant_id") and getattr(document, "tenant_id", None):
            tenant_id_value = document.tenant_id

        await audit_repo.log(
            tenant_id=tenant_id_value or uuid.UUID(int=0),
            deal_id=document.deal_id,
            action="CLASSIFY_FAILED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(doc_id),
                "stage": "classify",
                "reason": "classification_error",
                "message": message,
                "run_id": str(run_id) if run_id else None,
            },
        )
    except Exception:
        logger.warning(
            "Classifier: failed to write audit log for CLASSIFY_FAILED",
            document_id=str(doc_id),
        )

    