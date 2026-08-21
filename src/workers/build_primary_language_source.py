"""
Build Primary Language Source Worker (Phase 8).

Поддерживает dual-mode выполнение:
- V1 (legacy): pdfplumber -> ReportLab PDF regeneration -> primary_source_ref.
- V2 (new): Docling -> PyMuPDF enrichment -> monolingual projection -> run-scoped resolution.

V2 активируется флагом: settings.DOCUMENT_LAYOUT_V2_ENABLED или layout_config.document_layout_v2_enabled.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus, LanguageDiscoveryStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.document_run_language_resolution_repo import (
    DocumentRunLanguageResolutionRepository,
)
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.deal_language_discovery_service import recompute_deal_language_discovery_state
from services.deal_language_service import update_deal_languages
from services.document_layout.config import layout_config
from services.document_layout.service import DocumentLayoutService, QualityGateError
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

# Импортируем legacy-зависимости (сохраняются для V1 ветки)
from services.document_language_detection import detect_document_languages_from_pdf_bytes
from services.document_language_pipeline import (
    MIN_TARGET_LANGUAGE_RATIO,
    _normalize_lang,
    build_primary_language_layout,
)
from services.primary_layout_quality import validate_primary_layout

logger = get_logger(__name__)


_PRIMARY_LANGUAGE_METADATA_KEYS: tuple[str, ...] = (
    "language_pipeline",
    "language_filter",
)
_PRIMARY_LANGUAGE_METADATA_SIDECAR_CONTRACT_VERSION = 1


# ─── Legacy Helpers ──────────────────────────────────────────────────────────


def _build_primary_language_metadata_sidecar(
    primary_layout: dict[str, Any],
) -> dict[str, Any] | None:
    metadata = primary_layout.get("metadata")
    if not isinstance(metadata, dict):
        return None

    payload: dict[str, Any] = {
        "contract_version": _PRIMARY_LANGUAGE_METADATA_SIDECAR_CONTRACT_VERSION,
    }
    has_language_metadata = False

    for key in _PRIMARY_LANGUAGE_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, dict):
            payload[key] = deepcopy(value)
            has_language_metadata = True

    if not has_language_metadata:
        return None

    return payload


def _store_primary_language_metadata_sidecar_safe(
    *,
    store: ArtifactStore,
    tenant_id: str,
    deal_id: str,
    document_id: str,
    primary_layout: dict[str, Any],
    log_extra_base: dict[str, Any],
) -> str | None:
    payload = _build_primary_language_metadata_sidecar(primary_layout)
    if payload is None:
        return None

    sidecar_path = ArtifactPath.primary_source_language_metadata(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
    )

    try:
        sidecar_ref = store.put_json(sidecar_path, payload)
    except Exception as exc:
        logger.warning(
            "Primary source build: failed to store language metadata sidecar, continuing",
            **log_extra_base,
            sidecar_path=sidecar_path,
            error=str(exc),
        )
        return None
    return sidecar_ref


def _layout_elements_signature(layout: dict[str, Any] | None) -> frozenset[str]:
    elements = list((layout or {}).get("elements") or [])
    return frozenset(
        str(el.get("element_id"))
        for el in elements
        if el.get("element_id")
    )


def _primary_layout_materially_differs(
    raw_layout: dict[str, Any] | None,
    primary_layout: dict[str, Any] | None,
) -> bool:
    raw_ids = _layout_elements_signature(raw_layout)
    primary_ids = _layout_elements_signature(primary_layout)
    return raw_ids != primary_ids


def _determine_primary_source_build_mode(
    *,
    decision: Any,
    raw_layout: dict[str, Any],
    primary_layout: dict[str, Any],
) -> str:
    is_multi = (
        bool(getattr(decision, "is_multilingual", False))
        or bool(getattr(decision, "is_bilingual", False))
    )
    if is_multi:
        return "single_language_pdf"

    if _primary_layout_materially_differs(raw_layout, primary_layout):
        return "monolingual_filtered_pdf"

    return "monolingual_reuse"


def _is_canonical_layout_enabled_for_tenant(tenant_id: str) -> bool:
    global_enabled = bool(getattr(settings, "CANONICAL_LAYOUT_PIPELINE_ENABLED", False))
    allowlist = getattr(settings, "canonical_layout_tenant_allowlist", None)
    if allowlist is None:
        raw = getattr(settings, "CANONICAL_LAYOUT_PIPELINE_TENANT_ALLOWLIST", "")
        allowlist = [
            item.strip()
            for item in str(raw).split(",")
            if item and item.strip()
        ]
    return global_enabled or tenant_id in allowlist


def _prepare_primary_layout_for_canonical_analysis(
    primary_layout: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(primary_layout)
    metadata = dict(result.get("metadata") or {})
    language_filter = dict(metadata.get("language_filter") or {})

    language_filter["analysis_source_kind"] = "canonical_filtered_layout_v2"
    language_filter["downstream_requires_primary_source"] = False

    metadata["language_filter"] = language_filter
    result["metadata"] = metadata
    return result


def _store_canonical_layout_artifacts(
    *,
    store: ArtifactStore,
    tenant_id: str,
    deal_id: str,
    document_id: str,
    document_version_id: str,
    target_language: str,
    primary_layout: dict[str, Any],
    log_extra_base: dict[str, Any],
) -> tuple[str, str | None, dict[str, Any]]:
    canonical_layout = _prepare_primary_layout_for_canonical_analysis(primary_layout)
    primary_path = ArtifactPath.layout_primary(tenant_id, deal_id, document_id)
    layout_primary_ref = store.put_json(primary_path, canonical_layout)
    return layout_primary_ref, None, canonical_layout


# ─── Celery Entrypoint ────────────────────────────────────────────────────────


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_primary_language_source",
    track_job=False,
    queue="default",
)
def build_primary_language_source(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    target_language: str | None = None,
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
            return await _build_primary_language_source_async(
                document_version_id=document_version_id,
                document_id=document_id,
                deal_id=deal_id,
                tenant_id=resolved_tenant_id,
                db=uow.session,
                run_id=run_id,
                target_language=target_language,
            )

    try:
        result = run_async(_wrapper())
    except PermanentError as e:
        logger.error(
            "Permanent error during primary language source build",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            error=str(e),
        )
        raise
    except TransientError as e:
        logger.warning(
            "Transient error during primary language source build",
            document_id=document_id,
            document_version_id=document_version_id,
            error=str(e),
        )
        raise

    committed = bool(result.get("committed"))
    requires_user_selection = bool(result.get("requires_user_selection"))
    quarantined = bool(result.get("quarantined"))
    target_lang = result.get("target_language")

    if requires_user_selection:
        return result

    if quarantined:
        return result

    if run_id and committed:
        logger.info(
            "Primary language source build committed, retriggering run pipeline",
            document_id=document_id,
            run_id=run_id,
            target_language=target_lang,
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
        )

    return result


async def _build_primary_language_source_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,
    target_language: str | None = None,
) -> dict:
    """
    Async-координатор build_primary_language_source.
    """
    v2_enabled = getattr(settings, "DOCUMENT_LAYOUT_V2_ENABLED", False) or layout_config.document_layout_v2_enabled

    if v2_enabled:
        return await _build_primary_language_source_v2_async(
            document_version_id=document_version_id,
            document_id=document_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            db=db,
            run_id=run_id,
            target_language=target_language,
        )
    else:
        return await _build_primary_language_source_v1_legacy_async(
            document_version_id=document_version_id,
            document_id=document_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            db=db,
            run_id=run_id,
            target_language=target_language,
        )


# ─── V2 Pipeline Core Implementation ──────────────────────────────────────────


async def _build_primary_language_source_v2_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None,
    target_language: str | None,
) -> dict:
    """
    Реализация Фазы 8 на базе DoclingExtractor и DocumentLayoutService (V2).
    """
    log_extra = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
        "pipeline_version": "v2_docling",
    }

    logger.info("Starting build_primary_language_source V2 pipeline", **log_extra)

    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)
    deal_repo = DealRepository(db)
    res_repo = DocumentRunLanguageResolutionRepository(db)
    audit_repo = AuditRepository(db)
    store = ArtifactStore(settings)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)
    deal_uuid = uuid.UUID(deal_id)
    run_uuid = uuid.UUID(run_id) if run_id else None

    # 1. Загрузка версии и документа
    version = await ver_repo.get_by_id(version_uuid)
    if not version:
        raise PermanentError(f"DocumentVersion {document_version_id} not found")

    # Резолвим PDF источник (original или converted)
    source_ref = version.converted_pdf_ref or version.original_ref
    if version.origin_filetype and version.origin_filetype.lower() == "pdf":
        source_ref = version.original_ref

    if not source_ref:
        raise PermanentError(f"No source PDF ref found for version {document_version_id}")

    # Читаем PDF из MinIO
    try:
        source_path = _s3_ref_to_store_path(source_ref, store.bucket)
        pdf_bytes = store.get_file(source_path)
    except Exception as exc:
        logger.exception("Failed to read source PDF bytes from S3", **log_extra, source_ref=source_ref)
        raise PermanentError(f"Failed to read source PDF: {exc}")

    # 2. Выбор целевого языка проверки
    resolved_target_language = _normalize_lang(target_language)
    if not resolved_target_language:
        deal = await deal_repo.internal_unsafe_get_by_id(deal_uuid)
        resolved_target_language = _normalize_lang(
            getattr(deal, "primary_language", None) if deal else None
        )

    if not resolved_target_language:
        logger.warning("Target language is missing, pausing until user selects language", **log_extra)
        await doc_repo.update_status(doc_uuid, DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value)
        await db.commit()
        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "requires_user_selection": True,
            "committed": True,
        }

    # Считываем policy из Run (если есть) через чистый SQLAlchemy 2.0 API
    policy = "BLOCK_DOCUMENT_CONTINUE_RUN"
    if run_uuid:
        from db.models.run import Run
        stmt = select(Run.missing_target_language_policy).where(Run.id == run_uuid)
        res = await db.execute(stmt)
        policy = res.scalar_one_or_none() or "BLOCK_DOCUMENT_CONTINUE_RUN"

    # 3. Запуск DocumentLayoutService
    layout_service = DocumentLayoutService(store=store)

    try:
        res = layout_service.prepare_document_layout(
            pdf_bytes=pdf_bytes,
            target_language=resolved_target_language,
            document_id=document_id,
            document_version_id=document_version_id,
            run_id=run_id or str(uuid.UUID(int=0)),
            tenant_id=tenant_id,
            deal_id=deal_id,
        )

        # 4. Happy Path: Проекция построена и успешно прошла все гейты качества
        await ver_repo.update_refs(
            version_id=version_uuid,
            canonical_layout_ref=res.canonical_layout_ref,
            detected_languages=res.detected_languages,
            # Backward-compat: пишем макет также в layout_primary_ref для legacy PII
            layout_primary_ref=res.layout_primary_ref,
        )

        # Пишем в document_run_language_resolution
        if run_uuid:
            await res_repo.upsert_resolution(
                run_id=run_uuid,
                document_version_id=version_uuid,
                tenant_id=uuid.UUID(tenant_id),
                requested_language=resolved_target_language,
                available_languages=res.detected_languages,
                effective_language=resolved_target_language,
                resolution_status="LANGUAGE_READY",
                canonical_layout_ref=res.canonical_layout_ref,
                layout_primary_ref=res.layout_primary_ref,
            )

        # Language Discovery Side-Effect: обновляем языки документа и сделки
        await doc_repo.update_language_discovery(
            doc_uuid,
            detected_languages=res.detected_languages,
            status=LanguageDiscoveryStatus.COMPLETED,
        )
        if res.detected_languages:
            await update_deal_languages(db, deal_uuid, res.detected_languages)
        await recompute_deal_language_discovery_state(db, deal_uuid)

        # Переводим документ в статус PRIMARY_READY
        await doc_repo.update_status(doc_uuid, DocumentStatus.PRIMARY_READY.value)
        await db.commit()

        # Запись аудита
        try:
            await audit_repo.log(
                tenant_id=uuid.UUID(tenant_id),
                deal_id=deal_uuid,
                action="PRIMARY_SOURCE_READY",
                actor="system",
                actor_role="worker",
                details={
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                    "run_id": run_id,
                    "target_language": resolved_target_language,
                    "detected_languages": res.detected_languages,
                    "canonical_layout_ref": res.canonical_layout_ref,
                    "layout_primary_ref": res.layout_primary_ref,
                },
            )
        except Exception:
            pass

        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "canonical_layout_ref": res.canonical_layout_ref,
            "layout_primary_ref": res.layout_primary_ref,
            "target_language": resolved_target_language,
            "detected_languages": res.detected_languages,
            "requires_user_selection": False,
            "committed": True,
        }

    except QualityGateError as qg_exc:
        # 5. Обработка провала гейтов качества (карантин или unavailable)
        logger.warning(
            "Quality gate failed during layout preparation",
            **log_extra,
            reason_code=qg_exc.reason_code,
            error_message=qg_exc.message,
        )

        detected_langs = list(version.detected_languages) if version.detected_languages else []

        if qg_exc.reason_code == "TARGET_LANGUAGE_NOT_MATERIALLY_PRESENT":
            # Применяем missing target language policy
            if policy == "FAIL_RUN_IF_ANY_DOCUMENT_MISSING_LANGUAGE":
                raise PermanentError(
                    f"Run policy blocked execution: Document {document_id} "
                    f"does not contain target language '{resolved_target_language}'."
                )

            # Default / BLOCK_DOCUMENT_CONTINUE_RUN
            if run_uuid:
                await res_repo.upsert_resolution(
                    run_id=run_uuid,
                    document_version_id=version_uuid,
                    tenant_id=uuid.UUID(tenant_id),
                    requested_language=resolved_target_language,
                    available_languages=detected_langs,
                    effective_language=None,
                    resolution_status="LANGUAGE_UNAVAILABLE",
                    reason_code="TARGET_LANGUAGE_NOT_MATERIALLY_PRESENT",
                )

            await doc_repo.update_status(
                doc_uuid,
                DocumentStatus.QUARANTINE.value,
                processing_error_details={
                    "stage": "build_primary_language_source",
                    "type": "language_mismatch",
                    "reason": qg_exc.reason_code,
                    "message": qg_exc.message,
                    "timestamp": _utcnow_iso(),
                },
            )
            await doc_repo.update_language_discovery(
                doc_uuid,
                detected_languages=detected_langs,
                status=LanguageDiscoveryStatus.COMPLETED,
            )
            await recompute_deal_language_discovery_state(db, deal_uuid)
            await db.commit()

            return {
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "target_language": resolved_target_language,
                "quarantined": True,
                "quarantine_reason": qg_exc.reason_code,
                "committed": True,
            }

        else:
            await doc_repo.update_status(
                doc_uuid,
                DocumentStatus.QUARANTINE.value,
                processing_error_details={
                    "stage": "build_primary_language_source",
                    "type": "quality_gate_failed",
                    "reason": qg_exc.reason_code,
                    "message": qg_exc.message,
                    "timestamp": _utcnow_iso(),
                },
            )
            await db.commit()
            return {
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "target_language": resolved_target_language,
                "quarantined": True,
                "quarantine_reason": qg_exc.reason_code,
                "committed": True,
            }


# ─── V1 Legacy Pipeline Core Implementation ───────────────────────────────────


async def _build_primary_language_source_v1_legacy_async(
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    run_id: str | None = None,
    target_language: str | None = None,
) -> dict:
    log_extra_base = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
    }

    logger.info("Starting build_primary_language_source (legacy V1 pipeline)", **log_extra_base)

    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)
    store = ArtifactStore(settings)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)
    deal_uuid = uuid.UUID(deal_id)

    version = await ver_repo.get_by_id(version_uuid)
    if version is None:
        raise PermanentError(f"DocumentVersion {document_version_id} not found")

    existing_primary_ref = getattr(version, "primary_source_ref", None)
    converted_pdf_ref = getattr(version, "converted_pdf_ref", None)
    original_ref = getattr(version, "original_ref", None)
    origin_filetype = getattr(version, "origin_filetype", None)

    source_ref: str | None = None
    source_kind: str | None = None

    if origin_filetype and origin_filetype.lower() == "pdf":
        source_ref = original_ref
        source_kind = "original_ref_pdf"
    elif origin_filetype and origin_filetype.lower() in {"doc", "docx"}:
        if converted_pdf_ref:
            source_ref = converted_pdf_ref
            source_kind = "converted_pdf_ref_docx"
        else:
            raise PermanentError(f"No converted PDF for DOC/DOCX document")
    else:
        source_ref = converted_pdf_ref or original_ref
        source_kind = "converted_pdf_ref_other" if converted_pdf_ref else "original_ref_other"

    if not source_ref:
        raise PermanentError("No source PDF found")

    try:
        source_path = _s3_ref_to_store_path(source_ref, store.bucket)
        pdf_bytes = store.get_file(source_path)
    except Exception as e:
        raise PermanentError(f"Failed to read source PDF: {e}")

    detection_result = detect_document_languages_from_pdf_bytes(
        pdf_bytes=pdf_bytes,
        document_id=document_id,
        document_version_id=document_version_id,
    )
    quick_layout = detection_result.quick_layout
    detected_languages = detection_result.detected_languages

    canonical_enabled = _is_canonical_layout_enabled_for_tenant(tenant_id)
    raw_ref: str | None = None

    if canonical_enabled:
        try:
            raw_path = ArtifactPath.layout_raw(tenant_id, deal_id, document_id)
            raw_ref = store.put_json(raw_path, quick_layout)
        except Exception:
            raw_ref = None

    await doc_repo.update_language_discovery(
        doc_uuid,
        detected_languages=detected_languages,
        status=LanguageDiscoveryStatus.COMPLETED,
    )

    if detected_languages:
        await update_deal_languages(db=db, deal_id=deal_uuid, new_languages=detected_languages)
    await recompute_deal_language_discovery_state(db=db, deal_id=deal_uuid)

    deal_repo = DealRepository(db)
    resolved_target_language = _normalize_lang(target_language)

    if not resolved_target_language:
        deal = await deal_repo.internal_unsafe_get_by_id(deal_uuid)
        resolved_target_language = _normalize_lang(
            getattr(deal, "primary_language", None) if deal is not None else None
        )

    if not resolved_target_language:
        await doc_repo.update_status(doc_uuid, DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value)
        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "requires_user_selection": True,
            "committed": False,
        }

    primary_layout_result = await build_primary_language_layout(
        db=db,
        deal_id=deal_uuid,
        tenant_id=tenant_id,
        document_id=document_id,
        layout=quick_layout,
        target_language=resolved_target_language,
    )

    primary_layout = primary_layout_result.primary_layout
    decision = primary_layout_result.decision
    target_language = decision.target_language

    primary_source_build_mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=quick_layout,
        primary_layout=primary_layout,
    )

    if primary_layout_result.should_quarantine:
        await doc_repo.update_status(
            doc_uuid,
            DocumentStatus.QUARANTINE.value,
            processing_error_details={
                "stage": "build_primary_language_source",
                "type": "language_mismatch",
                "reason": decision.quarantine_reason,
                "message": "Quarantined due to language mismatch",
                "timestamp": _utcnow_iso(),
            },
        )
        await db.commit()
        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "quarantined": True,
            "quarantine_reason": decision.quarantine_reason,
            "committed": True,
        }

    layout_primary_ref: str | None = None
    filter_decisions_ref: str | None = None

    if canonical_enabled:
        quality = validate_primary_layout(
            raw_layout=quick_layout,
            primary_layout=_prepare_primary_layout_for_canonical_analysis(primary_layout),
            expected_target_ratio=float(getattr(decision, "target_language_ratio", 0.0) or 0.0),
        )
        primary_layout.setdefault("metadata", {})["quality"] = quality

        if quality.get("fidelity_status") == "failed":
            await doc_repo.update_status(
                doc_uuid,
                DocumentStatus.QUARANTINE.value,
                processing_error_details={
                    "stage": "build_primary_language_source",
                    "type": "primary_layout_quality_failed",
                    "reason": "canonical_primary_layout_validation_failed",
                    "message": "Primary layout failed quality validation",
                    "timestamp": _utcnow_iso(),
                },
            )
            await db.commit()
            return {
                "document_id": document_id,
                "quarantined": True,
                "quarantine_reason": "canonical_primary_layout_validation_failed",
                "committed": True,
            }

        layout_primary_ref, filter_decisions_ref, _ = _store_canonical_layout_artifacts(
            store=store,
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=document_id,
            document_version_id=document_version_id,
            target_language=target_language,
            primary_layout=primary_layout,
            log_extra_base=log_extra_base,
        )

    if primary_source_build_mode == "monolingual_reuse":
        primary_path = ArtifactPath.primary_source(tenant_id, deal_id, document_id)
        primary_source_ref = store.put_file(primary_path, pdf_bytes, content_type="application/pdf")

        _store_primary_language_metadata_sidecar_safe(
            store=store,
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=document_id,
            primary_layout=primary_layout,
            log_extra_base=log_extra_base,
        )

        await ver_repo.update_refs(
            version_id=version_uuid,
            primary_source_ref=primary_source_ref,
            raw_ref=raw_ref,
            layout_primary_ref=layout_primary_ref,
        )
        await doc_repo.update_status(doc_uuid, DocumentStatus.PRIMARY_READY.value)
        await db.commit()

        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "primary_source_ref": primary_source_ref,
            "raw_ref": raw_ref,
            "layout_primary_ref": layout_primary_ref,
            "target_language": target_language,
            "committed": True,
        }

    # Rebuild PDF from filtered layout path (V1)
    export_result = await _try_build_pdf_export(
        primary_layout=primary_layout,
        store=store,
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
        log_extra_base=log_extra_base,
    )
    primary_source_ref = export_result.get("primary_source_ref")

    if not primary_source_ref and not canonical_enabled:
        raise PermanentError("PDF export failed for version in legacy mode")

    _store_primary_language_metadata_sidecar_safe(
        store=store,
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
        primary_layout=primary_layout,
        log_extra_base=log_extra_base,
    )

    await ver_repo.update_refs(
        version_id=version_uuid,
        primary_source_ref=primary_source_ref,
        raw_ref=raw_ref,
        layout_primary_ref=layout_primary_ref,
    )
    await doc_repo.update_status(doc_uuid, DocumentStatus.PRIMARY_READY.value)
    await db.commit()

    return {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "primary_source_ref": primary_source_ref,
        "raw_ref": raw_ref,
        "layout_primary_ref": layout_primary_ref,
        "target_language": target_language,
        "committed": True,
    }


def _s3_ref_to_store_path(s3_ref: str, bucket: str) -> str:
    prefix = f"s3://{bucket}/"
    if not s3_ref or not s3_ref.startswith(prefix):
        raise PermanentError(f"Invalid S3 ref for bucket '{bucket}': {s3_ref!r}")
    return s3_ref.replace(prefix, "", 1)


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


async def _try_build_pdf_export(
    *,
    primary_layout: dict[str, Any],
    store: ArtifactStore,
    tenant_id: str,
    deal_id: str,
    document_id: str,
    log_extra_base: dict[str, Any],
) -> dict[str, Any]:
    from services.primary_pdf_builder import build_pdf_from_layout
    from services.primary_pdf_export_validator import validate_pdf_export

    try:
        pdf_bytes = build_pdf_from_layout(primary_layout)
    except Exception as exc:
        return {
            "primary_source_ref": None,
            "export_fidelity_status": "not_generated",
            "export_diagnostic_ref": None,
        }

    validation = validate_pdf_export(primary_layout, pdf_bytes)
    status = validation["export_fidelity_status"]

    if status == "failed":
        return {
            "primary_source_ref": None,
            "export_fidelity_status": "failed",
            "export_diagnostic_ref": None,
        }

    primary_path = ArtifactPath.primary_source(tenant_id, deal_id, document_id)
    try:
        primary_source_ref = store.put_file(primary_path, pdf_bytes, content_type="application/pdf")
        return {
            "primary_source_ref": primary_source_ref,
            "export_fidelity_status": status,
            "export_diagnostic_ref": None,
        }
    except Exception:
        return {
            "primary_source_ref": None,
            "export_fidelity_status": "not_generated",
            "export_diagnostic_ref": None,
        }
