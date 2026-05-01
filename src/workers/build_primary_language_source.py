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
- import/convert -> build_primary_language_source -> extract -> pii -> structure -> ...


Контракт:
- вызывается оркестратором или авто-пайплайном после import/convert_to_pdf;
- по завершении (успех) документ должен перейти в статус PRIMARY_READY;
- в DocumentVersion.primary_source_ref должна появиться S3‑ссылка на одноязычный PDF;
- запуск последующих стадий (extract и далее) выполняется централизованным оркестратором.
"""


import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from core.exceptions import PermanentError, TransientError


from core.config import settings
from core.constants import DocumentStatus
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories import AuditRepository
from services.document_language_pipeline import (
    build_primary_language_layout,
    MIN_TARGET_LANGUAGE_RATIO,
    _normalize_lang,
)
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.primary_pdf_builder import build_pdf_from_layout
from services.quick_pdf_layout import build_quick_layout_from_pdf
from storage.artifact_store import ArtifactPath, ArtifactStore
from services.run_orchestrator_trigger import retrigger_run_pipeline


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
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            error=str(e),
        )
        raise

    except TransientError as e:
        logger.warning(
            "Transient error during primary language source build; task should be retried",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            error=str(e),
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
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            detected_languages=result.get("detected_languages"),
        )
        return result

    # Ветка 2: построен одноязычный PDF и состояние гарантированно закоммичено.
    if run_id and committed:
        logger.info(
            "Primary language source build committed, retriggering run pipeline",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            target_language=target_language,
            primary_source_ref=primary_source_ref,
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
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        committed=committed,
        requires_user_selection=requires_user_selection,
        target_language=target_language,
        primary_source_ref=primary_source_ref,
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
    logger.info(
        "Starting build_primary_language_source",
        document_id=document_id,
        version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
    )

    ver_repo = DocumentVersionRepository(db)
    doc_repo = DocumentRepository(db)
    store = ArtifactStore(settings)

    version_uuid = uuid.UUID(document_version_id)
    doc_uuid = uuid.UUID(document_id)
    deal_uuid = uuid.UUID(deal_id)

    version = await ver_repo.get_by_id(version_uuid)
    if not version:
        raise PermanentError(f"DocumentVersion {document_version_id} not found")

    existing_primary_ref = getattr(version, "primary_source_ref", None)
    converted_pdf_ref = getattr(version, "converted_pdf_ref", None)
    original_ref = getattr(version, "original_ref", None)
    origin_filetype = getattr(version, "origin_filetype", None)

    logger.info(
        "Primary source build: resolved version refs",
        document_id=document_id,
        version_id=document_version_id,
        existing_primary_source_ref=existing_primary_ref,
        converted_pdf_ref=converted_pdf_ref,
        original_ref=original_ref,
        origin_filetype=origin_filetype,
    )

    # Выбор source_ref зависит от исходного типа:
    # - PDF: можно работать по original_ref;
    # - DOC/DOCX: строго требуем converted_pdf_ref;
    # - прочие: пробуем converted_pdf_ref, потом original_ref.
    source_ref: str | None = None
    source_kind: str | None = None

    if origin_filetype and origin_filetype.lower() in {"pdf"}:
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
        document_id=document_id,
        version_id=document_version_id,
        source_ref=source_ref,
        source_kind=source_kind,
    )

    # Если primary_source_ref уже существует И мы считаем его валидным,
    # можно было бы его переиспользовать. В варианте А мы хотим гарантированно
    # получить одноязычный PDF через новый pipeline, поэтому сейчас не
    # делаем early-return, а всегда перестраиваем primary_source.
    if existing_primary_ref:
        logger.info(
            "Primary source build: existing primary_source_ref present, "
            "rebuilding to enforce single-language PDF",
            document_id=document_id,
            version_id=document_version_id,
            existing_primary_source_ref=existing_primary_ref,
        )

    # 1. Считываем исходный PDF из MinIO.
    try:
        source_path = _s3_ref_to_store_path(source_ref, store.bucket)
        logger.info(
            "Primary source build: reading source PDF from store",
            document_id=document_id,
            version_id=document_version_id,
            source_ref=source_ref,
            source_path=source_path,
        )
        pdf_bytes = store.get_file(source_path)
        logger.info(
            "Primary source build: source PDF loaded",
            document_id=document_id,
            version_id=document_version_id,
            source_ref=source_ref,
            size=len(pdf_bytes),
        )
    except Exception as e:
        logger.exception(
            "Failed to read source PDF for primary source build",
            document_id=document_id,
            version_id=document_version_id,
            source_ref=source_ref,
            error=str(e),
        )
        raise PermanentError(f"Failed to read source PDF: {e}")

    # 2. Строим layout для раннего языкового анализа.
    quick_layout = build_quick_layout_from_pdf(
        pdf_bytes=pdf_bytes,
        document_id=document_id,
        document_version_id=document_version_id,
    )

    quick_meta = (quick_layout.get("metadata") or {}).get("quick_layout") or {}
    if quick_meta.get("degraded"):
        logger.warning(
            "Primary source build: quick layout marked as degraded",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            degraded_reason=quick_meta.get("degraded_reason"),
            total_chars=quick_meta.get("total_extracted_chars"),
            valid_bbox_ratio=quick_meta.get("valid_bbox_ratio"),
            usable_element_ratio=quick_meta.get("usable_element_ratio"),
        )

    # 3. Резолвим целевой язык:
    #    1) target_language из kwargs (от оркестратора, если он его пробросил);
    #    2) Deal.primary_language из БД.
    resolved_target_language = _normalize_lang(target_language)

    if not resolved_target_language:
        deal_repo = DealRepository(db)
        deal = await deal_repo.get_by_id(deal_uuid)
        resolved_target_language = _normalize_lang(
            getattr(deal, "primary_language", None) if deal else None
        )

    if not resolved_target_language:
        logger.warning(
            "Primary source build called without target language; "
            "pausing pipeline until user selects language",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
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
                    "reason": "no_target_language",
                },
            )
        except Exception:
            logger.warning(
                "Primary source build: failed to write audit log for PRIMARY_LANGUAGE_SELECTION_REQUIRED",
                document_id=document_id,
                document_version_id=document_version_id,
            )

        return {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_ref": source_ref,
            "primary_source_ref": existing_primary_ref,
            "target_language": None,
            "detected_languages": [],
            "requires_user_selection": True,
            "committed": False,
        }

    # 4. Строим одноязычный layout и проверяем соответствие документа целевому языку.
    primary_layout_result = await build_primary_language_layout(
        db=db,
        deal_id=deal_uuid,
        tenant_id=tenant_id,
        document_id=document_id,
        layout=quick_layout,
        target_language=resolved_target_language,   # ← язык теперь обязателен
    )

    primary_layout = primary_layout_result.primary_layout
    decision = primary_layout_result.decision
    target_language = decision.target_language

    # ── Карантин: целевой язык отсутствует или слишком мал по доле ──────────────
    # Worker обязан остановить обработку и перевести документ в QUARANTINE.
    if primary_layout_result.should_quarantine:
        logger.warning(
            "Primary source build: document quarantined due to language mismatch",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            target_language=target_language,
            detected_languages=decision.detected_languages,
            target_language_ratio=round(decision.target_language_ratio, 3),
            quarantine_reason=decision.quarantine_reason,
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
                document_id=document_id,
                document_version_id=document_version_id,
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
        document_id=document_id,
        version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        target_language=target_language,
        detected_languages=decision.detected_languages,
        is_bilingual=decision.is_bilingual,
        requires_user_selection=decision.requires_user_selection,
        language_filter_degraded=language_filter_meta.get("degraded"),
        language_filter_degraded_reason=language_filter_meta.get("degraded_reason"),
        element_retention_ratio=language_filter_meta.get("element_retention_ratio"),
    )

    # ── монолингвальный документ ─────────────────────────
    if not decision.is_bilingual:
        logger.info(
            "Primary source build: monolingual document, reusing original PDF as primary_source_ref",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            target_language=target_language,
            detected_languages=decision.detected_languages,
        )

        # 5. Сохраняем исходный PDF как primary_source_ref
        primary_path = ArtifactPath.primary_source(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=document_id,
        )
        try:
            primary_source_ref = store.put_file(
                primary_path,
                pdf_bytes,  # ← исходные байты, НЕ primary_pdf_bytes
                content_type="application/pdf",
            )
        except Exception as e:
            logger.exception(
                "Failed to store primary source PDF (monolingual reuse)",
                document_id=document_id,
                version_id=document_version_id,
                path=primary_path,
                error=str(e),
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
        if not refreshed_version or not getattr(refreshed_version, "primary_source_ref", None):
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
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            primary_source_ref=primary_source_ref,
            status=DocumentStatus.PRIMARY_READY.value,
        )

        # Аудит: primary source готов (монолингвальный reuse)
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
                "Primary source build: failed to write audit log for PRIMARY_SOURCE_READY (monolingual)",
                document_id=document_id,
                document_version_id=document_version_id,
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

    # 4. Собираем одноязычный PDF из primary_layout.
    try:
        primary_pdf_bytes = build_pdf_from_layout(primary_layout)
    except Exception as e:
        logger.exception(
            "Failed to build primary PDF from layout",
            document_id=document_id,
            version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            target_language=target_language,
            error=str(e),
        )
        raise PermanentError(f"Failed to build primary PDF from layout: {e}")

    if not primary_pdf_bytes or len(primary_pdf_bytes) < 700:
        raise PermanentError(
            f"build_pdf_from_layout returned empty or malformed PDF "
            f"(size={len(primary_pdf_bytes) if primary_pdf_bytes else 0}) "
            f"for version {document_version_id}. "
            "Possible cause: language filter removed all elements."
        )

    # 5. Сохраняем одноязычный PDF как primary_source_ref.
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
            document_id=document_id,
            version_id=document_version_id,
            primary_path=primary_path,
            primary_source_ref=primary_source_ref,
            size=len(primary_pdf_bytes),
            target_language=target_language,
        )
    except Exception as e:
        logger.exception(
            "Failed to store primary source PDF",
            document_id=document_id,
            version_id=document_version_id,
            path=primary_path,
            error=str(e),
        )
        raise PermanentError(f"Failed to store primary source PDF: {e}")

    # 6. Обновляем DocumentVersion.primary_source_ref.
    updated_version = await ver_repo.update_refs(
        version_id=version_uuid,
        primary_source_ref=primary_source_ref,
    )
    if not updated_version:
        raise PermanentError(
            f"Failed to update primary_source_ref for version {document_version_id}"
        )

    # 7. Переводим документ в статус PRIMARY_READY.
    updated_doc = await doc_repo.update_status(
        doc_uuid,
        DocumentStatus.PRIMARY_READY.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Document {document_id} not found during PRIMARY_READY status update"
        )

    # 8. Жёстко синхронизируем состояние перед возвратом:
    #    убеждаемся, что primary_source_ref действительно виден из БД.
    await db.flush()

    refreshed_version = await ver_repo.get_by_id(version_uuid)
    if not refreshed_version or not getattr(refreshed_version, "primary_source_ref", None):
        # Это именно временная несогласованность, а не бизнес‑ошибка.
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
        document_id=document_id,
        version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        primary_source_ref=primary_source_ref,
        status=DocumentStatus.PRIMARY_READY.value,
    )

    # Аудит: primary source готов (одноязычный PDF)
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
            document_id=document_id,
            document_version_id=document_version_id,
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
    Если ссылка не начинается с s3://<bucket>/, возвращаем ошибку явно,
    чтобы не читать случайный путь молча.
    """
    prefix = f"s3://{bucket}/"
    if not s3_ref or not s3_ref.startswith(prefix):
        raise PermanentError(
            f"Invalid S3 ref for bucket '{bucket}': {s3_ref}"
        )
    return s3_ref.replace(prefix, "", 1)


def _utcnow_iso() -> str:
    """Текущее время UTC в ISO 8601 для error_details."""
    return datetime.now(tz=timezone.utc).isoformat()



