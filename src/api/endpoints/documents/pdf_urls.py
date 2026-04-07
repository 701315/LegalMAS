# api/endpoints/documents/pdf_urls.py

"""
Document PDF URL endpoints.

Содержит эндпоинты для получения ссылок на исходный и конвертированный PDF.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
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
    Построить presigned URL для PDF-артефакта и единообразно обработать ошибки storage.
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


@router.get(
    "/{doc_id}/pdf-url",
    response_model=str,
    response_class=PlainTextResponse,
    summary="Get original PDF URL for document",
)
async def get_document_pdf_url(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть presigned URL для исходного файла документа.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    logger.info(
        "PDF URL access attempt",
        extra={
            "user_id": str(user.id),
            "global_role": getattr(user, "global_role", None),
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
            "url_type": "original",
        },
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
    summary="Get converted PDF URL for document",
)
async def get_document_converted_pdf_url(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть presigned URL для конвертированного PDF документа.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    logger.info(
        "PDF URL access attempt",
        extra={
            "user_id": str(user.id),
            "global_role": getattr(user, "global_role", None),
            "doc_id": str(doc_id),
            "deal_id": str(doc.deal_id),
            "url_type": "converted",
        },
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