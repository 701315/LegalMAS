# src/workers/extract_worker.py

"""
Extract Worker — извлечение текста и таблиц из PDF, сохранённых в MinIO.

Позиция в пайплайне:
- Пайплайн: import → build_primary_language_source → extract → pii → structure → classify → run_deal_checks.
- На вход получает одноязычный документ (PDF) и создаёт артефакты text_layout_raw и layout_primary.

Что делает воркер:
- Читает исходный PDF из MinIO (приоритетно по ссылке primary_source_ref, затем converted_pdf_ref
  или original_ref из DocumentVersion).
- Определяет стратегию извлечения (native text / OCR / гибрид).
- Строит структуру text_layout_raw (элементы и таблицы) и сохраняет её в MinIO.
- layout_primary сейчас совпадает с text_layout_raw (языковая нормализация выполняется до extract).
- При низком качестве извлечения или ошибках отправляет документ в карантин.
- При успехе обновляет статус документа до EXTRACTED и запускает PII‑санитизацию.
"""

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.ops.metrics import METRICS
from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, QuarantineError
from core.logging import get_logger
from db.repositories import DocumentRepository, DocumentVersionRepository
from db.uow import db_uow, UnitOfWork
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.pdf_extractor import (
    ExtractionResult,
    build_text_layout_raw,
    extract_pdf,
)
from storage.artifact_store import ArtifactPath, ArtifactStore
from services.extraction_quality import (
    ExtractionQualityPolicy,
    evaluate_extraction_quality,
)
logger = get_logger(__name__)


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
) -> dict:
    """
    Celery-обёртка вокруг асинхронной функции извлечения.

    Здесь только управление транзакцией и обработка ошибок.
    Вся бизнес-логика лежит в _extract_document_async.
    """

    async def _wrapper() -> dict:
        async with db_uow() as uow:
            try:
                return await _extract_document_async(
                    document_version_id=document_version_id,
                    document_id=document_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    db=uow.session,
                    run_id=run_id,
                )
            except PermanentError as e:
                logger.error(
                    "Permanent error during extraction",
                    document_id=document_id,
                    version_id=document_version_id,
                    error=str(e),
                )
                async with db_uow() as uow_status:
                    await _mark_failed(
                        uow_status,
                        document_uuid=uuid.UUID(document_id),
                        message=str(e),
                        run_id=uuid.UUID(run_id) if run_id else None,
                    )
                return {
                    "status": DocumentStatus.FAILED.value,
                    "document_id": document_id,
                    "error": str(e),
                }
            except QuarantineError as e:
                logger.error(
                    "Quarantine error during extraction",
                    document_id=document_id,
                    version_id=document_version_id,
                    error=str(e),
                )
                async with db_uow() as uow_status:
                    await _mark_quarantine(
                        uow_status,
                        document_uuid=uuid.UUID(document_id),
                        error=e,
                        run_id=uuid.UUID(run_id) if run_id else None,
                    )
                return {
                    "status": DocumentStatus.QUARANTINE.value,
                    "document_id": document_id,
                    "error": str(e),
                }

    return run_async(_wrapper())


