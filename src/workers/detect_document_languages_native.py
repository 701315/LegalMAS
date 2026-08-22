"""
Detect Document Languages Native Worker.

Выполняет предварительную быструю разметку языков документа для UX-слоя (pre-run discovery).
Использует PyMuPDF + universal language_classifier без обращения к legacy-модулям.
"""

from __future__ import annotations

import uuid
from typing import Any

import pymupdf as fitz
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import LanguageDiscoveryStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories import DocumentRepository, DocumentVersionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.deal_language_discovery_service import recompute_deal_language_discovery_state
from services.deal_language_service import update_deal_languages
from services.document_layout.language_classifier import classify_text
from storage.artifact_store import ArtifactStore
from core.tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


def _detect_languages_from_bytes(pdf_bytes: bytes) -> list[str]:
    """
    Точное и универсальное определение присутствующих языков для UX-слоя.
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        detected = set()

        total_cyrillic = 0
        total_latin = 0

        for page in doc:
            text = page.get_text()
            if text and text.strip():
                res = classify_text(text)
                if res.evidence:
                    total_cyrillic += res.evidence.cyrillic_chars
                    total_latin += res.evidence.latin_chars

        doc.close()

        if total_cyrillic >= 5:
            detected.add("ru")
        if total_latin >= 5:
            detected.add("en")

        return sorted(list(detected)) if detected else ["ru"]
    except Exception as e:
        logger.warning("Native language discovery fallback to ru", error=str(e))
        return ["ru"]


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.detect_document_languages_native",
    track_job=False,
    queue="default",
)
def detect_document_languages_native(
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

            await doc_repo.update_language_discovery(
                doc_uuid,
                detected_languages=langs,
                status=LanguageDiscoveryStatus.COMPLETED,
            )

            await uow.session.flush()

            if langs:
                await update_deal_languages(uow.session, deal_uuid, langs)

            await recompute_deal_language_discovery_state(db=uow.session, deal_id=deal_uuid)
            await uow.session.commit()

            return {
                "document_id": document_id,
                "detected_languages": langs,
                "status": "completed",
            }

    return run_async(_wrapper())
