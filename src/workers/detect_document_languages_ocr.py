# src/workers/detect_document_languages_ocr.py

"""
Document-level OCR language detection worker.

Назначение:
- Выполнить quick OCR-based language detection для одного документа;
- Использовать scanned PDF / image source;
- Сделать быстрый OCR только по ограниченному числу первых страниц/изображений;
- Определить языки через shared document language detection service;
- Записать результат в:
    - Document.detected_languages
    - Document.language_discovery_status
- Пересчитать aggregate language discovery state сделки через
  deal_language_discovery_service.

Важно:
- Это document-level worker в pre-run language discovery pipeline.
- Он не зависит от Run и не меняет основной Document.status.
- Он должен быть идемпотентным и безопасным для повторного запуска.
- Он согласован с MASBaseTask:
    * transient ошибки пробрасываются вверх для retry;
    * permanent ошибки фиксируют failed-state и затем бросаются как исключение;
    * success-path возвращает нормальный result dict.

Поток:
- import_bundle
- start_language_discovery
- prepare_document_for_language_discovery (для office форматов)
- convert_document_for_language_discovery (для office форматов)
- prepare_document_for_language_discovery (повторно, роутит на OCR после конвертации)
- detect_document_languages_ocr (per document)
- recompute_deal_language_discovery_state
- UI показывает Deal.languages / Deal.language_discovery_status
- пользователь выбирает Deal.primary_language
- только после этого запускается Run

Важное замечание по filetype:
- origin_filetype хранит исходный формат файла ('doc', 'docx', 'pdf', 'png', ...);
- для office-форматов source для OCR — это converted_pdf_ref (PDF после конвертации);
- при вызове extract_quick_ocr_text_for_language_detection нужно передавать
  эффективный тип файла ('pdf'), а не origin_filetype ('doc');
- _resolve_source_ocr_ref и _resolve_effective_ocr_filetype согласованы по одной логике.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import LanguageDiscoveryStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.document_language_detection import (
    detect_document_languages_from_text,
)
from services.document_ocr_language_detection import (
    extract_quick_ocr_text_for_language_detection,
)
from services.language_discovery_helpers import (
    mark_document_discovery_failed_and_recompute,
    recompute_deal_discovery_or_log,
)
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


QUICK_OCR_MAX_PAGES = 3
QUICK_OCR_MAX_IMAGES = 3


OFFICE_FILETYPES = {
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "rtf",
    "csv",
    "html",
    "htm",
}


IMAGE_FILETYPES = {
    "png",
    "jpg",
    "jpeg",
    "tif",
    "tiff",
    "bmp",
    "webp",
}

# Единственный статус, с которого этот worker легитимно начинает обработку.
# Orchestrator переводит документ из NULL/failed -> pending перед dispatch.
_EXPECTED_ENTRY_STATUS = LanguageDiscoveryStatus.PENDING


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.detect_document_languages_ocr",
    track_job=False,
    queue="default",
)
def detect_document_languages_ocr(
    self,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Sync Celery entrypoint для OCR language detection одного документа.

    Контракт:
    - получает явные IDs документа, версии, сделки и арендатора;
    - выполняет detection только по одному документу;
    - пишет completed / failed на уровне document language discovery;
    - после завершения пересчитывает aggregate state сделки.
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _detect_document_languages_ocr_async(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                db=uow.session,
            )

    return run_async(_wrapper())


async def _detect_document_languages_ocr_async(
    *,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Async-ядро OCR language detection для одного документа.

    Семантика ошибок:
    - TransientError:
        пробрасывается вверх без записи failed, чтобы MASBaseTask выполнил retry;
    - PermanentError:
        записываем document.language_discovery_status='failed',
        пересчитываем aggregate state сделки,
        затем пробрасываем ошибку вверх;
    - success:
        записываем completed и возвращаем result.

    Идемпотентность:
    - duplicate delivery одной и той же document task допустима;
    - worker атомарно claim'ит переход pending -> processing;
    - если документ уже completed, worker возвращает idempotent success;
    - если документ уже processing другим worker'ом, текущий запуск
      корректно выходит без повторной обработки;
    - если документ уже failed, worker считает это terminal state и не пытается
      снова выполнять detection в рамках этой же task delivery.
    """
    doc_uuid = uuid.UUID(document_id)
    version_uuid = uuid.UUID(document_version_id)
    deal_uuid = uuid.UUID(deal_id)
    tenant_uuid = uuid.UUID(tenant_id)

    logger.info(
        "Starting OCR document language detection",
        document_id=document_id,
        document_version_id=document_version_id,
        deal_id=deal_id,
        tenant_id=str(tenant_uuid),
    )

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    deal_repo = DealRepository(db)
    store = ArtifactStore(settings)

    # ── Валидация входных сущностей ──────────────────────────────────────────

    document = await doc_repo.get_by_id(doc_uuid)
    if not document:
        raise PermanentError(f"Document {document_id} not found for OCR language detection")

    deal = await deal_repo.get_by_id(deal_uuid)
    if not deal:
        raise PermanentError(f"Deal {deal_id} not found for OCR document language detection")

    version = await ver_repo.get_by_id(version_uuid)
    if not version:
        raise PermanentError(
            f"DocumentVersion {document_version_id} not found for OCR language detection"
        )

    version_document_id = getattr(version, "document_id", None)
    if version_document_id != doc_uuid:
        raise PermanentError(
            "DocumentVersion does not belong to provided document_id "
            f"(document_id={document_id}, document_version_id={document_version_id})"
        )

    # ── Idempotency guard ────────────────────────────────────────────────────
    # Читаем текущий document-level discovery status через канонический атрибут.

    current_status = document.language_discovery_status
    current_languages = list(document.detected_languages or [])

    if current_status == LanguageDiscoveryStatus.COMPLETED:
        recomputed = await recompute_deal_discovery_or_log(
            db=db,
            deal_id=deal_uuid,
            context="idempotent_already_completed",
            extra_log={
                "document_id": document_id,
                "document_version_id": document_version_id,
            },
        )
        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": current_languages,
            "status": LanguageDiscoveryStatus.COMPLETED.value,
            "handled": True,
            "executed": False,
            "idempotent_replay": True,
            "skipped_reason": "already_completed",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": (
                recomputed.get("language_discovery_status", LanguageDiscoveryStatus.PENDING).value
                if isinstance(recomputed.get("language_discovery_status"), LanguageDiscoveryStatus)
                else str(
                    recomputed.get(
                        "language_discovery_status", LanguageDiscoveryStatus.PENDING.value
                    )
                )
            ),
        }
        logger.info(
            "OCR document language detection skipped: already completed",
            **result,
        )
        return result

    if current_status == LanguageDiscoveryStatus.PROCESSING:
        recomputed = await recompute_deal_discovery_or_log(
            db=db,
            deal_id=deal_uuid,
            context="idempotent_already_processing",
            extra_log={
                "document_id": document_id,
                "document_version_id": document_version_id,
            },
        )
        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": current_languages,
            "status": LanguageDiscoveryStatus.PROCESSING.value,
            "handled": True,
            "executed": False,
            "idempotent_replay": False,
            "skipped_reason": "already_processing",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": (
                recomputed.get("language_discovery_status", LanguageDiscoveryStatus.PENDING).value
                if isinstance(recomputed.get("language_discovery_status"), LanguageDiscoveryStatus)
                else str(
                    recomputed.get(
                        "language_discovery_status", LanguageDiscoveryStatus.PENDING.value
                    )
                )
            ),
        }
        logger.info(
            "OCR document language detection skipped: already processing",
            **result,
        )
        return result

    if current_status == LanguageDiscoveryStatus.FAILED:
        recomputed = await recompute_deal_discovery_or_log(
            db=db,
            deal_id=deal_uuid,
            context="idempotent_already_failed",
            extra_log={
                "document_id": document_id,
                "document_version_id": document_version_id,
            },
        )
        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": current_languages,
            "status": LanguageDiscoveryStatus.FAILED.value,
            "handled": True,
            "executed": False,
            "idempotent_replay": True,
            "skipped_reason": "already_failed",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": (
                recomputed.get("language_discovery_status", LanguageDiscoveryStatus.PENDING).value
                if isinstance(recomputed.get("language_discovery_status"), LanguageDiscoveryStatus)
                else str(
                    recomputed.get(
                        "language_discovery_status", LanguageDiscoveryStatus.PENDING.value
                    )
                )
            ),
        }
        logger.info(
            "OCR document language detection skipped: already failed",
            **result,
        )
        return result

    # ── Аномальный статус: не pending и не terminal ──────────────────────────
    # Ожидаем LanguageDiscoveryStatus.PENDING как единственный легитимный входной статус.
    # Если статус иной — это либо bug в orchestrator, либо race с другим pipeline.
    # Логируем предупреждение и бросаем TransientError: retry позволит
    # системе осесть в корректное состояние, не маскируя проблему как permanent.

    if current_status != _EXPECTED_ENTRY_STATUS:
        logger.warning(
            "OCR document language detection: unexpected document status at entry; "
            "expected 'pending', got %r — possible orchestrator/pipeline race",
            current_status,
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            current_status=current_status,
        )
        raise TransientError(
            f"Unexpected document language discovery status '{current_status}' "
            f"for document {document_id}; expected 'pending'. "
            "Will retry to allow orchestrator/pipeline to settle."
        )

    # ── Атомарный claim: pending -> processing ───────────────────────────────

    claimed_doc = await doc_repo.try_mark_language_discovery_processing(
        doc_uuid,
        expected_current_status=_EXPECTED_ENTRY_STATUS,
        preserve_detected_languages=current_languages,
    )

    if not claimed_doc:
        # Claim не прошёл: кто-то другой уже перевёл документ из pending.
        refreshed_document = await doc_repo.get_by_id(doc_uuid)
        refreshed_status = (
            refreshed_document.language_discovery_status if refreshed_document else None
        )
        refreshed_languages = (
            list(refreshed_document.detected_languages or []) if refreshed_document else []
        )

        recomputed = await recompute_deal_discovery_or_log(
            db=db,
            deal_id=deal_uuid,
            context="claim_not_acquired",
            extra_log={
                "document_id": document_id,
                "document_version_id": document_version_id,
            },
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": refreshed_languages,
            "status": (
                refreshed_status.value
                if isinstance(refreshed_status, LanguageDiscoveryStatus)
                else str(refreshed_status or "unknown")
            ),
            "handled": True,
            "executed": False,
            "idempotent_replay": False,
            "skipped_reason": "claim_not_acquired",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": (
                recomputed.get("language_discovery_status", LanguageDiscoveryStatus.PENDING).value
                if isinstance(recomputed.get("language_discovery_status"), LanguageDiscoveryStatus)
                else str(
                    recomputed.get(
                        "language_discovery_status", LanguageDiscoveryStatus.PENDING.value
                    )
                )
            ),
        }

        logger.info(
            "OCR document language detection skipped: atomic processing claim not acquired",
            **result,
        )
        return result

    # ── Основная обработка ───────────────────────────────────────────────────
    # Документ успешно переведён в processing. Всё, что ниже, должно
    # завершиться либо completed, либо failed — без промежуточных состояний.

    try:
        source_ref = _resolve_source_ocr_ref(version)
        if not source_ref:
            raise PermanentError(
                "No suitable OCR source ref for document language detection "
                f"(document_id={document_id}, version_id={document_version_id}, "
                f"origin_filetype={getattr(version, 'origin_filetype', None)})"
            )

        effective_filetype = _resolve_effective_ocr_filetype(version)

        logger.info(
            "OCR language detection: reading source from storage",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            source_ref=source_ref,
            origin_filetype=getattr(version, "origin_filetype", None),
            effective_filetype=effective_filetype,
        )

        try:
            source_bytes = store.get_file(source_ref)
        except TransientError:
            raise
        except Exception as e:
            raise PermanentError(f"Failed to read OCR source for language detection: {e}") from e

        if not source_bytes:
            raise PermanentError(
                "OCR source is empty for language detection "
                f"(document_id={document_id}, version_id={document_version_id})"
            )

        ocr_text = extract_quick_ocr_text_for_language_detection(
            source_bytes=source_bytes,
            source_filename=getattr(version, "filename", None) or document_id,
            origin_filetype=effective_filetype,
            max_pages=QUICK_OCR_MAX_PAGES,
            max_images=QUICK_OCR_MAX_IMAGES,
        )

        if not ocr_text or not ocr_text.strip():
            raise PermanentError(
                "Quick OCR produced empty text for language detection "
                f"(document_id={document_id}, version_id={document_version_id})"
            )

        detection_result = detect_document_languages_from_text(
            text=ocr_text,
            document_id=document_id,
            document_version_id=document_version_id,
        )

        detected_languages = list(detection_result.detected_languages or [])

        await doc_repo.update_language_discovery(
            doc_uuid,
            detected_languages=detected_languages,
            status=LanguageDiscoveryStatus.COMPLETED,
        )

        recomputed = await recompute_deal_discovery_or_log(
            db=db,
            deal_id=deal_uuid,
            context="success",
            extra_log={
                "document_id": document_id,
                "document_version_id": document_version_id,
            },
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_ref": source_ref,
            "origin_filetype": getattr(version, "origin_filetype", None),
            "effective_filetype": effective_filetype,
            "detected_languages": detected_languages,
            "status": LanguageDiscoveryStatus.COMPLETED.value,
            "handled": True,
            "executed": True,
            "idempotent_replay": False,
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": (
                recomputed.get("language_discovery_status", LanguageDiscoveryStatus.PENDING).value
                if isinstance(recomputed.get("language_discovery_status"), LanguageDiscoveryStatus)
                else str(
                    recomputed.get(
                        "language_discovery_status", LanguageDiscoveryStatus.PENDING.value
                    )
                )
            ),
        }

        logger.info(
            "OCR document language detection completed successfully",
            **result,
        )
        return result

    except TransientError:
        # Transient: не пишем failed. MASBaseTask выполнит retry.
        # Документ остаётся в processing — stuck-pending repair job подберёт
        # его при необходимости, если все retries исчерпаются.
        logger.warning(
            "Transient error during OCR document language detection; re-raising for retry",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )
        raise

    except PermanentError:
        # Permanent: фиксируем failed, пересчитываем aggregate state сделки,
        # затем пробрасываем вверх для записи в MASBaseTask job log.
        logger.exception(
            "Permanent failure during OCR document language detection",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )
        await mark_document_discovery_failed_and_recompute(
            db=db,
            document_id=doc_uuid,
            deal_id=deal_uuid,
            reason="permanent_error",
            extra_log={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
            },
        )
        raise

    except Exception as e:
        # Неожиданное исключение: трактуем как transient — retry.
        # Не пишем failed: неизвестно, была ли это постоянная или временная проблема.
        logger.exception(
            "Unexpected error during OCR document language detection; re-raising for retry",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            error=str(e),
        )
        raise


