# src/workers/build_primary_language_source.py

"""
Build Primary Language Source Worker.


Назначение:
- Подготовить primary_source_ref для extract_worker.
- В архитектуре варианта А extract_worker больше НЕ занимается языковой
  фильтрацией и всегда работает по primary_source_ref.
- На этом этапе мы:
  1) строим layout из исходного PDF;
  2) определяем языки документа и выбираем основной;
  3) строим одноязычный layout по выбранному языку;
  4) собираем новый одноязычный PDF и сохраняем его как primary_source_ref.


Позиция в пайплайне:
    import/convert
    → build_primary_language_source  ← этот worker
    → extract
    → pii
    → structure
    → ...


Контракт:
- вызывается оркестратором или авто-пайплайном после import/convert_to_pdf;
- по завершении (успех) документ должен перейти в статус PRIMARY_READY;
- в DocumentVersion.primary_source_ref должна появиться S3-ссылка на одноязычный PDF;
- запуск последующих стадий (extract и далее) выполняется централизованным
  оркестратором, но только после подтверждённого commit одноязычного source.

Замечание по language discovery:
- Этот worker НЕ является частью language discovery pipeline
  (start_language_discovery → prepare → detect → recompute).
- Он использует detect_document_languages_from_pdf_bytes как вспомогательный
  инструмент для выбора target_language при построении primary_source_ref.
- После detection фиксирует Document.language_discovery_status = COMPLETED
  через doc_repo.update_language_discovery() и вызывает recompute_deal_language_discovery_state,
  чтобы deal-статус был консистентен.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus, LanguageDiscoveryStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.deal_language_discovery_service import recompute_deal_language_discovery_state
from services.deal_language_service import update_deal_languages
from services.document_language_detection import detect_document_languages_from_pdf_bytes
from services.document_language_pipeline import (
    MIN_TARGET_LANGUAGE_RATIO,
    _normalize_lang,
    build_primary_language_layout,
)
from services.primary_pdf_builder import build_pdf_from_layout
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


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
) -> dict:
    """
    Sync Celery entrypoint.

    Контракт:
    - вызывается оркестратором или auto-pipeline для документов после import
      или после convert_to_pdf;
    - по завершении (успех) документ должен перейти в статус PRIMARY_READY
      ИЛИ в LANGUAGE_SELECTION_REQUIRED, если нужен выбор языка пользователем;
    - в DocumentVersion.primary_source_ref должна появиться S3-ссылка,
      если построен одноязычный PDF;
    - запуск последующих стадий (extract и далее) выполняется централизованным
      оркестратором, но только после подтверждённого commit одноязычного source.
    """

    async def _wrapper() -> dict:
        async with db_uow() as uow:
            return await _build_primary_language_source_async(
                document_version_id=document_version_id,
                document_id=document_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                db=uow.session,
                run_id=run_id,
                target_language=target_language,
            )

    try:
        result = run_async(_wrapper())

    except PermanentError as e:
        logger.error(
            "Permanent error during primary language source build",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "error": str(e),
            },
        )
        raise

    except TransientError as e:
        logger.warning(
            "Transient error during primary language source build; task should be retried",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "error": str(e),
            },
        )
        raise

    committed = bool(result.get("committed"))
    requires_user_selection = bool(result.get("requires_user_selection"))
    target_language = result.get("target_language")
    primary_source_ref = result.get("primary_source_ref")

    # Ветка 1: пайплайн осознанно остановлен до выбора языка пользователем.
    if requires_user_selection:
        logger.info(
            "Primary language source build paused: user language selection required",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "detected_languages": result.get("detected_languages"),
            },
        )
        return result

    # Ветка 2: построен одноязычный PDF и состояние гарантированно закоммичено.
    if run_id and committed:
        logger.info(
            "Primary language source build committed, retriggering run pipeline",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "target_language": target_language,
                "primary_source_ref": primary_source_ref,
            },
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )
        return result

    # Ветка 3: функция завершилась без retrigger.
    # Это не ошибка, но важно видеть такое поведение в логах.
    logger.info(
        "Primary language source build completed without pipeline retrigger",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "committed": committed,
            "requires_user_selection": requires_user_selection,
            "target_language": target_language,
            "primary_source_ref": primary_source_ref,
        },
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
    Async-ядро build_primary_language_source.

    Language discovery side-effect:
    - После успешного detect_document_languages_from_pdf_bytes фиксирует
      Document.language_discovery_status = COMPLETED через update_language_discovery().
    - Затем вызывает recompute_deal_language_discovery_state() для обновления
      агрегированного deal-статуса.
    - Это обеспечивает консистентность deal-статуса независимо от того,
      запущен ли language discovery pipeline параллельно.
    """
    log_extra_base = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
    }

    logger.info(
        "Starting build_primary_language_source",
        extra=log_extra_base,
    )

    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)
    store = ArtifactStore(settings)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)
    deal_uuid = uuid.UUID(deal_id)

    # ── 1. Загрузка версии ────────────────────────────────────────────────────

    version = await ver_repo.get_by_id(version_uuid)
    if version is None:
        raise PermanentError(f"DocumentVersion {document_version_id} not found")

    existing_primary_ref = getattr(version, "primary_source_ref", None)
    converted_pdf_ref = getattr(version, "converted_pdf_ref", None)
    original_ref = getattr(version, "original_ref", None)
    origin_filetype = getattr(version, "origin_filetype", None)

    logger.info(
        "Primary source build: resolved version refs",
        extra={
            **log_extra_base,
            "existing_primary_source_ref": existing_primary_ref,
            "converted_pdf_ref": converted_pdf_ref,
            "original_ref": original_ref,
            "origin_filetype": origin_filetype,
        },
    )

    # ── 2. Выбор source_ref ───────────────────────────────────────────────────
    #
    # PDF: работаем по original_ref.
    # DOC/DOCX: строго требуем converted_pdf_ref.
    # Прочие: converted_pdf_ref, потом original_ref как fallback.

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
            raise PermanentError(
                "No converted PDF for DOC/DOCX document; "
                f"cannot build primary language source (version_id={document_version_id})"
            )

    else:
        source_ref = converted_pdf_ref or original_ref
        source_kind = "converted_pdf_ref_other" if converted_pdf_ref else "original_ref_other"

    if not source_ref:
        raise PermanentError(
            "No source PDF found for primary source build "
            f"(version_id={document_version_id}; converted_pdf_ref and original_ref are empty)"
        )

    logger.info(
        "Primary source build: source selected",
        extra={
            **log_extra_base,
            "source_ref": source_ref,
            "source_kind": source_kind,
        },
    )

    # Если primary_source_ref уже существует — всё равно перестраиваем,
    # чтобы гарантировать одноязычный PDF через новый pipeline.
    if existing_primary_ref:
        logger.info(
            "Primary source build: existing primary_source_ref present, "
            "rebuilding to enforce single-language PDF",
            extra={
                **log_extra_base,
                "existing_primary_source_ref": existing_primary_ref,
            },
        )

    # ── 3. Читаем исходный PDF из MinIO ──────────────────────────────────────

    try:
        source_path = _s3_ref_to_store_path(source_ref, store.bucket)
        logger.info(
            "Primary source build: reading source PDF from store",
            extra={
                **log_extra_base,
                "source_ref": source_ref,
                "source_path": source_path,
            },
        )
        pdf_bytes = store.get_file(source_path)
        logger.info(
            "Primary source build: source PDF loaded",
            extra={
                **log_extra_base,
                "source_ref": source_ref,
                "size": len(pdf_bytes),
            },
        )
    except PermanentError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to read source PDF for primary source build",
            extra={
                **log_extra_base,
                "source_ref": source_ref,
                "error": str(e),
            },
        )
        raise PermanentError(f"Failed to read source PDF: {e}")

    # ── 4. Определяем языки документа ────────────────────────────────────────

    detection_result = detect_document_languages_from_pdf_bytes(
        pdf_bytes=pdf_bytes,
        document_id=document_id,
        document_version_id=document_version_id,
    )
    quick_layout = detection_result.quick_layout
    detected_languages = detection_result.detected_languages

    logger.info(
        "Primary source build: detected languages from quick layout",
        extra={
            **log_extra_base,
            "detected_languages": detected_languages,
        },
    )

    # Фиксируем результат language discovery для этого документа.
    # Используем update_language_discovery() — canonical метод после рефакторинга
    # Используем update_language_discovery() — canonical метод после рефакторинга.
    # Статус COMPLETED означает: языки определены, pipeline discovery для этого
    # документа завершён.
    await doc_repo.update_language_discovery(
        doc_uuid,
        detected_languages=detected_languages,
        status=LanguageDiscoveryStatus.COMPLETED,
    )

    # Обновляем языки сделки и пересчитываем агрегированный discovery-статус.
    if detected_languages:
        await update_deal_languages(
            db=db,
            deal_id=deal_uuid,
            new_languages=detected_languages,
        )
        logger.info(
            "Primary source build: detected languages updated in deal",
            extra={
                **log_extra_base,
                "detected_languages": detected_languages,
            },
        )

    await recompute_deal_language_discovery_state(
        db=db,
        deal_id=deal_uuid,
    )

    deal_repo = DealRepository(db)
    deal_after_lang_update = await deal_repo.get_by_id(deal_uuid)
    logger.info(
        "Primary source build: deal languages after update",
        extra={
            **log_extra_base,
            "persisted_deal_languages": getattr(deal_after_lang_update, "languages", None),
        },
    )

    quick_meta = (quick_layout.get("metadata") or {}).get("quick_layout") or {}
    if quick_meta.get("degraded"):
        logger.warning(
            "Primary source build: quick layout marked as degraded",
            extra={
                **log_extra_base,
                "degraded_reason": quick_meta.get("degraded_reason"),
                "total_chars": quick_meta.get("total_extracted_chars"),
                "valid_bbox_ratio": quick_meta.get("valid_bbox_ratio"),
                "usable_element_ratio": quick_meta.get("usable_element_ratio"),
            },
        )

    # ── 5. Резолвим целевой язык ──────────────────────────────────────────────
    #
    # Приоритет:
    #   1) target_language из kwargs (явный вызов от оркестратора);
    #   2) Deal.primary_language из БД (штатный production-путь).
    #
    # Если язык не найден — fallback: переводим документ в LANGUAGE_SELECTION_REQUIRED
    # и ждём ручного выбора пользователем.

    resolved_target_language = _normalize_lang(target_language)

    if not resolved_target_language:
        deal = await deal_repo.get_by_id(deal_uuid)
        resolved_target_language = _normalize_lang(
            getattr(deal, "primary_language", None) if deal is not None else None
        )

    if not resolved_target_language:
        logger.warning(
            "Primary source build entered fallback mode: target language is missing; "
            "document will be paused until primary language is selected",
            extra=log_extra_base,
        )
        updated_doc = await doc_repo.update_status(
            doc_uuid,
            DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value,
            processing_error_details=None,
        )
        if not updated_doc:
            raise PermanentError(
                f"Document {document_id} not found during LANGUAGE_SELECTION_REQUIRED status update"
            )

        audit_repo = AuditRepository(db)
        try:
            await audit_repo.log(
                tenant_id=uuid.UUID(tenant_id),
                deal_id=deal_uuid,
                action="PRIMARY_LANGUAGE_SELECTION_REQUIRED",
                actor="system",
                actor_role="worker",
                details={
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                    "run_id": run_id,
                    "source_ref": source_ref,
                    "primary_source_ref": existing_primary_ref,
                    "reason": "missing_target_language_fallback",
                },
            )
        except Exception:
            logger.warning(
                "Primary source build: failed to write audit log for "
                "PRIMARY_LANGUAGE_SELECTION_REQUIRED",
                extra={
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                },
            )

        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_ref": source_ref,
            "primary_source_ref": existing_primary_ref,
            "target_language": None,
            "detected_languages": detected_languages,
            "requires_user_selection": True,
            "committed": False,
        }

    # ── 6. Строим одноязычный layout ──────────────────────────────────────────

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

    # ── 7. Карантин: целевой язык отсутствует или слишком мал по доле ────────

    if primary_layout_result.should_quarantine:
        logger.warning(
            "Primary source build: document quarantined due to language mismatch",
            extra={
                **log_extra_base,
                "target_language": target_language,
                "detected_languages": decision.detected_languages,
                "target_language_ratio": round(decision.target_language_ratio, 3),
                "quarantine_reason": decision.quarantine_reason,
            },
        )
        updated_doc = await doc_repo.update_status(
            doc_uuid,
            DocumentStatus.QUARANTINE.value,
            processing_error_details={
                "stage": "build_primary_language_source",
                "type": "language_mismatch",
                "reason": decision.quarantine_reason,
                "message": (
                    f"Document does not contain sufficient content in target language "
                    f"'{target_language}' "
                    f"(ratio={round(decision.target_language_ratio, 3)}, "
                    f"threshold={MIN_TARGET_LANGUAGE_RATIO})"
                ),
                "timestamp": _utcnow_iso(),
            },
        )
        if not updated_doc:
            raise PermanentError(
                f"Document {document_id} not found during QUARANTINE status update"
            )
        await db.commit()

        audit_repo = AuditRepository(db)
        try:
            await audit_repo.log(
                tenant_id=uuid.UUID(tenant_id),
                deal_id=deal_uuid,
                action="PRIMARY_SOURCE_QUARANTINED",
                actor="system",
                actor_role="worker",
                details={
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                    "run_id": run_id,
                    "target_language": target_language,
                    "detected_languages": decision.detected_languages,
                    "target_language_ratio": round(decision.target_language_ratio, 3),
                    "threshold": MIN_TARGET_LANGUAGE_RATIO,
                    "quarantine_reason": decision.quarantine_reason,
                },
            )
        except Exception:
            logger.warning(
                "Primary source build: failed to write audit log for PRIMARY_SOURCE_QUARANTINED",
                extra={
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                },
            )

        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_ref": source_ref,
            "primary_source_ref": existing_primary_ref,
            "target_language": target_language,
            "detected_languages": decision.detected_languages,
            "requires_user_selection": False,
            "quarantined": True,
            "quarantine_reason": decision.quarantine_reason,
            "committed": True,
        }

    language_filter_meta = (primary_layout.get("metadata") or {}).get("language_filter") or {}

    logger.info(
        "Primary source build: primary layout constructed",
        extra={
            **log_extra_base,
            "target_language": target_language,
            "detected_languages": decision.detected_languages,
            "is_bilingual": decision.is_bilingual,
            "requires_user_selection": decision.requires_user_selection,
            "language_filter_degraded": language_filter_meta.get("degraded"),
            "language_filter_degraded_reason": language_filter_meta.get("degraded_reason"),
            "element_retention_ratio": language_filter_meta.get("element_retention_ratio"),
        },
    )

    # ── 8. Монолингвальный документ: переиспользуем исходный PDF ─────────────

    if not decision.is_bilingual:
        logger.info(
            "Primary source build: monolingual document, "
            "reusing original PDF as primary_source_ref",
            extra={
                **log_extra_base,
                "target_language": target_language,
                "detected_languages": decision.detected_languages,
            },
        )

        primary_path = ArtifactPath.primary_source(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=document_id,
        )
        try:
            primary_source_ref = store.put_file(
                primary_path,
                pdf_bytes,
                content_type="application/pdf",
            )
        except Exception as e:
            logger.exception(
                "Failed to store primary source PDF (monolingual reuse)",
                extra={
                    **log_extra_base,
                    "path": primary_path,
                    "error": str(e),
                },
            )
            raise PermanentError(f"Failed to store primary source PDF: {e}")

        updated_version = await ver_repo.update_refs(
            version_id=version_uuid,
            primary_source_ref=primary_source_ref,
        )
        if not updated_version:
            raise PermanentError(
                f"Failed to update primary_source_ref for version {document_version_id}"
            )

        updated_doc = await doc_repo.update_status(
            doc_uuid,
            DocumentStatus.PRIMARY_READY.value,
            processing_error_details=None,
        )
        if not updated_doc:
            raise PermanentError(
                f"Document {document_id} not found during PRIMARY_READY status update"
            )

        await db.flush()
        refreshed_version = await ver_repo.get_by_id(version_uuid)
        if refreshed_version is None or not getattr(refreshed_version, "primary_source_ref", None):
            raise TransientError(
                f"primary_source_ref is not visible after flush for version {document_version_id}"
            )
        if refreshed_version.primary_source_ref != primary_source_ref:
            raise TransientError(
                f"primary_source_ref mismatch after flush for version {document_version_id}"
            )

        await db.commit()

        logger.info(
            "Primary source build committed successfully (monolingual reuse)",
            extra={
                **log_extra_base,
                "primary_source_ref": primary_source_ref,
                "status": DocumentStatus.PRIMARY_READY.value,
            },
        )

        audit_repo = AuditRepository(db)
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
                    "mode": "monolingual_reuse",
                    "target_language": target_language,
                    "detected_languages": decision.detected_languages,
                    "primary_source_ref": primary_source_ref,
                    "source_ref": source_ref,
                },
            )
        except Exception:
            logger.warning(
                "Primary source build: failed to write audit log for "
                "PRIMARY_SOURCE_READY (monolingual)",
                extra={
                    "document_id": document_id,
                    "document_version_id": document_version_id,
                },
            )

        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_ref": source_ref,
            "primary_source_ref": primary_source_ref,
            "target_language": target_language,
            "detected_languages": decision.detected_languages,
            "requires_user_selection": False,
            "committed": True,
        }

    # ── 9. Билингвальный документ: строим одноязычный PDF ────────────────────

    try:
        primary_pdf_bytes = build_pdf_from_layout(primary_layout)
    except Exception as e:
        logger.exception(
            "Failed to build primary PDF from layout",
            extra={
                **log_extra_base,
                "target_language": target_language,
                "error": str(e),
            },
        )
        raise PermanentError(f"Failed to build primary PDF from layout: {e}")

    if not primary_pdf_bytes or len(primary_pdf_bytes) < 700:
        raise PermanentError(
            f"build_pdf_from_layout returned empty or malformed PDF "
            f"(size={len(primary_pdf_bytes) if primary_pdf_bytes else 0}) "
            f"for version {document_version_id}. "
            "Possible cause: language filter removed all elements."
        )

    # ── 10. Сохраняем одноязычный PDF как primary_source_ref ─────────────────

    primary_path = ArtifactPath.primary_source(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
    )

    try:
        primary_source_ref = store.put_file(
            primary_path,
            primary_pdf_bytes,
            content_type="application/pdf",
        )
        logger.info(
            "Primary source build: primary single-language PDF stored",
            extra={
                **log_extra_base,
                "primary_path": primary_path,
                "primary_source_ref": primary_source_ref,
                "size": len(primary_pdf_bytes),
                "target_language": target_language,
            },
        )
    except Exception as e:
        logger.exception(
            "Failed to store primary source PDF",
            extra={
                **log_extra_base,
                "path": primary_path,
                "error": str(e),
            },
        )
        raise PermanentError(f"Failed to store primary source PDF: {e}")

    # ── 11. Обновляем DocumentVersion.primary_source_ref ─────────────────────

    updated_version = await ver_repo.update_refs(
        version_id=version_uuid,
        primary_source_ref=primary_source_ref,
    )
    if not updated_version:
        raise PermanentError(
            f"Failed to update primary_source_ref for version {document_version_id}"
        )

    # ── 12. Переводим документ в статус PRIMARY_READY ─────────────────────────

    updated_doc = await doc_repo.update_status(
        doc_uuid,
        DocumentStatus.PRIMARY_READY.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(f"Document {document_id} not found during PRIMARY_READY status update")

    # ── 13. Flush + consistency check перед commit ────────────────────────────
    #
    # Убеждаемся, что primary_source_ref виден из БД до возврата управления.
    # TransientError здесь — сигнал для Celery retry, не PermanentError.

    await db.flush()

    refreshed_version = await ver_repo.get_by_id(version_uuid)
    if refreshed_version is None or not getattr(refreshed_version, "primary_source_ref", None):
        raise TransientError(
            f"primary_source_ref is not visible after flush for version {document_version_id}"
        )
    if refreshed_version.primary_source_ref != primary_source_ref:
        raise TransientError(
            f"primary_source_ref mismatch after flush for version {document_version_id}"
        )

    await db.commit()

    logger.info(
        "Primary source build committed successfully",
        extra={
            **log_extra_base,
            "primary_source_ref": primary_source_ref,
            "status": DocumentStatus.PRIMARY_READY.value,
        },
    )

    # ── 14. Аудит ─────────────────────────────────────────────────────────────

    audit_repo = AuditRepository(db)
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
                "mode": "single_language_pdf",
                "target_language": target_language,
                "detected_languages": primary_layout_result.decision.detected_languages,
                "primary_source_ref": primary_source_ref,
                "source_ref": source_ref,
            },
        )
    except Exception:
        logger.warning(
            "Primary source build: failed to write audit log for PRIMARY_SOURCE_READY",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
            },
        )

    return {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
        "source_ref": source_ref,
        "primary_source_ref": primary_source_ref,
        "target_language": target_language,
        "detected_languages": primary_layout_result.decision.detected_languages,
        "requires_user_selection": False,
        "committed": True,
    }


def _s3_ref_to_store_path(s3_ref: str, bucket: str) -> str:
    """
    Преобразовать s3://bucket/path в path для ArtifactStore.get_file().

    Если ссылка не начинается с s3://<bucket>/, поднимаем PermanentError явно,
    чтобы не читать случайный путь молча.
    """
    prefix = f"s3://{bucket}/"
    if not s3_ref or not s3_ref.startswith(prefix):
        raise PermanentError(f"Invalid S3 ref for bucket '{bucket}': {s3_ref!r}")
    return s3_ref.replace(prefix, "", 1)


def _utcnow_iso() -> str:
    """Текущее время UTC в ISO 8601 для audit/error_details."""
    return datetime.now(tz=UTC).isoformat()
