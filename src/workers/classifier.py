"""
Classifier Worker — simplified version for vertical slice.

Uses HybridClassifier (L1 only) with YAML-driven rules.
Saves classification results to new DB fields:
  - classification_confidence
  - classification_level
  - classification_details  (JSON)
  - applicable_triggers     (JSON array)

applicable_triggers drives Runner routing:
  Runner reads this field to decide which checks to execute.
  In Stage 8: cross-referenced with check_catalogue.yaml.

Full 4-level cascade (L1+L2+L3+L4) in Stage 6.
"""

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.classifiers import HybridClassifier
from src.core.constants import DocumentStatus
from src.core.exceptions import PermanentError
from src.core.logging import get_logger
from src.db.uow import db_uow
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

_classifier: HybridClassifier | None = None


def _get_classifier() -> HybridClassifier:
    global _classifier
    if _classifier is None:
        _classifier = HybridClassifier()
    return _classifier


async def _classify_document_async(
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None,
) -> dict:
    """
    Async core: loads artifacts, runs HybridClassifier, updates DB and queues Runner.

    Все операции с БД выполняются через переданную AsyncSession (db),
    чтобы одна задача worker'а работала в рамках одного unit of work.
    """
    from src.db.repositories import (
        DocumentRepository,
        DocumentVersionRepository,
    )
    from src.workers.runner import run_checks

    start_time = time.time()
    store = ArtifactStore()

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)

    doc = await doc_repo.get_by_id(uuid.UUID(document_id))
    if not doc:
        raise PermanentError(f"Document {document_id} not found")

    version = await ver_repo.get_by_id(uuid.UUID(document_version_id))
    if not version:
        raise PermanentError(f"Version {document_version_id} not found")

    if not version.text_layout_raw_ref:
        raise PermanentError(f"No textlayoutraw for {document_id}")

    # 1. Load textlayoutraw
    raw_key = version.text_layout_raw_ref.replace(f"s3://{store.bucket}/", "")
    text_layout_raw = store.get_json(raw_key)

    # 2. Load sanitized (optional, for future L4)
    text_sanitized = ""
    if version.text_layout_sanitized_ref:
        try:
            san_key = version.text_layout_sanitized_ref.replace(f"s3://{store.bucket}/", "")
            sanitized_layout = store.get_json(san_key)
            text_sanitized = _extract_text(sanitized_layout)
        except Exception:
            # Санитайзер — не критичен для L1, падаем мягко
            pass

    # 3. Run HybridClassifier
    full_text = _extract_text(text_layout_raw)
    result = _get_classifier().classify(
        text=full_text,
        text_sanitized=text_sanitized,
        filename=doc.filename,
        folder_path=doc.folder_path or "",
    )

    # 4. Update document with ALL classification fields
    await doc_repo.update_classification(
        doc_id=doc.id,
        doc_type=result.doctype,
        classification_confidence=result.confidence,
        classification_level=result.level.value,
        classification_details=result.details,
        applicable_triggers=result.applicable_triggers,
    )
    await doc_repo.update_status(
        doc.id,
        status=DocumentStatus.CLASSIFIED.value,
        language=result.language,
        jurisdiction_guess=result.jurisdiction,
    )

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "Classification complete",
        document_id=document_id,
        doctype=result.doctype,
        confidence=result.confidence,
        level=result.level.value,
        language=result.language,
        triggers=result.applicable_triggers,
        duration_ms=duration_ms,
    )

    # 5. Queue Runner
    run_checks.delay(
        document_id=document_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        doctype=result.doctype,
    )

    return {
        "document_id": document_id,
        "doctype": result.doctype,
        "confidence": result.confidence,
        "level": result.level.value,
        "language": result.language,
        "jurisdiction": result.jurisdiction,
        "triggers": result.applicable_triggers,
        "duration_ms": duration_ms,
    }


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.classify_document",
    track_job=False,
    queue="default",
)
async def classify_document_task(
    self,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
) -> dict:
    """
    Celery entrypoint: async wrapper around classification core.

    Для каждой таски создаётся отдельный UnitOfWork/AsyncSession,
    внутри которого выполняются все операции с БД для данного документа.
    """
    logger.info("Starting classification", document_id=document_id)

    async with db_uow() as uow:
        return await _classify_document_async(
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            db=uow.session,
            run_id=run_id,
        )


def _extract_text(layout: dict) -> str:
    elements = layout.get("elements", [])
    return " ".join(elem.get("text", "") for elem in elements)
