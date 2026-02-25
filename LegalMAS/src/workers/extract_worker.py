"""
Extract Worker — production (async worker API preserved).

Extracts text and tables from a PDF document stored in MinIO.

Features:
  - Strategy detection per page: text / OCR / hybrid
  - pdfplumber for native-text PDFs
  - Tesseract OCR for scanned pages (graceful fallback if not installed)
  - Table extraction
  - Deterministic element IDs (SHA-256 based, reproducible)
  - Quarantine: 0 elements | low OCR confidence | parse errors
  - Structured logging with deal_id / document_id context
  - Triggers PII Sanitizer on success

textlayoutraw schema produced: see src.services.pdf_extractor.build_text_layout_raw
NOTE: element.clause_uid is null at this stage — set by Structure Builder (Stage 6).
"""

import time
import uuid

from src.core.constants import DocumentStatus
from src.core.exceptions import PermanentError, QuarantineError
from src.core.logging import get_logger
from src.core.config import settings
from src.queue.async_helpers import run_async
from src.db.session import get_session
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.services.pdf_extractor import (
    ExtractionResult,
    build_text_layout_raw,
    extract_pdf,
)
from src.storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.extract_document",
    track_job=False,
    queue="default",
)
async def extract_document(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
) -> dict:
    """
    Async entrypoint kept for compatibility with existing pipeline/tests.

    Thin async wrapper around _extract_document_async which implements
    full Stage 4 extraction logic.
    """
    return await _extract_document_async(
        document_version_id=document_version_id,
        document_id=document_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
    )


async def _extract_document_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
) -> dict:
    """Extract text and tables from PDF and produce textlayoutraw artifact."""
    logger.info(
        "Starting extraction",
        document_id=document_id,
        version_id=document_version_id,
    )
    start_time = time.time()
    store = ArtifactStore(settings)

    # 1. Load original PDF from MinIO
    original_ref = await get_original_ref(document_version_id)
    if not original_ref:
        raise PermanentError(f"No originalref for version {document_version_id}")

    s3_path = original_ref.replace(f"s3://{store.bucket}/", "")
    pdf_bytes = store.get_file(s3_path)

    # 2. Extract (Stage 4 PDF extractor: text / OCR / hybrid + tables)
    extraction: ExtractionResult = extract_pdf(pdf_bytes, document_id)

    # 3. Quarantine check
    _check_quarantine(extraction, document_id)

    # 4. Build textlayoutraw JSON (clause_uid = null at this stage)
    text_layout_raw = build_text_layout_raw(
        extraction,
        document_id=document_id,
        document_version_id=document_version_id,
    )

    # 5. Upload to MinIO
    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    raw_ref = store.put_json(raw_path, text_layout_raw)

    # 6. Update DB
    await update_extraction_result(
        document_version_id=document_version_id,
        document_id=document_id,
        raw_ref=raw_ref,
        page_count=extraction.page_count,
        strategy=extraction.strategy,
        ocr_confidence=extraction.avg_ocr_confidence,
    )

    duration = time.time() - start_time
    logger.info(
        "Extraction complete",
        document_id=document_id,
        elements=len(extraction.elements),
        tables=len(extraction.tables),
        pages=extraction.page_count,
        strategy=extraction.strategy,
        ocr_confidence=round(extraction.avg_ocr_confidence, 3),
        duration_seconds=round(duration, 2),
    )

    # 7. Trigger PII Sanitizer (Stage 5)
    if not settings.DISABLE_DOWNSTREAM_TASKS:
        from src.workers.pii_sanitizer import sanitize_document

        sanitize_document.delay(
            document_version_id=document_version_id,
            document_id=document_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
        )


    return {
        "document_id": document_id,
        "elements": len(extraction.elements),
        "tables": len(extraction.tables),
        "pages": extraction.page_count,
        "strategy": extraction.strategy,
        "duration_seconds": round(duration, 2),
    }


def _check_quarantine(extraction: ExtractionResult, document_id: str) -> None:
    """Raise QuarantineError if extraction results are below quality thresholds."""
    # Parse errors + no elements
    if extraction.errors and not extraction.elements:
        raise QuarantineError(
            f"PDF extraction failed: {'; '.join(extraction.errors)}",
            document_id=document_id,
            reason="extraction_failed",
        )

    # 0 elements at all
    if not extraction.elements:
        raise QuarantineError(
            "No text extracted from PDF — 0 elements",
            document_id=document_id,
            reason="no_text_extracted",
        )

    # Low OCR confidence for OCR/hybrid strategies
    if extraction.strategy in ("ocr", "hybrid") and (
        extraction.avg_ocr_confidence < settings.EXTRACTION_OCR_QUARANTINE_THRESHOLD
    ):
        raise QuarantineError(
            (
                f"OCR confidence too low: "
                f"{extraction.avg_ocr_confidence:.2f} < "
                f"threshold {settings.EXTRACTION_OCR_QUARANTINE_THRESHOLD}"
            ),
            document_id=document_id,
            reason="ocr_low_confidence",
            details={
                "avg_confidence": extraction.avg_ocr_confidence,
                "threshold": settings.EXTRACTION_OCR_QUARANTINE_THRESHOLD,
            },
        )


async def get_original_ref(document_version_id: str) -> str | None:
    from src.db.repositories import DocumentVersionRepository

    async with get_session() as session:
        repo = DocumentVersionRepository(session)
        version = await repo.get_by_id(uuid.UUID(document_version_id))
        return version.original_ref if version else None


async def update_extraction_result(
    document_version_id: str,
    document_id: str,
    raw_ref: str,
    page_count: int,
    strategy: str,
    ocr_confidence: float,
) -> None:
    from src.db.repositories import DocumentRepository, DocumentVersionRepository

    async with get_session() as session:
        ver_repo = DocumentVersionRepository(session)
        doc_repo = DocumentRepository(session)

        await ver_repo.update_refs(
            uuid.UUID(document_version_id),
            raw_ref=raw_ref,
            extraction_strategy=strategy,
            ocr_confidence=ocr_confidence,
        )

        await doc_repo.update_status(
            uuid.UUID(document_id),
            DocumentStatus.EXTRACTED.value,
            page_count=page_count,
        )
