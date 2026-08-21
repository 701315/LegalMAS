"""
Extract Worker (Phase 9).

В V2-пайплайне (DOCUMENT_LAYOUT_V2_ENABLED = True) полностью пропускает
тяжёлое извлечение (extract_pdf) и мгновенно активирует canonical bypass:
- Находит запись резолва document_run_language_resolution;
- Считывает run-scoped layout_primary_ref;
- Дублирует её в DocumentVersion (для обратной совместимости);
- Переводит статус в EXTRACTED и завершается.
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
from db.repositories.document_run_language_resolution_repo import (
    DocumentRunLanguageResolutionRepository,
)
from db.uow import UnitOfWork, db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from ops.metrics import METRICS
from services.document_layout.config import layout_config
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

# Импортируем legacy-зависимости
from services.extraction_quality import ExtractionQualityPolicy, evaluate_extraction_quality
from services.pdf_extractor import ExtractionResult, build_text_layout_raw, extract_pdf

logger = get_logger(__name__)


_PRIMARY_LANGUAGE_METADATA_KEYS: tuple[str, ...] = (
    "language_pipeline",
    "language_filter",
)


# ─── Legacy Helpers ──────────────────────────────────────────────────────────


def _load_primary_language_metadata_sidecar_safe(
    *,
    store: ArtifactStore,
    tenant_id: str,
    deal_id: str,
    document_id: str,
    document_version_id: str,
) -> dict[str, Any] | None:
    sidecar_path = ArtifactPath.primary_source_language_metadata(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
    )
    try:
        payload = store.get_json(sidecar_path)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    language_metadata: dict[str, Any] = {}
    for key in _PRIMARY_LANGUAGE_METADATA_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            language_metadata[key] = deepcopy(value)

    return language_metadata if language_metadata else None


def _attach_primary_language_metadata(
    *,
    layout: dict[str, Any],
    language_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    layout_primary = deepcopy(layout)
    if not language_metadata:
        return layout_primary

    existing_metadata = layout_primary.get("metadata")
    merged_metadata = dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
    merged_metadata.update(language_metadata)
    layout_primary["metadata"] = merged_metadata
    return layout_primary


# ─── Celery Entrypoint ────────────────────────────────────────────────────────


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
                    error=str(e),
                )
                raise
            except PermanentError as e:
                logger.error(
                    "Permanent error during extraction",
                    document_id=document_id,
                    version_id=document_version_id,
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

    from mas_queue.async_helpers import run_async
    result = run_async(_wrapper())

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
    doc_uuid = uuid.UUID(document_id)
    run_uuid = uuid.UUID(run_id) if run_id else None

    # Включаем V2 master-switch
    v2_enabled = getattr(settings, "DOCUMENT_LAYOUT_V2_ENABLED", False) or layout_config.document_layout_v2_enabled

    # ─── V2 CANONICAL BYPASS ──────────────────────────────────────────────────
    if v2_enabled and run_uuid:
        res_repo = DocumentRunLanguageResolutionRepository(db)
        res_record = await res_repo.get_by_run_and_version(run_uuid, version_uuid)

        if res_record and res_record.layout_primary_ref:
            logger.info(
                "V2: Resolution record found, activating extract-bypass",
                document_id=document_id,
                layout_primary_ref=res_record.layout_primary_ref,
            )

            # Получаем количество страниц из канонического макета (best-effort)
            page_count = 1
            try:
                canonical_path = _s3_ref_to_store_path(res_record.canonical_layout_ref, store.bucket)
                canonical_json = store.get_json(canonical_path)
                page_count = int(canonical_json.get("page_count", 1))
            except Exception:
                pass

            # Обновляем refs версии (пишем layout_primary_ref в DocumentVersion для legacy-совместимости с PII)
            await update_extraction_result(
                document_version_id=document_version_id,
                document_id=document_id,
                raw_ref=res_record.canonical_layout_ref,  # raw_ref == canonical_layout_ref в v2
                primary_ref=res_record.layout_primary_ref,
                page_count=page_count,
                strategy="canonical_filtered_layout_v2",
                ocr_confidence=1.0,
                db=db,
            )
            await db.commit()

            return {
                "status": DocumentStatus.EXTRACTED.value,
                "document_id": document_id,
                "document_version_id": document_version_id,
                "elements": 0,
                "tables": 0,
                "pages": page_count,
                "strategy": "canonical_filtered_layout_v2",
                "duration_seconds": round(time.time() - start_time, 2),
                "raw_ref": res_record.canonical_layout_ref,
                "layout_primary_ref": res_record.layout_primary_ref,
                "tenant_id": tenant_id,
                "committed": True,
                "analysis_source_kind": "canonical_filtered_layout_v2",
                "stage_execution_result_details": None,
            }

    # ─── V1 LEGACY PIPELINE PATH ──────────────────────────────────────────────
    canonical_enabled = (
        getattr(settings, "CANONICAL_LAYOUT_PIPELINE_ENABLED", False)
        or tenant_id in getattr(settings, "CANONICAL_LAYOUT_PIPELINE_TENANT_ALLOWLIST", [])
    )

    if canonical_enabled:
        try:
            ver_repo_check = DocumentVersionRepository(db)
            version_check = await ver_repo_check.get_by_id(version_uuid)
            existing_primary_ref = getattr(version_check, "layout_primary_ref", None) if version_check else None

            if existing_primary_ref:
                existing_primary = store.get_json(
                    _s3_ref_to_store_path(existing_primary_ref, store.bucket)
                )
                analysis_source_kind = (
                    existing_primary.get("metadata", {})
                    .get("language_filter", {})
                    .get("analysis_source_kind")
                )

                if analysis_source_kind == "canonical_filtered_layout_v2":
                    logger.info(
                        "Extract: legacy canonical bypass found, skipping extract_pdf()",
                        document_id=document_id,
                        layout_primary_ref=existing_primary_ref,
                    )
                    raw_ref_existing = getattr(version_check, "text_layout_raw_ref", None)
                    page_count = existing_primary.get("metadata", {}).get("pages", 0) or 0

                    await update_extraction_result(
                        document_version_id=document_version_id,
                        document_id=document_id,
                        raw_ref=raw_ref_existing or existing_primary_ref,
                        primary_ref=existing_primary_ref,
                        page_count=page_count,
                        strategy="canonical_filtered_layout_v2",
                        ocr_confidence=None,
                        db=db,
                    )
                    await db.commit()

                    return {
                        "status": DocumentStatus.EXTRACTED.value,
                        "document_id": document_id,
                        "document_version_id": document_version_id,
                        "elements": 0,
                        "tables": 0,
                        "pages": page_count,
                        "strategy": "canonical_filtered_layout_v2",
                        "duration_seconds": round(time.time() - start_time, 2),
                        "raw_ref": raw_ref_existing or existing_primary_ref,
                        "layout_primary_ref": existing_primary_ref,
                        "tenant_id": tenant_id,
                        "committed": True,
                        "analysis_source_kind": "canonical_filtered_layout_v2",
                        "stage_execution_result_details": None,
                    }
        except Exception as canonical_exc:
            logger.warning("Extract: legacy canonical check failed, falling back to legacy", error=str(canonical_exc))

    # Чтение PDF
    pdf_ref = await get_pdf_source_ref(document_version_id=document_version_id, db=db, require_primary=True)
    if not pdf_ref:
        raise PermanentError(f"No PDF source ref for version {document_version_id}")

    try:
        s3_path = _s3_ref_to_store_path(pdf_ref, store.bucket)
        pdf_bytes = store.get_file(s3_path)
    except Exception as e:
        raise PermanentError(f"Failed to read PDF from store: {e}")

    # Извлечение
    try:
        extraction: ExtractionResult = extract_pdf(pdf_bytes, document_id)
    except Exception as e:
        raise PermanentError(f"extract_pdf failed: {e}")

    # Оценка качества
    quality_decision = evaluate_extraction_quality(
        extraction,
        policy=ExtractionQualityPolicy(
            ocr_quarantine_threshold=settings.EXTRACTION_OCR_QUARANTINE_THRESHOLD,
            hybrid_min_ocr_rate_for_quarantine=settings.EXTRACTION_HYBRID_MIN_OCR_RATE_FOR_QUARANTINE,
        ),
    )

    if quality_decision.outcome == "failed":
        raise PermanentError(quality_decision.message)
    if quality_decision.outcome == "quarantine":
        METRICS.quarantine.labels(reason=quality_decision.reason or "unknown").inc()
        raise QuarantineError(
            quality_decision.message,
            document_id=document_id,
            reason=quality_decision.reason or "unknown",
            details=quality_decision.details,
        )

    # Построение макетов
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

    if not (layout_primary.get("metadata", {}).get("language_filter", {}).get("analysis_source_kind")):
        lf = layout_primary.setdefault("metadata", {}).setdefault("language_filter", {})
        lf["analysis_source_kind"] = "legacy_primary_pdf"
        lf["legacy_reason"] = "document_processed_before_canonical_layout_migration"

    # Сохранение в S3
    raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
    raw_ref = store.put_json(raw_path, text_layout_raw)

    primary_path = ArtifactPath.layout_primary(tenant_id, deal_id, document_id)
    primary_ref = store.put_json(primary_path, layout_primary)

    # Фиксация в БД
    await update_extraction_result(
        document_version_id=document_version_id,
        document_id=document_id,
        raw_ref=raw_ref,
        primary_ref=primary_ref,
        page_count=extraction.page_count,
        strategy=extraction.strategy or "text",
        ocr_confidence=float(extraction.avg_ocr_confidence) if extraction.avg_ocr_confidence is not None else None,
        db=db,
    )
    await db.commit()

    duration = time.time() - start_time
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
    }


async def get_pdf_source_ref(
    document_version_id: str,
    db: AsyncSession,
    *,
    require_primary: bool = False,
) -> str | None:
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
        raise TransientError(f"primary_source_ref is missing for version {document_version_id}")
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

    version_existing_raw_ref = getattr(version, "text_layout_raw_ref", None) if version else None
    effective_raw_ref = version_existing_raw_ref or raw_ref

    await ver_repo.update_refs(
        version_uuid,
        raw_ref=effective_raw_ref,
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
        raise PermanentError(f"Document {document_id} not found during EXTRACTED status update")


async def _mark_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    tenant_id: str,
    message: str,
    run_id: uuid.UUID | None,
    error: PermanentError | None = None,
) -> None:
    repo = DocumentRepository(uow.session)
    reason = getattr(error, "details", {}).get("kind") if error else "extraction_error"
    await repo.set_failed(document_uuid, stage="extract", message=message, reason=reason, run_id=run_id)


async def _mark_quarantine(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    tenant_id: str,
    error: QuarantineError,
    run_id: uuid.UUID | None,
) -> None:
    repo = DocumentRepository(uow.session)
    reason = getattr(error, "reason", None)
    msg = str(error)
    await repo.set_quarantined(document_uuid, stage="extract", message=msg, reason=reason, run_id=run_id)


def _s3_ref_to_store_path(s3_ref: str, bucket: str) -> str:
    prefix = f"s3://{bucket}/"
    if not s3_ref or not s3_ref.startswith(prefix):
        raise PermanentError(f"Invalid S3 ref for bucket '{bucket}': {s3_ref}")
    return s3_ref.replace(prefix, "", 1)
