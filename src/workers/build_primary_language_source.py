"""
Build Primary Language Source Worker (V2 Only).

Назначение:
- Построение канонического многоязычного макета (CanonicalLayout) через Docling + PyMuPDF;
- Формирование одноязычной проекции для указанного target_language;
- Валидация качества на 3 рубежах Quality Gates;
- Запись результатов в run-scoped таблицу document_run_language_resolution;
- Обновление языка сделки и статуса языка документа.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
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
from storage.artifact_store import ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


def _normalize_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    cleaned = str(lang).strip().lower()
    return cleaned if cleaned else None


def _s3_ref_to_store_path(s3_ref: str, bucket: str) -> str:
    prefix = f"s3://{bucket}/"
    if not s3_ref or not s3_ref.startswith(prefix):
        raise PermanentError(f"Invalid S3 ref for bucket '{bucket}': {s3_ref!r}")
    return s3_ref.replace(prefix, "", 1)


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


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
            "Permanent error during primary language source build V2",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            error=str(e),
        )
        raise
    except TransientError as e:
        logger.warning(
            "Transient error during primary language source build V2",
            document_id=document_id,
            document_version_id=document_version_id,
            error=str(e),
        )
        raise

    committed = bool(result.get("committed"))
    requires_user_selection = bool(result.get("requires_user_selection"))
    quarantined = bool(result.get("quarantined"))
    target_lang = result.get("target_language")

    if requires_user_selection or quarantined:
        return result

    if run_id and committed:
        logger.info(
            "Primary language source build committed V2, retriggering run pipeline",
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
    Асинхронное ядро V2-пайплайна построения макета.
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

    # Считываем policy из Run (если есть)
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
            layout_primary_ref=res.layout_primary_ref,
            # Записываем оригинальный PDF как primary_source для фронтенда.
            # В v3 мы больше не генерируем кривой PDF через ReportLab,
            # а используем исходный документ + точный JSON-макет для подсветки.
            primary_source_ref=source_ref,
        )

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

        # Language Discovery Side-Effect
        await doc_repo.update_language_discovery(
            doc_uuid,
            detected_languages=res.detected_languages,
            status=LanguageDiscoveryStatus.COMPLETED,
        )
        if res.detected_languages:
            await update_deal_languages(db, deal_uuid, res.detected_languages)
        
        # Исправлено: Явная передача keyword-only аргументов во избежание TypeError
        await recompute_deal_language_discovery_state(db=db, deal_id=deal_uuid)

        await doc_repo.update_status(doc_uuid, DocumentStatus.PRIMARY_READY.value)
        await db.commit()

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
        logger.warning(
            "Quality gate failed during layout preparation",
            **log_extra,
            reason_code=qg_exc.reason_code,
            error_message=qg_exc.message,
        )

        detected_langs = list(version.detected_languages) if version.detected_languages else []

        if qg_exc.reason_code == "TARGET_LANGUAGE_NOT_MATERIALLY_PRESENT":
            if policy == "FAIL_RUN_IF_ANY_DOCUMENT_MISSING_LANGUAGE":
                raise PermanentError(
                    f"Run policy blocked execution: Document {document_id} "
                    f"does not contain target language '{resolved_target_language}'."
                )

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
            
            # Исправлено: Явная передача keyword-only аргументов в error-path ветке
            await recompute_deal_language_discovery_state(db=db, deal_id=deal_uuid)
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


            