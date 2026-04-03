# src/workers/extract_worker.py
"""
Extract Worker — извлечение текста и таблиц из PDF, сохранённых в MinIO.

Позиция в пайплайне:
- Пайплайн: import → extract → pii → structure → classify → run_deal_checks.
- На вход получает документ (PDF) и создаёт артефакт text_layout_raw.

Что делает воркер:
- Читает исходный PDF из MinIO (по ссылке original_ref или converted_pdf_ref из DocumentVersion).
- Определяет стратегию извлечения (native text / OCR / гибрид).
- Строит структуру text_layout_raw (элементы и таблицы) и сохраняет её в MinIO.
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
from services.layout_language_filter import (
    detect_languages_in_layout,
    filter_layout_to_language,
)
from services.deal_language_service import update_deal_languages
from db.repositories.deal_repo import DealRepository

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
    Extract text and tables from PDF and produce text_layout_raw artifact.

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

    # --- Чтение PDF из MinIO с защитой и логами ---
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
                f"(neither converted_pdf_ref nor original_ref is set)"
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
        raise PermanentError(f"Failed to read PDF from store: {e}")
    # --- КОНЕЦ БЛОКА ЧТЕНИЯ PDF ---

    # 2. Extract (Stage 4 PDF extractor: text / OCR / hybrid + tables)
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

    # 3. Quarantine check
    _check_quarantine(extraction, document_id)

    # 4. Build text_layout_raw JSON (clause_uid = null at this stage)
    text_layout_raw = build_text_layout_raw(
        extraction,
        document_id=document_id,
        document_version_id=document_version_id,
    )

    # 4.1. Определяем фактические языки по исходному layout (multi-lang).
    detected_langs = detect_languages_in_layout(text_layout_raw)
    await update_deal_languages(
        db=db,
        deal_id=uuid.UUID(deal_id),
        new_languages=detected_langs,
    )

    # 4.2. Выбираем целевой язык для layout_primary.
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(uuid.UUID(deal_id))

    primary = (getattr(deal, "primary_language", None) or "").lower()
    langs_from_deal = [
        (l or "").lower()
        for l in (getattr(deal, "languages", None) or [])
        if (l or "").strip()
    ]

    target_lang: str | None = None

    # 1) Явный primary_language сделки, если он реально найден в документе
    if primary and primary in detected_langs:
        target_lang = primary

    # 2) Первый язык сделки, который реально найден в документе
    if not target_lang:
        for lang in langs_from_deal:
            if lang in detected_langs:
                target_lang = lang
                break

    # 3) Доминирующий язык документа
    if not target_lang and detected_langs:
        target_lang = detected_langs[0]

    # 4) Явный fallback контракта пайплайна
    if not target_lang:
        target_lang = primary or (langs_from_deal[0] if langs_from_deal else "ru")

    # 4.3. Языковая фильтрация layout.
    #
    # is_bilingual определяем здесь, а не внутри filter_layout_to_language,
    # чтобы у extract_worker была та же картина, что у фильтра.
    is_bilingual = len(detected_langs) >= 2

    filter_context = {
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "document_id": document_id,
        "is_bilingual": is_bilingual,
    }
    layout_primary = filter_layout_to_language(
        text_layout_raw, target_lang, context=filter_context
    )

    # 4.4. Оценка качества одноязычного layout относительно исходного.
    #
    # Передаём is_bilingual чтобы пороги degraded учитывали тип документа:
    # - для билингвального документа ~50% элементов — это норма (один язык из двух);
    # - для монолингвального 50% элементов — это уже деградация.
    quality = _evaluate_primary_layout_quality(
        text_layout_raw, layout_primary, is_bilingual=is_bilingual
    )

    if not (layout_primary.get("elements") or []):
        logger.warning(
            "Primary layout is empty after language filter, falling back to raw layout",
            document_id=document_id,
            version_id=document_version_id,
            target_lang=target_lang,
        )
        layout_primary = text_layout_raw
    else:
        # Записываем диагностику внутрь metadata layout_primary
        metadata = dict(layout_primary.get("metadata") or {})
        lf_meta = dict(metadata.get("language_filter") or {})
        lf_meta.update(
            {
                "target_language": target_lang,
                "elements_before": quality["elements_before"],
                "elements_after": quality["elements_after"],
                "chars_before": quality["chars_before"],
                "chars_after": quality["chars_after"],
                "element_retention_ratio": quality["element_retention_ratio"],
                "char_retention_ratio": quality["char_retention_ratio"],
                "degraded": quality["degraded"],
                "degraded_reason": quality["degraded_reason"],
            }
        )
        metadata["language_filter"] = lf_meta
        layout_primary["metadata"] = metadata

        if quality["degraded"]:
            logger.warning(
                "Primary layout marked as degraded after language filter",
                document_id=document_id,
                version_id=document_version_id,
                target_lang=target_lang,
                element_retention_ratio=quality["element_retention_ratio"],
                char_retention_ratio=quality["char_retention_ratio"],
                degraded_reason=quality["degraded_reason"],
                is_bilingual=is_bilingual,
            )

    # 5. Upload to MinIO

    # 5.1. Полный многоязычный layout_raw (для отладки и fallback)
    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    raw_ref = store.put_json(raw_path, text_layout_raw)

    # 5.2. Одноязычный layout_primary (под выбранный язык)
    primary_path = ArtifactPath.layout_primary(tenant_id, deal_id, document_id)
    primary_ref = store.put_json(primary_path, layout_primary)

    # 6. Update DB (используем ту же сессию db)
    await update_extraction_result(
        document_version_id=document_version_id,
        document_id=document_id,
        raw_ref=raw_ref,
        primary_ref=primary_ref,
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
        target_lang=target_lang,
        is_bilingual=is_bilingual,
        element_retention_ratio=round(quality["element_retention_ratio"], 3),
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


def _check_quarantine(extraction: ExtractionResult, document_id: str) -> None:
    """Raise QuarantineError if extraction results are below quality thresholds."""
    if extraction.errors and not extraction.elements:
        METRICS.quarantine.labels(reason="extraction_failed").inc()
        raise QuarantineError(
            f"PDF extraction failed: {'; '.join(extraction.errors)}",
            document_id=document_id,
            reason="extraction_failed",
        )

    if not extraction.elements:
        METRICS.quarantine.labels(reason="no_text_extracted").inc()
        raise QuarantineError(
            "No text extracted from PDF — 0 elements",
            document_id=document_id,
            reason="no_text_extracted",
        )

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


def _evaluate_primary_layout_quality(
    raw_layout: dict,
    primary_layout: dict,
    is_bilingual: bool = False,
) -> dict:
    """
    Оценить качество layout_primary относительно исходного text_layout_raw.

    Возвращает словарь с полями:
    - elements_before / elements_after
    - chars_before / chars_after
    - element_retention_ratio
    - char_retention_ratio
    - degraded (bool)
    - degraded_reason (str | None)

    Пороги degraded зависят от типа документа:

    Монолингвальный документ:
      - Нормальный фильтр оставляет >80% элементов (убирает только шум).
      - Порог degraded: элементов < 60%, символов < 65%.

    Билингвальный документ (is_bilingual=True):
      - Нормальный фильтр оставляет ~50% элементов (один язык из двух).
      - Пороги должны быть ниже, иначе все двуязычные документы будут degraded.
      - Порог degraded: элементов < 20%, символов < 25%.
      - Почему 20%: если осталось меньше 1/5 от исходного — что-то точно сломалось
        (например, неверно определён целевой язык или фильтр упал в fallback
        и оставил только нейтральные блоки).
    """
    raw_elements = raw_layout.get("elements") or []
    prim_elements = primary_layout.get("elements") or []

    elements_before = len(raw_elements)
    elements_after = len(prim_elements)

    def _count_chars(text: str) -> int:
        return len((text or "").replace(" ", "").replace("\n", ""))

    chars_before = sum(_count_chars(el.get("text") or "") for el in raw_elements)
    chars_after = sum(_count_chars(el.get("text") or "") for el in prim_elements)

    elem_ratio = (elements_after / elements_before) if elements_before else 0.0
    char_ratio = (chars_after / chars_before) if chars_before else 0.0

    # Выбираем пороги в зависимости от типа документа
    if is_bilingual:
        # Для билингвального: нормально потерять ~50%, критично потерять >80%
        elem_threshold = 0.20
        char_threshold = 0.25
    else:
        # Для монолингвального: должно оставаться большинство элементов
        elem_threshold = 0.60
        char_threshold = 0.65

    degraded = False
    reason: str | None = None

    if elem_ratio < elem_threshold:
        degraded = True
        reason = (
            f"too_few_elements_retained:{elem_ratio:.2f}"
            f"(threshold={'bilingual' if is_bilingual else 'monolingual'}:{elem_threshold})"
        )
    elif char_ratio < char_threshold:
        degraded = True
        reason = (
            f"too_few_chars_retained:{char_ratio:.2f}"
            f"(threshold={'bilingual' if is_bilingual else 'monolingual'}:{char_threshold})"
        )

    return {
        "elements_before": elements_before,
        "elements_after": elements_after,
        "chars_before": chars_before,
        "chars_after": chars_after,
        "element_retention_ratio": elem_ratio,
        "char_retention_ratio": char_ratio,
        "degraded": degraded,
        "degraded_reason": reason,
    }


async def get_pdf_source_ref(
    document_version_id: str,
    db: AsyncSession,
) -> str | None:
    """
    Получить ссылку на PDF-источник для извлечения.

    Логика:
    - если у версии есть converted_pdf_ref (DOCX/DOC → PDF), используем его;
    - иначе используем original_ref (исходный PDF).
    """
    repo = DocumentVersionRepository(db)
    version = await repo.get_by_id(uuid.UUID(document_version_id))
    if not version:
        return None

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
    ocr_confidence: float,
    db: AsyncSession,
) -> None:
    """
    Обновить результаты извлечения в БД (version + document).

    Контракт пайплайна:
    - raw_ref хранит технический multi-language snapshot после extract;
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
        layout_primary_ref=primary_ref,
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
