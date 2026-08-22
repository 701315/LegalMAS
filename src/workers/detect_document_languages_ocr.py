"""
Detect Document Languages OCR Worker.

Fallback воркер предварительного обнаружения языков (pre-run discovery).
Использует универсальный language_classifier без обращения к legacy-модулям.
Обновляет языки документа, сделки и пересчитывает Deal.language_discovery_status.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.config import settings
from core.constants import LanguageDiscoveryStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories import DocumentRepository, DocumentVersionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.deal_language_discovery_service import (
    recompute_deal_language_discovery_state,
)
from services.deal_language_service import update_deal_languages
from storage.artifact_store import ArtifactStore
from workers.detect_document_languages_native import _detect_languages_from_bytes
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.detect_document_languages_ocr",
    track_job=False,
    queue="default",
)
def detect_document_languages_ocr(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
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
            store = ArtifactStore(settings)
            ver_repo = DocumentVersionRepository(uow.session)
            doc_repo = DocumentRepository(uow.session)

            version = await ver_repo.get_by_id(uuid.UUID(document_version_id))
            if not version:
                raise PermanentError(f"DocumentVersion {document_version_id} not found")

            source_ref = version.converted_pdf_ref or version.original_ref
            if not source_ref:
                raise PermanentError(f"No source ref for version {document_version_id}")

            pdf_path = source_ref.replace(f"s3://{store.bucket}/", "")
            pdf_bytes = store.get_file(pdf_path)

            langs = _detect_languages_from_bytes(pdf_bytes)

            doc_uuid = uuid.UUID(document_id)
            deal_uuid = uuid.UUID(deal_id)

            # 1. Обновляем языки и статус документа
            await doc_repo.update_language_discovery(
                doc_uuid,
                detected_languages=langs,
                status=LanguageDiscoveryStatus.COMPLETED,
            )

            await uow.session.flush()

            # 2. Обновляем языки сделки
            if langs:
                await update_deal_languages(uow.session, deal_uuid, langs)

            # 3. Пересчитываем статус обнаружения языков по всей сделке (именованные аргументы!)
            await recompute_deal_language_discovery_state(db=uow.session, deal_id=deal_uuid)

            await uow.session.commit()

            logger.info(
                "Document & Deal language discovery completed via OCR worker",
                document_id=document_id,
                deal_id=deal_id,
                detected_languages=langs,
            )

            return {
                "document_id": document_id,
                "detected_languages": langs,
                "status": "completed",
            }

    return run_async(_wrapper())
