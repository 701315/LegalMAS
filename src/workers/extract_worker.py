"""
Extract Worker (Phase 13 V2 Only).

В V2-пайплайн полностью избавлен от тяжелого повторного извлечения PDF.
Мгновенно активирует canonical bypass:
- Находит запись резолва document_run_language_resolution;
- Считывает run-scoped layout_primary_ref;
- Переводит статус в EXTRACTED и завершается за доли секунды.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, QuarantineError, TransientError
from core.logging import get_logger
from db.repositories import AuditRepository, DocumentRepository, DocumentVersionRepository
from db.repositories.document_run_language_resolution_repo import (
    DocumentRunLanguageResolutionRepository,
)
from db.uow import UnitOfWork, db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.document_layout.config import layout_config
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


def _s3_ref_to_store_path(s3_ref: str, bucket: str) -> str:
    prefix = f"s3://{bucket}/"
    if not s3_ref or not s3_ref.startswith(prefix):
        raise PermanentError(f"Invalid S3 ref for bucket '{bucket}': {s3_ref}")
    return s3_ref.replace(prefix, "", 1)


async def update_extraction_result(
    document_version_id: str,
    document_id: str,
    raw_ref: str,
    primary_ref: str | None,
    page_count: int,
    strategy: str,
    ocr_confidence: float | None,
    db: AsyncSession,
) -> None:
    """
    Обновить результаты извлечения в БД (version + document).
    """
    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)

    await ver_repo.update_refs(
        version_uuid,
        raw_ref=raw_ref,
        layout_primary_ref=primary_ref,
        extraction_strategy=strategy,
        ocr_confidence=ocr_confidence,
    )

    updated_doc = await doc_repo.update_status(
        doc_uuid,
        DocumentStatus.EXTRACTED.value,
        page_count=page_count,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(f"Document {document_id} not found during EXTRACTED status update")


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.extract_document",
    track_job=False,
    queue="default",
)
def extract_document(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    async def _wrapper() -> dict:
        async with db_uow() as uow:
            resolved_tenant_id = await resolve_artifact_tenant_id(
                session=uow.session,
                deal_id=deal_id,
                document_id=document_id,
                payload_tenant_id=tenant_id,
            )
            return await _extract_document_async(
                document_version_id=document_version_id,
                document_id=document_id,
                deal_id=deal_id,
                tenant_id=resolved_tenant_id,
                db=uow.session,
                run_id=run_id,
            )

    try:
        result = run_async(_wrapper())
    except PermanentError as e:
        logger.error(
            "Permanent error during extraction",
            document_id=document_id,
            version_id=document_version_id,
            error=str(e),
        )
        raise
    except TransientError as e:
        logger.warning(
            "Transient error during extraction; task should be retried",
            document_id=document_id,
            version_id=document_version_id,
            error=str(e),
        )
        raise

    if run_id and result.get("committed") is True:
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
        )

    return result


async def _extract_document_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,
) -> dict:
    start_time = time.time()
    store = ArtifactStore(settings)

    version_uuid = uuid.UUID(document_version_id)
    run_uuid = uuid.UUID(run_id) if run_id else None

    if not run_uuid:
        raise PermanentError(f"run_id is required for V2 extraction, version={document_version_id}")

    res_repo = DocumentRunLanguageResolutionRepository(db)
    res_record = await res_repo.get_by_run_and_version(run_uuid, version_uuid)

    if not res_record or not res_record.layout_primary_ref:
        raise PermanentError(
            f"V2 resolution record not found or missing layout_primary_ref for run={run_id}, version={document_version_id}"
        )

    logger.info(
        "V2: Canonical bypass activated for extract",
        document_id=document_id,
        layout_primary_ref=res_record.layout_primary_ref,
    )

    page_count = 1
    try:
        canonical_path = _s3_ref_to_store_path(res_record.canonical_layout_ref, store.bucket)
        canonical_json = store.get_json(canonical_path)
        page_count = int(canonical_json.get("page_count", 1))
    except Exception:
        pass

    await update_extraction_result(
        document_version_id=document_version_id,
        document_id=document_id,
        raw_ref=res_record.canonical_layout_ref,
        primary_ref=res_record.layout_primary_ref,
        page_count=page_count,
        strategy="canonical_filtered_layout_v2",
        ocr_confidence=1.0,
        db=db,
    )
    await db.commit()

    duration = time.time() - start_time

    return {
        "status": DocumentStatus.EXTRACTED.value,
        "document_id": document_id,
        "document_version_id": document_version_id,
        "elements": 0,
        "tables": 0,
        "pages": page_count,
        "strategy": "canonical_filtered_layout_v2",
        "duration_seconds": round(duration, 2),
        "raw_ref": res_record.canonical_layout_ref,
        "layout_primary_ref": res_record.layout_primary_ref,
        "tenant_id": tenant_id,
        "committed": True,
        "analysis_source_kind": "canonical_filtered_layout_v2",
    }
