# src/workers/prepare_document_for_language_discovery.py

"""
Document preparation worker for pre-run language discovery.

Назначение:
- Подготовить документ к language discovery, если исходный формат не является
  прямым PDF/image input для downstream detector'ов;
- Для office-like форматов обеспечить наличие converted_pdf_ref через
  отдельный pre-run conversion worker;
- После успешной подготовки выбрать downstream detector:
    - workers.detect_document_languages_native
    - workers.detect_document_languages_ocr
- Не выполнять собственно language detection внутри этого worker;
- Не менять основной Document.status;
- Сохранять идемпотентность и совместимость с MASBaseTask.

Pipeline:
- import_bundle
- start_language_discovery
- prepare_document_for_language_discovery
- convert_document_for_language_discovery (if needed)
- detect_document_languages_native | detect_document_languages_ocr
- recompute_deal_language_discovery_state
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

logger = get_logger(__name__)

PREPARE_LANGUAGE_DISCOVERY_TASK_NAME = "workers.prepare_document_for_language_discovery"
CONVERT_LANGUAGE_DISCOVERY_TASK_NAME = "workers.convert_document_for_language_discovery"
NATIVE_LANGUAGE_DISCOVERY_TASK_NAME = "workers.detect_document_languages_native"
OCR_LANGUAGE_DISCOVERY_TASK_NAME = "workers.detect_document_languages_ocr"

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

OCR_PIPELINE_STRATEGIES = {
    "pdf_ocr",
    "docx_via_pdf_ocr",
    "image_ocr",
    "ocr_only",
    "hybrid_ocr",
}

NATIVE_PIPELINE_STRATEGIES = {
    "pdf_native",
    "docx_via_pdf_native",
}

OCR_EXTRACTION_STRATEGIES = {
    "ocr_only",
    "hybrid",
}

NATIVE_EXTRACTION_STRATEGIES = {
    "pdfplumber",
}

DEFAULT_OCR_CONFIDENCE_THRESHOLD = 0.70


def _normalize_route_value(value: Any) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_ocr_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None

    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def _select_downstream_task_name(version: Any) -> str:
    """
    Выбрать downstream detector после prepare stage.

    Контракт:
    - office formats после конвертации по умолчанию идут в OCR как safest path;
    - PDF route может идти в native, если это явно native-compatible;
    - image formats идут в OCR;
    - ambiguous route => OCR.
    """
    pipeline_strategy = _normalize_route_value(
        getattr(version, "pipeline_strategy", None)
    )
    extraction_strategy = _normalize_route_value(
        getattr(version, "extraction_strategy", None)
    )
    origin_filetype = _normalize_route_value(
        getattr(version, "origin_filetype", None)
    )
    ocr_confidence = _normalize_ocr_confidence(
        getattr(version, "ocr_confidence", None)
    )

    if origin_filetype in IMAGE_FILETYPES:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if origin_filetype in OFFICE_FILETYPES:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if pipeline_strategy in OCR_PIPELINE_STRATEGIES:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if pipeline_strategy in NATIVE_PIPELINE_STRATEGIES:
        return NATIVE_LANGUAGE_DISCOVERY_TASK_NAME

    if extraction_strategy in OCR_EXTRACTION_STRATEGIES:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if extraction_strategy in NATIVE_EXTRACTION_STRATEGIES:
        return NATIVE_LANGUAGE_DISCOVERY_TASK_NAME

    if ocr_confidence is not None and ocr_confidence < DEFAULT_OCR_CONFIDENCE_THRESHOLD:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if origin_filetype == "pdf":
        return NATIVE_LANGUAGE_DISCOVERY_TASK_NAME

    return OCR_LANGUAGE_DISCOVERY_TASK_NAME


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name=PREPARE_LANGUAGE_DISCOVERY_TASK_NAME,
    track_job=False,
    queue="default",
)
def prepare_document_for_language_discovery(
    self,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _prepare_document_for_language_discovery_async(
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                db=uow.session,
            )

    return run_async(_wrapper())


async def _prepare_document_for_language_discovery_async(
    *,
    document_id: str,
    document_version_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    doc_uuid = uuid.UUID(document_id)
    version_uuid = uuid.UUID(document_version_id)
    deal_uuid = uuid.UUID(deal_id)
    tenant_uuid = uuid.UUID(tenant_id)

    logger.info(
        "Starting document preparation for language discovery",
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

    document = await doc_repo.get_by_id(doc_uuid)
    if not document:
        raise PermanentError(
            f"Document {document_id} not found for prepare language discovery"
        )

    deal = await deal_repo.get_by_id(deal_uuid)
    if not deal:
        raise PermanentError(
            f"Deal {deal_id} not found for prepare language discovery"
        )

    version = await ver_repo.get_by_id(version_uuid)
    if not version:
        raise PermanentError(
            f"DocumentVersion {document_version_id} not found for prepare language discovery"
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
        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "status": "completed",
            "handled": True,
            "executed": False,
            "idempotent_replay": True,
            "skipped_reason": "already_completed",
            "detected_languages": current_languages,
        }
        logger.info(
            "Prepare language discovery skipped: already completed",
            extra=result,
        )
        return result

    if current_status == "failed":
        result = {
            "document_id": document_id,
            "document_version_id": document_version_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "status": "failed",
            "handled": True,
            "executed": False,
            "idempotent_replay": True,
            "skipped_reason": "already_failed",
            "detected_languages": current_languages,
        }
        logger.info(
            "Prepare language discovery skipped: already failed",
            extra=result,
        )
        return result

    if current_status not in {"pending", "processing"}:
        raise PermanentError(
            "Document is in unexpected language_detection_status for prepare stage "
            f"(document_id={document_id}, status={current_status})"
        )

    try:
        route_result = await _ensure_pdf_prepared_for_language_discovery(
            db=db,
            version_repo=ver_repo,
            version=version,
            tenant_id=tenant_id,
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
        )

        next_task_name = route_result["next_task_name"]

        celery_app.send_task(
            next_task_name,
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
            "status": str(current_status or "pending"),
            "handled": True,
            "executed": True,
            "idempotent_replay": False,
            "next_task_name": next_task_name,
            "origin_filetype": route_result.get("origin_filetype"),
            "converted_pdf_ref": route_result.get("converted_pdf_ref"),
            "pipeline_strategy": route_result.get("pipeline_strategy"),
            "extraction_strategy": route_result.get("extraction_strategy"),
            "ocr_confidence": route_result.get("ocr_confidence"),
        }

        logger.info(
            "Document preparation for language discovery completed; next task enqueued",
            extra=result,
        )
        return result

    except TransientError:
        logger.warning(
            "Transient error during prepare language discovery; re-raising for retry",
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
            "Permanent failure during prepare language discovery",
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
        raise

    except Exception as e:
        logger.exception(
            "Unexpected error during prepare language discovery; re-raising for retry",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        raise


async def _ensure_pdf_prepared_for_language_discovery(
    *,
    db: AsyncSession,
    version_repo: DocumentVersionRepository,
    version: Any,
    tenant_id: str,
    document_id: str,
    document_version_id: str,
    deal_id: str,
) -> dict[str, Any]:
    origin_filetype = _normalize_route_value(getattr(version, "origin_filetype", None))
    converted_pdf_ref = getattr(version, "converted_pdf_ref", None)

    if origin_filetype == "pdf":
        return {
            "next_task_name": _select_downstream_task_name(version),
            "origin_filetype": origin_filetype,
            "converted_pdf_ref": converted_pdf_ref,
            "pipeline_strategy": getattr(version, "pipeline_strategy", None),
            "extraction_strategy": getattr(version, "extraction_strategy", None),
            "ocr_confidence": getattr(version, "ocr_confidence", None),
        }

    if origin_filetype in IMAGE_FILETYPES:
        return {
            "next_task_name": OCR_LANGUAGE_DISCOVERY_TASK_NAME,
            "origin_filetype": origin_filetype,
            "converted_pdf_ref": converted_pdf_ref,
            "pipeline_strategy": getattr(version, "pipeline_strategy", None),
            "extraction_strategy": getattr(version, "extraction_strategy", None),
            "ocr_confidence": getattr(version, "ocr_confidence", None),
        }

    if origin_filetype in OFFICE_FILETYPES and converted_pdf_ref:
        refreshed = await version_repo.get_by_id(uuid.UUID(document_version_id))
        actual_version = refreshed or version
        return {
            "next_task_name": _select_downstream_task_name(actual_version),
            "origin_filetype": getattr(actual_version, "origin_filetype", None),
            "converted_pdf_ref": getattr(actual_version, "converted_pdf_ref", None),
            "pipeline_strategy": getattr(actual_version, "pipeline_strategy", None),
            "extraction_strategy": getattr(actual_version, "extraction_strategy", None),
            "ocr_confidence": getattr(actual_version, "ocr_confidence", None),
        }

    if origin_filetype in OFFICE_FILETYPES and not converted_pdf_ref:
        return {
            "next_task_name": CONVERT_LANGUAGE_DISCOVERY_TASK_NAME,
            "origin_filetype": origin_filetype,
            "converted_pdf_ref": None,
            "pipeline_strategy": getattr(version, "pipeline_strategy", None),
            "extraction_strategy": getattr(version, "extraction_strategy", None),
            "ocr_confidence": getattr(version, "ocr_confidence", None),
        }

    if converted_pdf_ref:
        refreshed = await version_repo.get_by_id(uuid.UUID(document_version_id))
        actual_version = refreshed or version
        return {
            "next_task_name": _select_downstream_task_name(actual_version),
            "origin_filetype": getattr(actual_version, "origin_filetype", None),
            "converted_pdf_ref": getattr(actual_version, "converted_pdf_ref", None),
            "pipeline_strategy": getattr(actual_version, "pipeline_strategy", None),
            "extraction_strategy": getattr(actual_version, "extraction_strategy", None),
            "ocr_confidence": getattr(actual_version, "ocr_confidence", None),
        }

    raise PermanentError(
        "Unsupported source for prepare language discovery "
        f"(document_id={document_id}, document_version_id={document_version_id}, "
        f"origin_filetype={origin_filetype})"
    )



