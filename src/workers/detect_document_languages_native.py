# src/workers/detect_document_languages_native.py

"""
Document-level native language detection worker.

Назначение:
- Выполнить native language detection для одного документа без OCR;
- Использовать доступный PDF source (original_ref / converted_pdf_ref);
- Определить языки через shared document language detection service;
- Записать результат в:
    - Document.detected_languages
    - Document.language_detection_status
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
- detect_document_languages_native (per document)
- recompute_deal_language_discovery_state
- UI показывает Deal.languages / Deal.language_discovery_status
- пользователь выбирает Deal.primary_language
- только после этого запускается Run
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.deal_language_discovery_service import (
    recompute_deal_language_discovery_state,
)
from services.document_language_detection import (
    detect_document_languages_from_pdf_bytes,
)
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

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


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.detect_document_languages_native",
    track_job=False,
    queue="default",
)
def detect_document_languages_native(
    self,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Sync Celery entrypoint для native language detection одного документа.

    Контракт:
    - получает явные IDs документа, версии, сделки и арендатора;
    - выполняет detection только по одному документу;
    - пишет completed / failed на уровне document language detection;
    - после завершения пересчитывает aggregate state сделки.

    Для непрофессионального программиста:
    - это "рабочая лошадка" pre-run language discovery;
    - orchestrator только ставит такие задачи в очередь;
    - вся реальная обработка PDF выполняется здесь.
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _detect_document_languages_native_async(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                db=uow.session,
            )

    return run_async(_wrapper())


async def _detect_document_languages_native_async(
    *,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Async-ядро native language detection для одного документа.

    Семантика ошибок:
    - TransientError:
        пробрасывается вверх без записи failed, чтобы MASBaseTask выполнил retry;
    - PermanentError:
        записываем document.language_detection_status='failed',
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
        "Starting native document language detection",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": str(tenant_uuid),
        },
    )

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    deal_repo = DealRepository(db)
    store = ArtifactStore(settings)

    document = await doc_repo.get_by_id(doc_uuid)
    if not document:
        raise PermanentError(
            f"Document {document_id} not found for language detection"
        )

    deal = await deal_repo.get_by_id(deal_uuid)
    if not deal:
        raise PermanentError(
            f"Deal {deal_id} not found for document language detection"
        )

    version = await ver_repo.get_by_id(version_uuid)
    if not version:
        raise PermanentError(
            f"DocumentVersion {document_version_id} not found for language detection"
        )

    version_document_id = getattr(version, "document_id", None)
    if version_document_id != doc_uuid:
        raise PermanentError(
            "DocumentVersion does not belong to provided document_id "
            f"(document_id={document_id}, document_version_id={document_version_id})"
        )

    current_status = getattr(document, "language_detection_status", None)
    current_languages = list(getattr(document, "detected_languages", None) or [])

    if current_status == "completed":
        recomputed = await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_uuid,
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": current_languages,
            "status": "completed",
            "handled": True,
            "executed": False,
            "idempotent_replay": True,
            "skipped_reason": "already_completed",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": str(
                recomputed.get("language_discovery_status", "pending")
            ),
        }

        logger.info(
            "Native document language detection skipped: already completed",
            extra=result,
        )
        return result

    if current_status == "processing":
        recomputed = await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_uuid,
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": current_languages,
            "status": "processing",
            "handled": True,
            "executed": False,
            "idempotent_replay": False,
            "skipped_reason": "already_processing",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": str(
                recomputed.get("language_discovery_status", "pending")
            ),
        }

        logger.info(
            "Native document language detection skipped: already processing",
            extra=result,
        )
        return result

    if current_status == "failed":
        recomputed = await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_uuid,
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": current_languages,
            "status": "failed",
            "handled": True,
            "executed": False,
            "idempotent_replay": True,
            "skipped_reason": "already_failed",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": str(
                recomputed.get("language_discovery_status", "pending")
            ),
        }

        logger.info(
            "Native document language detection skipped: already failed",
            extra=result,
        )
        return result

    claimed_doc = await doc_repo.try_mark_language_detection_processing(
        doc_uuid,
        expected_current_status="pending",
        preserve_detected_languages=current_languages,
    )

    if not claimed_doc:
        refreshed_document = await doc_repo.get_by_id(doc_uuid)
        refreshed_status = (
            getattr(refreshed_document, "language_detection_status", None)
            if refreshed_document
            else None
        )
        refreshed_languages = (
            list(getattr(refreshed_document, "detected_languages", None) or [])
            if refreshed_document
            else []
        )

        recomputed = await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_uuid,
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "detected_languages": refreshed_languages,
            "status": str(refreshed_status or "unknown"),
            "handled": True,
            "executed": False,
            "idempotent_replay": False,
            "skipped_reason": "claim_not_acquired",
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": str(
                recomputed.get("language_discovery_status", "pending")
            ),
        }

        logger.info(
            "Native document language detection skipped: atomic processing claim not acquired",
            extra=result,
        )
        return result

    try:
        source_ref = _resolve_source_pdf_ref(version)
        if not source_ref:
            raise PermanentError(
                "No suitable PDF source ref for native language detection "
                f"(document_id={document_id}, version_id={document_version_id}, "
                f"origin_filetype={getattr(version, 'origin_filetype', None)})"
            )

        logger.info(
            "Native language detection: reading PDF source from storage",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "source_ref": source_ref,
            },
        )

        try:
            pdf_bytes = store.get_file(source_ref)
        except TransientError:
            raise
        except Exception as e:
            raise PermanentError(
                f"Failed to read source PDF for language detection: {e}"
            ) from e

        if not pdf_bytes:
            raise PermanentError(
                "Source PDF is empty for native language detection "
                f"(document_id={document_id}, version_id={document_version_id})"
            )

        detection_result = detect_document_languages_from_pdf_bytes(
            pdf_bytes=pdf_bytes,
            document_id=document_id,
            document_version_id=document_version_id,
        )

        detected_languages = list(detection_result.detected_languages or [])

        await doc_repo.update_language_detection(
            doc_uuid,
            detected_languages=detected_languages,
            status="completed",
        )

        recomputed = await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_uuid,
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_ref": source_ref,
            "detected_languages": detected_languages,
            "status": "completed",
            "handled": True,
            "executed": True,
            "idempotent_replay": False,
            "deal_languages": list(recomputed.get("languages", [])),
            "deal_language_discovery_status": str(
                recomputed.get("language_discovery_status", "pending")
            ),
        }

        logger.info(
            "Native document language detection completed successfully",
            extra=result,
        )

        return result

    except TransientError:
        logger.warning(
            "Transient error during native document language detection; re-raising for retry",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
            },
        )
        raise

    except PermanentError:
        logger.exception(
            "Permanent failure during native document language detection",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
            },
        )

        await _mark_document_detection_failed_and_recompute(
            db=db,
            document_id=doc_uuid,
            deal_id=deal_uuid,
        )
        raise

    except Exception as e:
        logger.exception(
            "Unexpected error during native document language detection; re-raising for retry",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        raise


async def _mark_document_detection_failed_and_recompute(
    *,
    db: AsyncSession,
    document_id: uuid.UUID,
    deal_id: uuid.UUID,
) -> None:
    """
    Зафиксировать окончательный failed-state document language detection
    и пересчитать aggregate состояние сделки.

    Используется только для permanent failures.
    """
    doc_repo = DocumentRepository(db)

    await doc_repo.update_language_detection(
        document_id,
        detected_languages=[],
        status="failed",
    )

    await recompute_deal_language_discovery_state(
        db=db,
        deal_id=deal_id,
    )


def _resolve_source_pdf_ref(version) -> str | None:
    """
    Выбрать PDF source для native language detection.

    Production contract:
    - если исходный тип = PDF -> берем original_ref;
    - если исходный тип = office format -> берем только converted_pdf_ref;
    - если исходный тип = image -> native route недопустим, возвращаем None;
    - для неизвестных форматов допускаем только converted_pdf_ref.

    Возвращает:
    - S3 ref на PDF-файл, либо None, если подходящего источника нет.
    """
    origin_filetype = (getattr(version, "origin_filetype", None) or "").strip().lower()
    converted_pdf_ref = getattr(version, "converted_pdf_ref", None)
    original_ref = getattr(version, "original_ref", None)

    if origin_filetype == "pdf":
        return original_ref

    if origin_filetype in OFFICE_FILETYPES:
        return converted_pdf_ref

    if origin_filetype in IMAGE_FILETYPES:
        return None

    return converted_pdf_ref





