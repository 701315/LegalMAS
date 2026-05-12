# src/workers/convert_document_for_language_discovery.py

"""
Pre-run document conversion worker для language discovery.

Назначение:
- Конвертировать office-форматы в PDF перед language detection;
- Обеспечить отдельный conversion path для pre-run workflow, независимый от основного
  workers.convert_worker и analysis pipeline;
- После успешной конвертации передать управление обратно в
  workers.prepare_document_for_language_discovery для выбора downstream detector;
- Сохранять идемпотентность и совместимость с MASBaseTask.

Pipeline position:
- import_bundle
- start_language_discovery
- prepare_document_for_language_discovery
- convert_document_for_language_discovery ← этот worker
- prepare_document_for_language_discovery (повторно)
- detect_document_languages_native | detect_document_languages_ocr
- recompute_deal_language_discovery_state

Контракт:
- Принимает document_id, document_version_id, deal_id, tenant_id;
- Проверяет Document.language_detection_status (skip если completed/failed);
- Вызывает services.language_discovery_conversion_service.convert_document_for_language_discovery;
- После успеха commit и enqueue workers.prepare_document_for_language_discovery;
- При permanent failure пишет Document.language_detection_status='failed';
- При transient error re-raises для Celery retry.

Ошибки:
- PermanentError: document/deal/version not found, version ownership mismatch,
  unsupported filetype, missing original_ref, conversion service error;
- TransientError: converter timeout/connection, version disappeared after flush,
  converted_pdf_ref не видно после flush.

Использование:
- Вызывается из workers.prepare_document_for_language_discovery, если
  origin_filetype in OFFICE_FILETYPES и converted_pdf_ref пуст;
- НЕ вызывается из run-stage workers или основного pipeline.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.language_discovery_conversion_service import (
    convert_document_for_language_discovery,
)

logger = get_logger(__name__)

CONVERT_LANGUAGE_DISCOVERY_TASK_NAME = "workers.convert_document_for_language_discovery"
PREPARE_LANGUAGE_DISCOVERY_TASK_NAME = "workers.prepare_document_for_language_discovery"


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name=CONVERT_LANGUAGE_DISCOVERY_TASK_NAME,
    track_job=False,
    queue="default",
)
def convert_document_for_language_discovery_task(
    self,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Sync Celery entrypoint для pre-run document conversion.

    :param document_id: UUID документа.
    :param document_version_id: UUID версии документа.
    :param deal_id: UUID сделки.
    :param tenant_id: UUID тенанта.
    :return: Result dictionary с pdf_ref, status, next_task_name.
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _convert_document_for_language_discovery_async(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                db=uow.session,
            )

    return run_async(_wrapper())


async def _convert_document_for_language_discovery_async(
    *,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Async-ядро pre-run document conversion.

    :param document_id: UUID документа.
    :param document_version_id: UUID версии документа.
    :param deal_id: UUID сделки.
    :param tenant_id: UUID тенанта.
    :param db: AsyncSession для database операций.
    :return: Result dictionary с pdf_ref, status, next_task_name.
    :raises PermanentError: Document/deal/version not found, ownership mismatch,
                            conversion service error.
    :raises TransientError: Converter timeout/connection, ref не видно после flush.
    """
    doc_uuid = uuid.UUID(document_id)
    version_uuid = uuid.UUID(document_version_id)
    deal_uuid = uuid.UUID(deal_id)

    logger.info(
        "Starting pre-run document conversion for language discovery",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
        },
    )

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    deal_repo = DealRepository(db)

    document = await doc_repo.get_by_id(doc_uuid)
    if not document:
        raise PermanentError(
            f"Document {document_id} not found for language discovery conversion"
        )

    deal = await deal_repo.get_by_id(deal_uuid)
    if not deal:
        raise PermanentError(
            f"Deal {deal_id} not found for language discovery conversion"
        )

    version = await ver_repo.get_by_id(version_uuid)
    if not version:
        raise PermanentError(
            f"DocumentVersion {document_version_id} not found for language discovery conversion"
        )

    version_document_id = getattr(version, "document_id", None)
    if version_document_id != doc_uuid:
        raise PermanentError(
            "DocumentVersion does not belong to provided document_id "
            f"(document_id={document_id}, document_version_id={document_version_id})"
        )

    current_status = getattr(document, "language_detection_status", None)
    if current_status in {"completed", "failed"}:
        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "status": str(current_status),
            "handled": True,
            "executed": False,
            "skipped_reason": f"already_{current_status}",
        }
        logger.info(
            "Pre-run language discovery conversion skipped",
            extra=result,
        )
        return result

    try:
        conversion_result = await convert_document_for_language_discovery(
            db=db,
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )

        await db.commit()

        celery_app.send_task(
            PREPARE_LANGUAGE_DISCOVERY_TASK_NAME,
            kwargs={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
            },
            retry=True,
            retry_policy={
                "max_retries": 3,
                "interval_start": 1,
                "interval_step": 2,
                "interval_max": 5,
            },
        )

        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "status": "converted",
            "handled": True,
            "executed": True,
            "pdf_ref": conversion_result.pdf_ref,
            "origin_filetype": conversion_result.origin_filetype,
            "next_task_name": PREPARE_LANGUAGE_DISCOVERY_TASK_NAME,
        }

        logger.info(
            "Pre-run document conversion for language discovery completed",
            extra=result,
        )
        return result

    except TransientError:
        logger.warning(
            "Transient error during pre-run language discovery conversion; re-raising for retry",
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
            "Permanent failure during pre-run language discovery conversion",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
            },
        )
        await doc_repo.update_language_detection(
            doc_uuid,
            detected_languages=[],
            status="failed",
        )
        await db.commit()
        raise

    except Exception as e:
        logger.exception(
            "Unexpected error during pre-run language discovery conversion; re-raising for retry",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        raise

    