def _resolve_source_ocr_ref(version: Any) -> str | None:
    """
    Выбрать source ref для OCR language detection.

    Production contract:
    - для image input используем original_ref;
    - для PDF input используем original_ref;
    - для office formats используем только converted_pdf_ref;
    - для неизвестных форматов допускаем только converted_pdf_ref.

    Это исключает ошибочный путь, когда OCR worker пытается читать raw DOCX/XLSX/PPTX
    вместо уже подготовленного PDF.

    Согласован с _resolve_effective_ocr_filetype: оба метода используют одну
    и ту же классификацию по origin_filetype.
    """
    original_ref = getattr(version, "original_ref", None)
    converted_pdf_ref = getattr(version, "converted_pdf_ref", None)
    origin_filetype = (getattr(version, "origin_filetype", None) or "").strip().lower()

    if origin_filetype in IMAGE_FILETYPES:
        return original_ref

    if origin_filetype == "pdf":
        return original_ref

    if origin_filetype in OFFICE_FILETYPES:
        return converted_pdf_ref

    return converted_pdf_ref


def _resolve_effective_ocr_filetype(version: Any) -> str:
    """
    Определить эффективный тип файла для передачи в OCR-детектор.

    Важно: origin_filetype хранит исходный формат документа ('doc', 'docx', ...),
    но для office-форматов OCR читает converted_pdf_ref — то есть реальный
    источник байтов является PDF. Передача origin_filetype ('doc') в OCR-детектор
    приведёт к PermanentError, так как детектор ожидает 'pdf' или image-тип.

    Логика классификации согласована с _resolve_source_ocr_ref:
    - image input  → original_ref  → возвращаем origin_filetype ('png', 'jpg', ...)
    - PDF input    → original_ref  → возвращаем 'pdf'
    - office input → converted_pdf_ref → возвращаем 'pdf'
    - unknown      → converted_pdf_ref → возвращаем 'pdf'
    """
    origin_filetype = (getattr(version, "origin_filetype", None) or "").strip().lower()

    if origin_filetype in IMAGE_FILETYPES:
        return origin_filetype

    if origin_filetype == "pdf":
        return "pdf"

    if origin_filetype in OFFICE_FILETYPES:
        return "pdf"

    return "pdf"
