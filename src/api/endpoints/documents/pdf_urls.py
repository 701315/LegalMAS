# api/endpoints/documents/pdf_urls.py

"""
Document PDF streaming endpoints.

Архитектурное решение:
- MinIO остаётся приватным (127.0.0.1) — это правильная топология.
- Браузер НИКОГДА не ходит в MinIO напрямую.
- PDF отдаётся через backend streaming: backend читает из MinIO,
  отдаёт браузеру как application/pdf.
- Presigned URL endpoints удалены — они нарушали security policy
  и несовместимы с приватным MinIO endpoint.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db
from storage.artifact_store import ArtifactStore
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


async def _stream_pdf_response(
    *,
    artifact_ref: str,
    doc_id: UUID,
    deal_id: UUID,
    user_id: UUID,
    url_type: str,
    filename: str,
) -> StreamingResponse:
    """
    Прочитать PDF из MinIO и отдать браузеру как streaming response.

    Архитектурные инварианты:
    - Backend читает из MinIO по внутренней сети (127.0.0.1).
    - Браузер получает чистый application/pdf от backend.
    - MinIO никогда не доступен браузеру напрямую.
    - Content-Disposition: inline — браузер рендерит сразу.
    """
    store = ArtifactStore()

    try:
        pdf_bytes = store.get_file(artifact_ref)
    except Exception as e:
        logger.exception(
            "Failed to read PDF from storage",
            extra={
                "doc_id": str(doc_id),
                "deal_id": str(deal_id),
                "user_id": str(user_id),
                "url_type": url_type,
                "artifact_ref": artifact_ref,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF temporarily unavailable",
        ) from e

    safe_filename = filename.replace('"', "")

    return StreamingResponse(
        content=iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Streaming endpoints (единственный browser-safe способ получить PDF)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{doc_id}/pdf-content",
    summary="Stream original PDF content for browser viewer",
    response_class=StreamingResponse,
)
async def get_document_pdf_content(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Отдать оригинальный PDF документа напрямую браузеру (streaming).

    Backend читает из приватного MinIO, браузер получает application/pdf.
    MinIO не доступен браузеру напрямую.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    version_repo = DocumentVersionRepository(db)
    version = await version_repo.get_latest(doc_id)
    if not version or not version.original_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original PDF not available",
        )

    filename = getattr(doc, "filename", None) or f"document_{doc_id}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = filename + ".pdf"

    logger.info(
        "PDF content stream",
        extra={
            "user_id": str(user.id),
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
            "url_type": "original",
        },
    )

    return await _stream_pdf_response(
        artifact_ref=version.original_ref,
        doc_id=doc_id,
        deal_id=doc.deal_id,
        user_id=user.id,
        url_type="original",
        filename=filename,
    )


@router.get(
    "/{doc_id}/converted-pdf-content",
    summary="Stream converted PDF content for browser viewer",
    response_class=StreamingResponse,
)
async def get_document_converted_pdf_content(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Отдать конвертированный PDF документа напрямую браузеру (streaming).

    Если converted PDF недоступен — fallback на original.
    Backend читает из приватного MinIO, браузер получает application/pdf.
    MinIO не доступен браузеру напрямую.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    version_repo = DocumentVersionRepository(db)
    version = await version_repo.get_latest(doc_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not available",
        )

    # Используем converted PDF если есть, иначе original
    artifact_ref = version.converted_pdf_ref or version.original_ref
    if not artifact_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF not available",
        )

    filename = getattr(doc, "filename", None) or f"document_{doc_id}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = filename + ".pdf"

    logger.info(
        "PDF content stream",
        extra={
            "user_id": str(user.id),
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
            "url_type": "converted",
            "using_ref": "converted" if version.converted_pdf_ref else "original_fallback",
        },
    )

    return await _stream_pdf_response(
        artifact_ref=artifact_ref,
        doc_id=doc_id,
        deal_id=doc.deal_id,
        user_id=user.id,
        url_type="converted",
        filename=filename,
    )


@router.get(
    "/{doc_id}/source-pdf-content",
    summary="Stream source PDF content for pipeline SOURCE stage viewer",
    response_class=StreamingResponse,
)
async def get_document_source_pdf_content(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Отдать source PDF (converted или original) для pipeline SOURCE stage viewer.

    Семантика идентична converted-pdf-content: converted_pdf_ref or original_ref.
    Выделен как отдельный endpoint для явности назначения в pipeline preview.
    Backend читает из приватного MinIO, браузер получает application/pdf.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    version_repo = DocumentVersionRepository(db)
    version = await version_repo.get_latest(doc_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not available",
        )

    artifact_ref = version.converted_pdf_ref or version.original_ref
    if not artifact_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source PDF not available",
        )

    filename = getattr(doc, "filename", None) or f"document_{doc_id}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = filename + ".pdf"

    logger.info(
        "Source PDF content stream",
        extra={
            "user_id": str(user.id),
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
            "url_type": "source",
        },
    )

    return await _stream_pdf_response(
        artifact_ref=artifact_ref,
        doc_id=doc_id,
        deal_id=doc.deal_id,
        user_id=user.id,
        url_type="source",
        filename=filename,
    )


@router.get(
    "/{doc_id}/primary-pdf-content",
    summary="Stream primary source PDF for pipeline PRIMARY stage viewer",
    response_class=StreamingResponse,
)
async def get_document_primary_pdf_content(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Отдать primary source PDF для pipeline PRIMARY stage viewer.

    primary_source_ref — одноязычный PDF после выбора основного языка сделки.
    Backend читает из приватного MinIO, браузер получает application/pdf.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    version_repo = DocumentVersionRepository(db)
    version = await version_repo.get_latest(doc_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not available",
        )

    if not version.primary_source_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Primary source PDF not available",
        )

    filename = getattr(doc, "filename", None) or f"document_{doc_id}_primary.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = filename + ".pdf"

    logger.info(
        "Primary PDF content stream",
        extra={
            "user_id": str(user.id),
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
            "url_type": "primary",
        },
    )

    return await _stream_pdf_response(
        artifact_ref=version.primary_source_ref,
        doc_id=doc_id,
        deal_id=doc.deal_id,
        user_id=user.id,
        url_type="primary",
        filename=filename,
    )


@router.get(
    "/{doc_id}/original-file",
    summary="Download original file (any format) via backend streaming",
    response_class=StreamingResponse,
)
async def get_document_original_file(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Скачать оригинальный файл документа через backend streaming.

    В отличие от /pdf-content, этот endpoint отдаёт файл в его реальном формате
    (DOCX, PDF, XLSX и т.д.) с правильным Content-Type и Content-Disposition: attachment.
    Backend читает из приватного MinIO, браузер получает файл напрямую.
    MinIO не доступен браузеру напрямую.
    """
    import mimetypes
    from pathlib import PurePosixPath
    from core.exceptions import PermanentError, TransientError

    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    version_repo = DocumentVersionRepository(db)
    version = await version_repo.get_latest(doc_id)
    if not version or not version.original_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original file not available",
        )

    store = ArtifactStore()

    try:
        metadata = store.get_file_metadata(version.original_ref)
        storage_response = store.open_file_stream(version.original_ref)
    except PermanentError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original file not found in storage",
        ) from e
    except TransientError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage temporarily unavailable",
        ) from e

    filename = getattr(doc, "filename", None) or f"document_{doc_id}"
    safe_filename = filename.replace('"', "")

    storage_ct = metadata.get("content_type") or ""
    if storage_ct and storage_ct != "application/octet-stream":
        content_type = storage_ct
    else:
        ext = PurePosixPath(filename).suffix.lower()
        _KNOWN = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }
        content_type = _KNOWN.get(ext) or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }

    size = metadata.get("size")
    if isinstance(size, int) and size >= 0:
        headers["Content-Length"] = str(size)

    logger.info(
        "Original file download stream",
        extra={
            "user_id": str(user.id),
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
            "document_filename": filename,
            "content_type": content_type,
        },
    )

    CHUNK = 1024 * 1024

    def _iter(resp):
        try:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                resp.close()
            finally:
                resp.release_conn()

    return StreamingResponse(
        _iter(storage_response),
        media_type=content_type,
        headers=headers,
    )
