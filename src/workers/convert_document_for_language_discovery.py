# src/workers/convert_document_for_language_discovery.py

"""
Pre-run document conversion worker для language discovery.

Назначение:
- Конвертировать office-форматы в PDF перед language discovery;
- Обеспечить отдельный conversion path для pre-run workflow, независимый от основного
  workers.convert_worker и analysis pipeline;
- После успешной конвертации передать управление обратно в
  workers.prepare_document_for_language_discovery для выбора downstream detector;
- Сохранять идемпотентность и совместимость с MASBaseTask.

Pipeline position:
    import_bundle
    → start_language_discovery
    → prepare_document_for_language_discovery
    → convert_document_for_language_discovery  ← этот worker
    → prepare_document_for_language_discovery (повторно)
    → detect_document_languages_native | detect_document_languages_ocr
    → recompute_deal_language_discovery_state

Контракт:
- Принимает document_id, document_version_id, deal_id, tenant_id;
- Проверяет Document.language_discovery_status (skip если completed/failed);
- Вызывает services.language_discovery_conversion_service.convert_document_for_language_discovery;
- После успеха: commit и enqueue workers.prepare_document_for_language_discovery;
- При permanent failure: фиксирует Document.language_discovery_status='failed'
  и вызывает recompute deal-статуса через shared helper;
- При transient error: re-raises для Celery retry.

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
from services.language_discovery_conversion_service import (
    convert_document_for_language_discovery,
)
from services.language_discovery_helpers import (
    mark_document_discovery_failed_and_recompute,
)

logger = get_logger(__name__)

CONVERT_LANGUAGE_DISCOVERY_TASK_NAME = "workers.convert_document_for_language_discovery"
PREPARE_LANGUAGE_DISCOVERY_TASK_NAME = "workers.prepare_document_for_language_discovery"

# Статусы, при которых conversion уже не имеет смысла.
# Используем frozenset для O(1) lookup и защиты от случайной мутации.
_SKIP_STATUSES: frozenset[LanguageDiscoveryStatus] = frozenset(
    {LanguageDiscoveryStatus.COMPLETED, LanguageDiscoveryStatus.FAILED}
)


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

    При permanent failure гарантированно вызывает recompute deal-статуса,
    чтобы deal не застрял в 'processing' при сбое воркера (race condition fix).

    :param document_id: UUID документа (строка).
    :param document_version_id: UUID версии документа (строка).
    :param deal_id: UUID сделки (строка).
    :param tenant_id: UUID тенанта (строка).
    :param db: AsyncSession для database операций.
    :return: Result dictionary с pdf_ref, status, next_task_name.
    :raises PermanentError: Document/deal/version not found, ownership mismatch,
                            conversion service error.
    :raises TransientError: Converter timeout/connection, ref не видно после flush.
    """
    doc_uuid = uuid.UUID(document_id)
    version_uuid = uuid.UUID(document_version_id)
    deal_uuid = uuid.UUID(deal_id)

    log_extra_base: dict[str, Any] = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "deal_id": deal_id,
        "tenant_id": tenant_id,
    }

    logger.info(
        "Starting pre-run document conversion for language discovery",
        extra=log_extra_base,
    )

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    deal_repo = DealRepository(db)

    # ── 1. Загрузка сущностей ──────────────────────────────────────────────────

    document = await doc_repo.get_by_id(doc_uuid)
    if document is None:
        raise PermanentError(f"Document {document_id} not found for language discovery conversion")

    deal = await deal_repo.get_by_id(deal_uuid)
    if deal is None:
        raise PermanentError(f"Deal {deal_id} not found for language discovery conversion")

    version = await ver_repo.get_by_id(version_uuid)
    if version is None:
        raise PermanentError(
            f"DocumentVersion {document_version_id} not found for language discovery conversion"
        )

    version_document_id = getattr(version, "document_id", None)
    if version_document_id != doc_uuid:
        raise PermanentError(
            "DocumentVersion does not belong to provided document_id "
            f"(document_id={document_id}, document_version_id={document_version_id})"
        )

    # ── 2. Idempotency guard ───────────────────────────────────────────────────

    current_status = document.language_discovery_status
    if current_status in _SKIP_STATUSES:
        result: dict[str, Any] = {
            **log_extra_base,
            "status": str(current_status),
            "handled": True,
            "executed": False,
            "skipped_reason": f"already_{current_status}",
        }
        logger.info(
            "Pre-run language discovery conversion skipped: document already in terminal status",
            extra=result,
        )
        return result

    # ── 3. Conversion ──────────────────────────────────────────────────────────

    try:
        conversion_result = await convert_document_for_language_discovery(
            db=db,
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )

        await db.commit()

        # Enqueue следующий шаг pipeline.
        # prepare_document_for_language_discovery повторно определит downstream detector
        # уже с заполненным converted_pdf_ref.
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
            **log_extra_base,
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
        # Transient — не трогаем статус документа, Celery сделает retry.
        logger.warning(
            "Transient error during pre-run language discovery conversion; re-raising for retry",
            extra=log_extra_base,
        )
        raise

    except PermanentError:
        # Permanent failure: фиксируем failed и пересчитываем deal-статус.
        # mark_document_discovery_failed_and_recompute содержит собственный
        # try/except, поэтому исключения внутри helper не скрывают оригинальный raise.
        logger.exception(
            "Permanent failure during pre-run language discovery conversion",
            extra=log_extra_base,
        )
        await mark_document_discovery_failed_and_recompute(
            db=db,
            document_id=doc_uuid,
            deal_id=deal_uuid,
            reason="permanent_error_in_conversion",
            extra_log=log_extra_base,
        )
        raise

    except Exception:
        # Unexpected — логируем, но считаем transient (Celery retry).
        # Статус документа не трогаем: если retry исчерпаются, Celery поднимет
        # ошибку выше и task перейдёт в FAILURE — отдельный мониторинг-алерт.
        logger.exception(
            "Unexpected error during pre-run language discovery conversion; re-raising for retry",
            extra=log_extra_base,
        )
        raise
