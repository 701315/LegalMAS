# src/workers/extract_worker.py

# src/workers/extract_worker.py

"""
Extract Worker — извлечение текста и таблиц из PDF, сохранённых в MinIO.


Позиция в пайплайне:
- Пайплайн: import → build_primary_language_source → extract → pii → structure → classify → run_deal_checks.
- На вход получает одноязычный документ (PDF) и создаёт артефакты text_layout_raw и layout_primary.


Что делает воркер:
- Читает PDF из MinIO строго по ссылке primary_source_ref из DocumentVersion.
- Определяет стратегию извлечения (native text / OCR / гибрид).
- Строит структуру text_layout_raw (элементы и таблицы) и сохраняет её в MinIO.
- layout_primary строится из text_layout_raw и при наличии sidecar
  восстанавливает language metadata, потерянную на границе PDF → extract.
- При низком качестве извлечения или ошибках отправляет документ в карантин.
- При успехе обновляет статус документа до EXTRACTED; запуск PII‑санитизации делает оркестратор.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from copy import deepcopy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, QuarantineError, TransientError
from core.logging import get_logger
from core.stage_trace import build_stage_trace_fragment
from db.repositories import AuditRepository, DocumentRepository, DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from ops.metrics import METRICS
from services.extraction_quality import (
    ExtractionQualityPolicy,
    evaluate_extraction_quality,
)
from services.pdf_extractor import (
    ExtractionResult,
    build_text_layout_raw,
    extract_pdf,
)
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


_PRIMARY_LANGUAGE_METADATA_KEYS: tuple[str, ...] = (
    "language_pipeline",
    "language_filter",
)


def _load_primary_language_metadata_sidecar_safe(
    *,
    store: ArtifactStore,
    tenant_id: str,
    deal_id: str,
    document_id: str,
    document_version_id: str,
) -> dict[str, Any] | None:
    """
    Load language metadata sidecar written by build_primary_language_source.

    Failure-isolated by design:
    - missing sidecar must not break extract;
    - malformed sidecar must not break extract.
    """
    sidecar_path = ArtifactPath.primary_source_language_metadata(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
    )

    try:
        payload = store.get_json(sidecar_path)
    except Exception as exc:
        logger.warning(
            "Extract: primary language metadata sidecar unavailable, continuing without it",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            sidecar_path=sidecar_path,
            error=str(exc),
        )
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "Extract: primary language metadata sidecar has invalid format, continuing without it",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            sidecar_path=sidecar_path,
            payload_type=type(payload).__name__,
        )
        return None

    language_metadata: dict[str, Any] = {}
    for key in _PRIMARY_LANGUAGE_METADATA_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            language_metadata[key] = deepcopy(value)

    if not language_metadata:
        logger.warning(
            "Extract: primary language metadata sidecar contains no supported keys, continuing without it",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            sidecar_path=sidecar_path,
        )
        return None

    logger.info(
        "Extract: primary language metadata sidecar loaded",
        document_id=document_id,
        version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        sidecar_path=sidecar_path,
        metadata_keys=sorted(language_metadata.keys()),
    )
    return language_metadata


def _attach_primary_language_metadata(
    *,
    layout: dict[str, Any],
    language_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Build layout_primary from extracted raw layout and optional language metadata.

    Important contract:
    - never mutates the original raw layout object;
    - preserves existing metadata keys;
    - overlays only supported language metadata keys.
    """
    layout_primary = deepcopy(layout)

    if not language_metadata:
        return layout_primary

    existing_metadata = layout_primary.get("metadata")
    merged_metadata = dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
    merged_metadata.update(language_metadata)
    layout_primary["metadata"] = merged_metadata
    return layout_primary


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
    stage_execution_id: str | None = None,      # ← добавить
    orchestration_strategy: str | None = None,  # ← добавить
    **kwargs: Any,                               # ← добавить
) -> dict:
    """
    Celery-обёртка вокруг асинхронной функции извлечения.

    Здесь только управление транзакцией и обработка ошибок.
    Вся бизнес-логика лежит в _extract_document_async.
    """

    async def _wrapper() -> dict:
        resolved_tenant_id = tenant_id

        async with db_uow() as uow:
            try:
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

            except TransientError as e:
                logger.warning(
                    "Transient error during extraction; task should be retried",
                    document_id=document_id,
                    version_id=document_version_id,
                    deal_id=deal_id,
                    tenant_id=resolved_tenant_id,
                    run_id=run_id,
                    error=str(e),
                )
                raise

            except PermanentError as e:
                logger.error(
                    "Permanent error during extraction",
                    document_id=document_id,
                    version_id=document_version_id,
                    deal_id=deal_id,
                    tenant_id=resolved_tenant_id,
                    run_id=run_id,
                    error=str(e),
                )
                async with db_uow() as uow_status:
                    failed_tenant_id = await resolve_artifact_tenant_id(
                        session=uow_status.session,
                        deal_id=deal_id,
                        document_id=document_id,
                        payload_tenant_id=resolved_tenant_id,
                    )
                    await _mark_failed(
                        uow_status,
                        document_uuid=uuid.UUID(document_id),
                        tenant_id=failed_tenant_id,
                        message=str(e),
                        run_id=uuid.UUID(run_id) if run_id else None,
                        error=e,
                    )
                return {
                    "status": DocumentStatus.FAILED.value,
                    "document_id": document_id,
                    "error": str(e),
                    "committed": False,
                }

            except QuarantineError as e:
                logger.error(
                    "Quarantine error during extraction",
                    document_id=document_id,
                    version_id=document_version_id,
                    deal_id=deal_id,
                    tenant_id=resolved_tenant_id,
                    run_id=run_id,
                    error=str(e),
                )
                async with db_uow() as uow_status:
                    failed_tenant_id = await resolve_artifact_tenant_id(
                        session=uow_status.session,
                        deal_id=deal_id,
                        document_id=document_id,
                        payload_tenant_id=resolved_tenant_id,
                    )
                    await _mark_quarantine(
                        uow_status,
                        document_uuid=uuid.UUID(document_id),
                        tenant_id=failed_tenant_id,
                        error=e,
                        run_id=uuid.UUID(run_id) if run_id else None,
                    )
                return {
                    "status": DocumentStatus.QUARANTINE.value,
                    "document_id": document_id,
                    "error": str(e),
                    "committed": False,
                }

    result = run_async(_wrapper())

    if run_id and result.get("committed") is True:
        logger.info(
            "Extraction committed, retriggering run pipeline",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
            run_id=run_id,
            layout_primary_ref=result.get("layout_primary_ref"),
            raw_ref=result.get("raw_ref"),
        )
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
    """
    Основная бизнес-логика извлечения текста и таблиц из PDF.


    Контракт стадии:
    - extract работает только с primary_source_ref;
    - fallback на converted_pdf_ref/original_ref в активном pipeline запрещён;
    - downstream retrigger допустим только после commit артефактов extract.
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

    # Business span для stage extract.
    # Охватывает полный цикл: PDF → extraction → quality check → artifacts → DB commit.
    from contextlib import nullcontext  # noqa: PLC0415
    from core.tracing import get_stage_tracer  # noqa: PLC0415
    _stage_tracer = get_stage_tracer()
    _stage_span_ctx = (
        _stage_tracer.start_as_current_span(
            "stage.extract_document",
            attributes={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "run_id": run_id or "",
            },
        )
        if _stage_tracer else nullcontext()
    )

    with _stage_span_ctx:

        # 1. Чтение исходного PDF строго по primary_source_ref
        try:
            pdf_ref = await get_pdf_source_ref(
                document_version_id=document_version_id,
                db=db,
                require_primary=True,
            )
            logger.info(
                "Extract: pdf_ref resolved",
                document_id=document_id,
                version_id=document_version_id,
                pdf_ref=pdf_ref,
            )

            if not pdf_ref:
                raise PermanentError(
                    f"No PDF source ref for version {document_version_id} "
                    f"(primary_source_ref is required for extract stage)",
                    details={"stage": "extract", "kind": "missing_pdf_ref"},
                )

            s3_path = _s3_ref_to_store_path(pdf_ref, store.bucket)
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

        except TransientError:
            raise

        except PermanentError:
            raise

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

        # 2. Извлечение текста/таблиц
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

            # Обогатить span стратегией извлечения — становится известна после parse.
            try:
                from opentelemetry import trace as _otel_trace  # noqa: PLC0415
                _cur = _otel_trace.get_current_span()
                if _cur and _cur.is_recording():
                    _cur.set_attribute("extraction.strategy", extraction.strategy or "unknown")
                    _cur.set_attribute("extraction.pages", extraction.page_count or 0)
                    _cur.set_attribute("extraction.elements", len(extraction.elements))
            except Exception:  # noqa: BLE001
                pass

        except Exception as e:
            logger.exception(
                "Extract: extract_pdf failed",
                document_id=document_id,
                version_id=document_version_id,
                error=str(e),
            )
            raise PermanentError(
                f"extract_pdf failed: {e}",
                details={"stage": "extract", "kind": "pdf_parse_error"},
            )

        # 3. Политика качества извлечения
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
            raise PermanentError(
                quality_decision.message,
                details={
                    "stage": "extract",
                    "kind": "quality_failed",
                    "reason": quality_decision.reason,
                    "details": quality_decision.details,
                },
            )

        if quality_decision.outcome == "quarantine":
            METRICS.quarantine.labels(reason=quality_decision.reason or "unknown").inc()
            raise QuarantineError(
                quality_decision.message,
                document_id=document_id,
                reason=quality_decision.reason or "unknown",
                details=quality_decision.details,
            )

        # 4. Построение layout-артефактов
        text_layout_raw = build_text_layout_raw(
            extraction,
            document_id=document_id,
            document_version_id=document_version_id,
        )

        language_metadata = _load_primary_language_metadata_sidecar_safe(
            store=store,
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=document_id,
            document_version_id=document_version_id,
        )

        layout_primary = _attach_primary_language_metadata(
            layout=text_layout_raw,
            language_metadata=language_metadata,
        )

        # 5. Сохранение артефактов в storage
        raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
        raw_ref = store.put_json(raw_path, text_layout_raw)

        primary_path = ArtifactPath.layout_primary(tenant_id, deal_id, document_id)
        primary_ref = store.put_json(primary_path, layout_primary)

        # 6. Фиксация результатов в БД
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

        # Важный production-подход:
        # граница успешной записи — commit(), а не проверка "видно ли ref сразу после flush".
        await db.commit()

        # Мягкая post-commit верификация для диагностики — без исключений.
        try:
            ver_repo = DocumentVersionRepository(db)
            refreshed_version = await ver_repo.get_by_id(uuid.UUID(document_version_id))
            refreshed_layout_primary_ref = (
                getattr(refreshed_version, "layout_primary_ref", None) if refreshed_version else None
            )
            refreshed_raw_ref = (
                getattr(refreshed_version, "raw_ref", None) if refreshed_version else None
            )

            if not refreshed_version:
                logger.warning(
                    "Extract: document version not visible immediately after commit; "
                    "next orchestrator pass will validate downstream refs",
                    document_id=document_id,
                    version_id=document_version_id,
                    run_id=run_id,
                )
            else:
                # Жёсткое расхождение: сломан layout_primary_ref или raw_ref изменился на другое ненулевое значение.
                hard_mismatch = refreshed_layout_primary_ref != primary_ref or (
                    refreshed_raw_ref is not None and refreshed_raw_ref != raw_ref
                )

                # При необходимости даём БД шанс догнать raw_ref.
                if refreshed_layout_primary_ref == primary_ref and not refreshed_raw_ref and raw_ref:
                    await asyncio.sleep(0.1)
                    refreshed_version = await ver_repo.get_by_id(uuid.UUID(document_version_id))
                    refreshed_raw_ref = (
                        getattr(refreshed_version, "raw_ref", None) if refreshed_version else None
                    )

                soft_raw_lag = (
                    refreshed_layout_primary_ref == primary_ref and not refreshed_raw_ref and raw_ref
                )

                if hard_mismatch:
                    logger.warning(
                        "Extract: refs differ on immediate post-commit read; "
                        "keeping committed result and relying on orchestrator guards",
                        document_id=document_id,
                        version_id=document_version_id,
                        expected_layout_primary_ref=primary_ref,
                        actual_layout_primary_ref=refreshed_layout_primary_ref,
                        expected_raw_ref=raw_ref,
                        actual_raw_ref=refreshed_raw_ref,
                        run_id=run_id,
                    )
                elif soft_raw_lag:
                    logger.info(
                        "Extract: raw_ref not visible on immediate post-commit read; "
                        "committed result is authoritative, orchestrator will re-read later",
                        document_id=document_id,
                        version_id=document_version_id,
                        expected_layout_primary_ref=primary_ref,
                        actual_layout_primary_ref=refreshed_layout_primary_ref,
                        expected_raw_ref=raw_ref,
                        actual_raw_ref=refreshed_raw_ref,
                        run_id=run_id,
                    )

        except Exception as e:
            logger.warning(
                "Extract: post-commit readback failed; committed result kept",
                document_id=document_id,
                version_id=document_version_id,
                run_id=run_id,
                error=str(e),
            )

        duration = time.time() - start_time

        page_strategies = extraction.page_strategies or {}
        ocr_page_count = sum(1 for s in page_strategies.values() if s == "ocr")
        ocr_rate = round(ocr_page_count / max(extraction.page_count or 0, 1), 3)

        logger.info(
            "Extraction committed successfully",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            elements=len(extraction.elements),
            tables=len(extraction.tables),
            pages=extraction.page_count,
            strategy=extraction.strategy,
            raw_ref=raw_ref,
            layout_primary_ref=primary_ref,
            ocr_confidence=(
                round(extraction.avg_ocr_confidence, 3)
                if extraction.avg_ocr_confidence is not None
                else None
            ),
            ocr_rate=ocr_rate,
            duration_seconds=round(duration, 2),
            status=DocumentStatus.EXTRACTED.value,
        )

        METRICS.extraction_duration.labels(
            strategy=extraction.strategy,
        ).observe(duration)

        METRICS.extraction_pages.labels(
            strategy=extraction.strategy,
        ).inc(extraction.page_count)

        if extraction.avg_ocr_confidence is not None and extraction.strategy in ("ocr", "hybrid"):
            METRICS.extraction_ocr_confidence.observe(extraction.avg_ocr_confidence)

        # Аудит: успешное завершение extract
        audit_repo = AuditRepository(db)
        try:
            await audit_repo.log(
                tenant_id=uuid.UUID(tenant_id),
                deal_id=uuid.UUID(deal_id),
                action="EXTRACTION_COMPLETED",
                actor="system",
                actor_role="worker",
                details={
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                    "run_id": run_id,
                    "strategy": extraction.strategy,
                    "page_count": extraction.page_count,
                    "elements": len(extraction.elements),
                    "tables": len(extraction.tables),
                    "raw_ref": raw_ref,
                    "layout_primary_ref": primary_ref,
                    "ocr_confidence": (
                        float(extraction.avg_ocr_confidence)
                        if extraction.avg_ocr_confidence is not None
                        else None
                    ),
                    "ocr_rate": ocr_rate,
                    "duration_seconds": round(duration, 2),
                },
            )
        except Exception:
            logger.warning(
                "Extract: failed to write audit log for EXTRACTION_COMPLETED",
                document_id=document_id,
                document_version_id=document_version_id,
                run_id=run_id,
            )

        _trace = build_stage_trace_fragment(
            strategy=extraction.strategy,
            input_summary={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "run_id": run_id,
            },
            output_summary={
                "page_count": extraction.page_count,
                "elements_count": len(extraction.elements),
                "tables_count": len(extraction.tables),
                "ocr_confidence": (
                    float(extraction.avg_ocr_confidence)
                    if extraction.avg_ocr_confidence is not None else None
                ),
                "ocr_rate": ocr_rate,
                "duration_seconds": round(duration, 2),
            },
            warnings=[],
            artifact_refs={
                "raw_ref": raw_ref,
                "layout_primary_ref": primary_ref,
            },
            decision_details={
                "primary_only_source_contract": True,
            },
        )

        return {
            "status": DocumentStatus.EXTRACTED.value,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "elements": len(extraction.elements),
            "tables": len(extraction.tables),
            "pages": extraction.page_count,
            "strategy": extraction.strategy,
            "duration_seconds": round(duration, 2),
            "raw_ref": raw_ref,
            "layout_primary_ref": primary_ref,
            "tenant_id": tenant_id,
            "committed": True,
            "stage_execution_result_details": _trace,
        }


async def get_pdf_source_ref(
    document_version_id: str,
    db: AsyncSession,
    *,
    require_primary: bool = False,
) -> str | None:
    """
    Получить ссылку на PDF-источник для extract.


    Активный pipeline:
    - extract должен читать только primary_source_ref.


    Legacy fallback (только если require_primary=False):
    - converted_pdf_ref;
    - original_ref.
    """
    repo = DocumentVersionRepository(db)
    version = await repo.get_by_id(uuid.UUID(document_version_id))
    if not version:
        return None

    primary_ref = getattr(version, "primary_source_ref", None)
    converted_ref = getattr(version, "converted_pdf_ref", None)
    original_ref = getattr(version, "original_ref", None)

    if primary_ref:
        return primary_ref

    if require_primary:
        raise TransientError(
            f"primary_source_ref is missing for version {document_version_id} "
            f"while extract requires primary-only source"
        )

    if converted_ref:
        return converted_ref

    return original_ref


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
        origin_filetype_norm = str(origin_filetype).lower()

        if origin_filetype_norm == "pdf":
            if normalized_strategy == "text":
                pipeline_strategy = "pdf_native"
            elif normalized_strategy == "ocr":
                pipeline_strategy = "pdf_ocr"
            elif normalized_strategy == "hybrid":
                pipeline_strategy = "pdf_hybrid"

        elif origin_filetype_norm in {"doc", "docx"}:
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

    updated_doc = await doc_repo.update_status(
        uuid.UUID(document_id),
        DocumentStatus.EXTRACTED.value,
        page_count=page_count,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Document {document_id} not found during EXTRACTED status update",
            details={"stage": "extract", "kind": "document_not_found"},
        )


async def _mark_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    tenant_id: str,
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

    document = await repo.get_by_id(document_uuid)
    if not document:
        return

    audit_repo = AuditRepository(uow.session)
    try:
        await audit_repo.log(
            tenant_id=uuid.UUID(tenant_id),
            deal_id=document.deal_id,
            action="EXTRACTION_FAILED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(document_uuid),
                "run_id": str(run_id) if run_id else None,
                "stage": "extract",
                "reason": reason,
                "message": message,
            },
        )
    except Exception:
        logger.warning(
            "Extract: failed to write audit log for EXTRACTION_FAILED",
            document_id=str(document_uuid),
            run_id=str(run_id) if run_id else None,
        )


async def _mark_quarantine(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    tenant_id: str,
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

    document = await repo.get_by_id(document_uuid)
    if not document:
        return

    audit_repo = AuditRepository(uow.session)
    try:
        await audit_repo.log(
            tenant_id=uuid.UUID(tenant_id),
            deal_id=document.deal_id,
            action="EXTRACTION_QUARANTINED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(document_uuid),
                "run_id": str(run_id) if run_id else None,
                "stage": "extract",
                "reason": reason,
                "message": msg,
            },
        )
    except Exception:
        logger.warning(
            "Extract: failed to write audit log for EXTRACTION_QUARANTINED",
            document_id=str(document_uuid),
            run_id=str(run_id) if run_id else None,
        )


def _s3_ref_to_store_path(s3_ref: str, bucket: str) -> str:
    """
    Преобразовать s3://bucket/path в path для ArtifactStore.get_file().
    Если ссылка не начинается с s3://<bucket>/, возвращаем ошибку явно.
    """
    prefix = f"s3://{bucket}/"
    if not s3_ref or not s3_ref.startswith(prefix):
        raise PermanentError(
            f"Invalid S3 ref for bucket '{bucket}': {s3_ref}",
            details={"stage": "extract", "kind": "invalid_pdf_ref"},
        )
    return s3_ref.replace(prefix, "", 1)