async def _extract_document_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,
) -> dict:
    """
    Основная бизнес-логика извлечения текста и таблиц из PDF.

    Предполагается, что к этому моменту build_primary_language_source уже подготовил
    одноязычный PDF и записал его в primary_source_ref.
    """

    logger.info(
        "Starting extraction",
        document_id=document_id,
        version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    start_time = time.time()
    store = ArtifactStore(settings)

    # 1. Чтение PDF из MinIO с учётом primary_source_ref / converted_pdf_ref / original_ref
    try:
        pdf_ref = await get_pdf_source_ref(document_version_id, db)
        logger.info(
            "Extract: pdf_ref resolved",
            document_id=document_id,
            version_id=document_version_id,
            pdf_ref=pdf_ref,
        )

        if not pdf_ref:
            raise PermanentError(
                f"No PDF source ref for version {document_version_id} "
                f"(none of primary_source_ref, converted_pdf_ref, original_ref is set)"
            )

        s3_path = pdf_ref.replace(f"s3://{store.bucket}/", "")
        logger.info(
            "Extract: reading PDF from store",
            document_id=document_id,
            version_id=document_version_id,
            s3_path=s3_path,
        )

        pdf_bytes = store.get_file(s3_path)
        logger.info(
            "Extract: PDF bytes loaded",
            document_id=document_id,
            version_id=document_version_id,
            size=len(pdf_bytes),
        )
    except Exception as e:
        logger.exception(
            "Extract: failed to read PDF from store",
            document_id=document_id,
            version_id=document_version_id,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to read PDF from store: {e}",
            details={"stage": "extract", "kind": "storage_read_error"},
        )

    # 2. Extract (native/OCR/hybrid + tables)
    try:
        extraction: ExtractionResult = extract_pdf(pdf_bytes, document_id)
        logger.info(
            "Extract: pdf parsed",
            document_id=document_id,
            version_id=document_version_id,
            elements=len(extraction.elements),
            tables=len(extraction.tables),
            pages=extraction.page_count,
            strategy=extraction.strategy,
        )
    except Exception as e:
        logger.exception(
            "Extract: extract_pdf failed",
            document_id=document_id,
            version_id=document_version_id,
            error=str(e),
        )
        raise PermanentError(f"extract_pdf failed: {e}")

    # 3. Extraction quality policy
    quality_decision = evaluate_extraction_quality(
        extraction,
        policy=ExtractionQualityPolicy(
            ocr_quarantine_threshold=settings.EXTRACTION_OCR_QUARANTINE_THRESHOLD,
            hybrid_min_ocr_rate_for_quarantine=(
                settings.EXTRACTION_HYBRID_MIN_OCR_RATE_FOR_QUARANTINE
            ),
        ),
    )

    logger.info(
        "Extract: quality decision evaluated",
        document_id=document_id,
        version_id=document_version_id,
        outcome=quality_decision.outcome,
        reason=quality_decision.reason,
        details=quality_decision.details,
    )

    if quality_decision.outcome == "failed":
        raise PermanentError(quality_decision.message)

    if quality_decision.outcome == "quarantine":
        METRICS.quarantine.labels(
            reason=quality_decision.reason or "unknown"
        ).inc()
        raise QuarantineError(
            quality_decision.message,
            document_id=document_id,
            reason=quality_decision.reason or "unknown",
            details=quality_decision.details,
        )

    # 4. Build text_layout_raw JSON (clause_uid = null at this stage)
    text_layout_raw = build_text_layout_raw(
        extraction,
        document_id=document_id,
        document_version_id=document_version_id,
    )

    # Вариант А: языковая нормализация выполняется на шаге build_primary_language_source.
    # Здесь мы не определяем языки и не фильтруем layout.
    # Для downstream-совместимости layout_primary = text_layout_raw.
    layout_primary = text_layout_raw

    # 5. Upload to MinIO
    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    raw_ref = store.put_json(raw_path, text_layout_raw)

    primary_path = ArtifactPath.layout_primary(tenant_id, deal_id, document_id)
    primary_ref = store.put_json(primary_path, layout_primary)

    # 6. Update DB
    await update_extraction_result(
        document_version_id=document_version_id,
        document_id=document_id,
        raw_ref=raw_ref,
        primary_ref=primary_ref,
        page_count=extraction.page_count,
        strategy=extraction.strategy or "text",
        ocr_confidence=(
            float(extraction.avg_ocr_confidence)
            if extraction.avg_ocr_confidence is not None
            else None
        ),
        db=db,
    )

    duration = time.time() - start_time

    page_strategies = extraction.page_strategies or {}
    ocr_page_count = sum(1 for s in page_strategies.values() if s == "ocr")
    ocr_rate = round(ocr_page_count / max(extraction.page_count or 0, 1), 3)

    logger.info(
        "Extraction complete",
        document_id=document_id,
        version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        elements=len(extraction.elements),
        tables=len(extraction.tables),
        pages=extraction.page_count,
        strategy=extraction.strategy,
        ocr_confidence=(
            round(extraction.avg_ocr_confidence, 3)
            if extraction.avg_ocr_confidence is not None
            else None
        ),
        ocr_rate=ocr_rate,
        duration_seconds=round(duration, 2),
    )

    METRICS.extraction_duration.labels(
        strategy=extraction.strategy,
    ).observe(duration)

    METRICS.extraction_pages.labels(
        strategy=extraction.strategy,
    ).inc(extraction.page_count)

    if extraction.avg_ocr_confidence is not None and extraction.strategy in ("ocr", "hybrid"):
        METRICS.extraction_ocr_confidence.observe(extraction.avg_ocr_confidence)

    if not settings.DISABLE_DOWNSTREAM_TASKS:
        from mas_queue.celery_app import celery_app as _celery

        _celery.send_task(
            "pii.sanitize_document",
            kwargs={
                "document_version_id": document_version_id,
            },
        )

    return {
        "document_id": document_id,
        "elements": len(extraction.elements),
        "tables": len(extraction.tables),
        "pages": extraction.page_count,
        "strategy": extraction.strategy,
        "duration_seconds": round(duration, 2),
    }


async def get_pdf_source_ref(
    document_version_id: str,
    db: AsyncSession,
) -> str | None:
    """
    Получить ссылку на PDF-источник для извлечения.

    Новый приоритет:
    - если у версии есть primary_source_ref (одноязычный source) — используем его;
    - иначе, если есть converted_pdf_ref (DOCX/DOC → PDF) — используем его;
    - иначе используем original_ref (исходный PDF).
    """
    repo = DocumentVersionRepository(db)
    version = await repo.get_by_id(uuid.UUID(document_version_id))
    if not version:
        return None

    if getattr(version, "primary_source_ref", None):
        return version.primary_source_ref

    if getattr(version, "converted_pdf_ref", None):
        return version.converted_pdf_ref

    return version.original_ref


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

    Контракт пайплайна:
    - raw_ref хранит технический snapshot layout после extract;
    - layout_primary_ref — единственный downstream layout после extract;
    - все следующие стадии (PII, structure, content/chunks, checks) должны
      использовать именно layout_primary_ref, а не raw_ref.
    """
    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)

    version_uuid = uuid.UUID(document_version_id)
    version = await ver_repo.get_by_id(version_uuid)

    pipeline_strategy: str | None = None
    origin_filetype = getattr(version, "origin_filetype", None) if version else None
    normalized_strategy = (strategy or "text").lower()

    if origin_filetype:
        if origin_filetype == "pdf":
            if normalized_strategy == "text":
                pipeline_strategy = "pdf_native"
            elif normalized_strategy == "ocr":
                pipeline_strategy = "pdf_ocr"
            elif normalized_strategy == "hybrid":
                pipeline_strategy = "pdf_hybrid"
        elif origin_filetype == "docx":
            if normalized_strategy == "text":
                pipeline_strategy = "docx_via_pdf_native"
            elif normalized_strategy == "ocr":
                pipeline_strategy = "docx_via_pdf_ocr"
            elif normalized_strategy == "hybrid":
                pipeline_strategy = "docx_via_pdf_hybrid"


    await ver_repo.update_refs(
        version_uuid,
        raw_ref=raw_ref,
        layout_primary_ref=primary_ref,
        extraction_strategy=normalized_strategy,
        ocr_confidence=ocr_confidence,
        pipeline_strategy=pipeline_strategy,
    )

    await doc_repo.update_status(
        uuid.UUID(document_id),
        DocumentStatus.EXTRACTED.value,
        page_count=page_count,
        processing_error_details=None,
    )


async def _mark_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    message: str,
    run_id: uuid.UUID | None,
    error: PermanentError | None = None,
) -> None:
    """Перевести документ в статус FAILED для стадии extract."""
    repo = DocumentRepository(uow.session)
    reason = getattr(error, "details", {}).get("kind") if error else "extraction_error"
    await repo.set_failed(
        document_uuid,
        stage="extract",
        message=message,
        reason=reason,
        run_id=run_id,
    )


async def _mark_quarantine(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    error: QuarantineError,
    run_id: uuid.UUID | None,
) -> None:
    """Перевести документ в статус QUARANTINE для стадии extract."""
    repo = DocumentRepository(uow.session)
    reason = getattr(error, "reason", None)
    msg = str(error)
    await repo.set_quarantined(
        document_uuid,
        stage="extract",
        message=msg,
        reason=reason,
        run_id=run_id,
    )
    