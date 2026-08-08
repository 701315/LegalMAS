# api/endpoints/documents/pdf_urls.py

"""
Document PDF URL endpoints.

Содержит эндпоинты для получения ссылок и содержимого PDF.

Архитектурное решение:
- MinIO остаётся приватным (127.0.0.1:19000) — это правильная топология.
- Браузер НИКОГДА не ходит в MinIO напрямую.
- PDF отдаётся через backend streaming: backend читает из MinIO,
  отдаёт браузеру как application/pdf.
- Presigned URL endpoints оставлены для внутреннего использования
  (worker-to-worker, server-side) но не используются во frontend viewer.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from minio.error import S3Error
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db
from storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_presigned_pdf_url(
    *,
    artifact_ref: str,
    doc_id: UUID,
    deal_id: UUID,
    user_id: UUID,
    url_type: str,
) -> str:
    """
    Построить presigned URL для PDF-артефакта.
    Используется только для внутренних/server-side нужд.
    Для browser viewer используйте streaming endpoints.
    """
    store = ArtifactStore()

    try:
        return store.get_presigned_get_url(artifact_ref)
    except S3Error as e:
        logger.exception(
            "Failed to generate presigned PDF URL",
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
            detail="Storage temporarily unavailable",
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error while generating presigned PDF URL",
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
            detail="PDF URL temporarily unavailable",
        ) from e


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
    - Backend читает из MinIO по внутренней сети (127.0.0.1:19000).
    - Браузер получает чистый application/pdf от backend.
    - MinIO никогда не доступен браузеру напрямую.
    - Content-Disposition: inline — браузер/react-pdf рендерит сразу.
    """
    store = ArtifactStore()

    try:
        pdf_bytes = store.get_file(artifact_ref)
    except S3Error as e:
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
            detail="Storage temporarily unavailable",
        ) from e
    except Exception as e:
        logger.exception(
            "Unexpected error while reading PDF",
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
# Streaming endpoints (для browser viewer)
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

    Используется browser viewer вместо presigned URL.
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

    Используется browser viewer вместо presigned URL.
    Если converted PDF недоступен — fallback на original.
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


# ──────────────────────────────────────────────────────────────────────────────
# Presigned URL endpoints (для внутреннего/server-side использования)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{doc_id}/pdf-url",
    response_model=str,
    response_class=PlainTextResponse,
    summary="Get original PDF presigned URL (internal use only)",
)
async def get_document_pdf_url(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть presigned URL для исходного файла документа.
    Только для server-side использования. Для browser viewer используйте /pdf-content.
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

    return _build_presigned_pdf_url(
        artifact_ref=version.original_ref,
        doc_id=doc_id,
        deal_id=doc.deal_id,
        user_id=user.id,
        url_type="original",
    )


@router.get(
    "/{doc_id}/converted-pdf-url",
    response_model=str,
    response_class=PlainTextResponse,
    summary="Get converted PDF presigned URL (internal use only)",
)
async def get_document_converted_pdf_url(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть presigned URL для конвертированного PDF документа.
    Только для server-side использования. Для browser viewer используйте /converted-pdf-content.
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
    if not version or not version.converted_pdf_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Converted PDF not available",
        )

    return _build_presigned_pdf_url(
        artifact_ref=version.converted_pdf_ref,
        doc_id=doc_id,
        deal_id=doc.deal_id,
        user_id=user.id,
        url_type="converted",
    )



