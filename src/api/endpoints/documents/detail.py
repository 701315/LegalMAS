# src/api/endpoints/documents/detail.py

"""
Document detail endpoints.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.documents import DocumentDetailResponse
from db.repositories.document_repo import DocumentRepository
from db.session import get_db

from .common import load_document_detail

router = APIRouter()


@router.get(
    "/{doc_id}",
    response_model=DocumentDetailResponse,
    summary="Получить детальную информацию о документе",
)
async def get_document_detail(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
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

    return await load_document_detail(db=db, doc_id=doc_id)
