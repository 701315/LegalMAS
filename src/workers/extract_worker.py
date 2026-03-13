# src/workers/extract_worker.py

"""
Extract Worker — извлечение текста и таблиц из PDF, сохранённых в MinIO.

Позиция в пайплайне:
- Импорт → extract → pii → structure → classify → run_checks.
- На вход получает документ (PDF) и создаёт артефакт textlayoutraw.

Что делает воркер:
- Читает исходный PDF из MinIO (по ссылке original_ref или converted_pdf_ref из DocumentVersion).
- Определяет стратегию извлечения (native text / OCR / гибрид).
- Строит структуру textlayoutraw (элементы и таблицы) и сохраняет её в MinIO.
- При низком качестве извлечения или ошибках отправляет документ в карантин.
- При успехе обновляет статус документа до EXTRACTED и запускает PII‑санитизацию.

Архитектура:
- Внешняя Celery‑таска extract_document — синхронная (def), её вызывает Celery.
- Внутри таски один раз происходит переход sync → async через run_async.
- Вся логика работы с БД и MinIO сосредоточена в _extract_document_async()
  и вспомогательных async‑функциях под управлением db_uow(), без ручного
  управления event loop.
- Метрики производительности и качества извлечения пишутся в Prometheus
  через глобальный реестр METRICS.
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
    Sync Celery entrypoint.

    Новый архитектурный паттерн:
    - Celery вызывает синхронную функцию.
    - Внутри мы один раз передаём управление в async‑мир через run_async.
    - Весь async‑код (БД, MinIO и т.п.) живёт в _extract_document_async()
      и вспомогательных async‑функциях под db_uow().
    """

    async def _wrapper() -> dict:
        # Основной unit of work для извлечения
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
                # Отдельный UoW только для записи статуса FAILED + деталей
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
                # Отдельный UoW только для записи статуса QUARANTINE + деталей
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

    # Запускаем async‑обёртку через общий мост run_async
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
    Extract text and tables from PDF and produce textlayoutraw artifact.

    Все операции с БД выполняются через переданную AsyncSession (db),
    чтобы одна задача worker'а работала в рамках одного unit of work.
    """
    logger.info(
        "Starting extraction",
        document_id=document_id,
        version_id=document_version_id,
    )
    start_time = time.time()
    store = ArtifactStore(settings)

    # --- ИЗМЕНЕНО: вместо original_ref берём единый PDF‑source ---
    pdf_ref = await get_pdf_source_ref(document_version_id, db)
    if not pdf_ref:
        # Если нет ни converted_pdf_ref, ни original_ref, это фатальная ошибка конфигурации.
        raise PermanentError(
            f"No PDF source ref for version {document_version_id} "
            f"(neither converted_pdf_ref nor original_ref is set)"
        )

    # pdf_ref может быть как полным s3://..., так и относительным путём.
    s3_path = pdf_ref.replace(f"s3://{store.bucket}/", "")
    pdf_bytes = store.get_file(s3_path)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

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

    # 6. Update DB (используем ту же сессию db)
    await update_extraction_result(
        document_version_id=document_version_id,
        document_id=document_id,
        raw_ref=raw_ref,
        page_count=extraction.page_count,
        strategy=extraction.strategy,
        ocr_confidence=extraction.avg_ocr_confidence,
        db=db,
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

    # --- Метрики извлечения ---
    METRICS.extraction_duration.labels(
        strategy=extraction.strategy,
    ).observe(duration)

    METRICS.extraction_pages.labels(
        strategy=extraction.strategy,
    ).inc(extraction.page_count)

    if extraction.strategy == "ocr" and extraction.avg_ocr_confidence is not None:
        METRICS.extraction_ocr_confidence.observe(extraction.avg_ocr_confidence)

    # 7. Trigger PII Sanitizer (Stage 5)
    if not settings.DISABLE_DOWNSTREAM_TASKS:
        from mas_queue.celery_app import celery_app as _celery  # на случай циклов импорта

        # Запускаем таску по строковому имени, без прямого импорта workers.pii_sanitizer,
        # чтобы избежать циклических зависимостей между воркерами.
        _celery.send_task(
            "pii.sanitize_document",
            kwargs={
                "document_version_id": document_version_id,
                "document_id": document_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
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


def _check_quarantine(extraction: ExtractionResult, document_id: str) -> None:
    """Raise QuarantineError if extraction results are below quality thresholds."""
    # Parse errors + no elements
    if extraction.errors and not extraction.elements:
        METRICS.quarantine.labels(reason="extraction_failed").inc()
        raise QuarantineError(
            f"PDF extraction failed: {'; '.join(extraction.errors)}",
            document_id=document_id,
            reason="extraction_failed",
        )

    # 0 elements at all
    if not extraction.elements:
        METRICS.quarantine.labels(reason="no_text_extracted").inc()
        raise QuarantineError(
            "No text extracted from PDF — 0 elements",
            document_id=document_id,
            reason="no_text_extracted",
        )

    # Low OCR confidence for OCR/hybrid strategies
    if extraction.strategy in ("ocr", "hybrid") and (
        extraction.avg_ocr_confidence
        < settings.EXTRACTION_OCR_QUARANTINE_THRESHOLD
    ):
        METRICS.quarantine.labels(reason="ocr_low_confidence").inc()
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


# --- НОВОЕ ---
async def get_pdf_source_ref(
    document_version_id: str,
    db: AsyncSession,
) -> str | None:
    """
    Получить ссылку на PDF-источник для извлечения.

    Логика:
    - если у версии есть converted_pdf_ref (DOCX/DOC → PDF), используем его;
    - иначе используем original_ref (исходный PDF).

    Работает через переданную AsyncSession, не создаёт собственных сессий.
    """
    repo = DocumentVersionRepository(db)
    version = await repo.get_by_id(uuid.UUID(document_version_id))
    if not version:
        return None

    # Если документ был конвертирован из офисного формата, используем PDF после конвертации.
    if getattr(version, "converted_pdf_ref", None):
        return version.converted_pdf_ref

    # По умолчанию — исходный PDF.
    return version.original_ref
# --- КОНЕЦ НОВОГО ---


async def update_extraction_result(
    document_version_id: str,
    document_id: str,
    raw_ref: str,
    page_count: int,
    strategy: str,
    ocr_confidence: float,
    db: AsyncSession,
) -> None:
    """
    Обновить результаты извлечения в БД (version + document).

    Работает через переданную AsyncSession в рамках одного unit of work.
    """
    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)

    version_uuid = uuid.UUID(document_version_id)
    version = await ver_repo.get_by_id(version_uuid)

    # Вычисляем pipeline_strategy на основе origin_filetype + стратегии извлечения
    pipeline_strategy: str | None = None
    origin_filetype = getattr(version, "origin_filetype", None) if version else None

    if origin_filetype:
        if origin_filetype == "pdf":
            if strategy == "native":
                pipeline_strategy = "pdf_native"
            elif strategy == "ocr":
                pipeline_strategy = "pdf_ocr"
            elif strategy == "hybrid":
                pipeline_strategy = "pdf_hybrid"
        elif origin_filetype == "docx":
            if strategy == "native":
                pipeline_strategy = "docx_via_pdf_native"
            elif strategy == "ocr":
                pipeline_strategy = "docx_via_pdf_ocr"
            elif strategy == "hybrid":
                pipeline_strategy = "docx_via_pdf_hybrid"

    await ver_repo.update_refs(
        version_uuid,
        raw_ref=raw_ref,
        extraction_strategy=strategy,
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
) -> None:
    """
    Отдельный простой UoW для перевода документа в статус FAILED
    с заполнением processing_error_details.
    """
    repo = DocumentRepository(uow.session)
    await repo.set_failed(
        document_uuid,
        stage="extract",
        message=message,
        reason="extraction_error",
        run_id=run_id,
    )


async def _mark_quarantine(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    error: QuarantineError,
    run_id: uuid.UUID | None,
) -> None:
    """
    Отдельный простой UoW для перевода документа в QUARANTINE
    с заполнением processing_error_details.
    """
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


#async def get_original_ref(
#    document_version_id: str,
#    db: AsyncSession,
#) -> str | None:
#    """
#    Получить ссылку на исходный PDF (original_ref) для версии документа.
#
#    Работает через переданную AsyncSession, не создаёт собственных сессий.
#    """
#    repo = DocumentVersionRepository(db)
#    version = await repo.get_by_id(uuid.UUID(document_version_id))
#    return version.original_ref if version else None