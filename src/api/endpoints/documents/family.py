# src/api/endpoints/documents/family.py

"""
Document family endpoints.

Семья документа: master + связанные документы.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.mappers.documents import map_document_to_response
from api.schemas.documents import FamilyResponse
from db.models.document import Document
from db.models.relation import DocumentFamily, DocumentFamilyMember
from db.repositories.document_repo import DocumentRepository
from db.session import get_db

router = APIRouter()


async def _get_family_for_document(
    db: AsyncSession,
    doc_id: UUID,
) -> DocumentFamily | None:
    """
    Найти семью документа независимо от того,
    является ли он master или member.
    """
    stmt_master = (
        select(DocumentFamily)
        .where(DocumentFamily.master_doc_id == doc_id)
        .options(selectinload(DocumentFamily.members))
    )
    result_master = await db.execute(stmt_master)
    family = result_master.scalars().first()
    if family:
        return family

    stmt_member = (
        select(DocumentFamilyMember.family_id)
        .where(DocumentFamilyMember.doc_id == doc_id)
        .limit(1)
    )
    result_member = await db.execute(stmt_member)
    family_id = result_member.scalar_one_or_none()
    if not family_id:
        return None

    stmt_family = (
        select(DocumentFamily)
        .where(DocumentFamily.id == family_id)
        .options(selectinload(DocumentFamily.members))
    )
    result_family = await db.execute(stmt_family)
    return result_family.scalars().first()


@router.get(
    "/{doc_id}/family",
    response_model=FamilyResponse,
    summary="Get document family (master + members)",
)
async def get_document_family(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть семью документа:
    - master_document — основной документ;
    - related_documents — все остальные документы семьи;
    - relations — пока пустой список.
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

    family = await _get_family_for_document(db=db, doc_id=doc_id)
    if not family:
        return FamilyResponse(
            family_id=doc.id,
            master_document=map_document_to_response(doc),
            related_documents=[],
            relations=[],
        )

    master_doc = await doc_repo.get_by_id(family.master_doc_id)
    if not master_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Family master document not found",
        )

    member_doc_ids = [member.doc_id for member in family.members]
    related_doc_ids = [
        member_id for member_id in member_doc_ids
        if member_id != family.master_doc_id
    ]

    related_docs: list[Document] = []
    if related_doc_ids:
        stmt_members = select(Document).where(Document.id.in_(related_doc_ids))
        members_result = await db.execute(stmt_members)
        related_docs = list(members_result.scalars().all())

    return FamilyResponse(
        family_id=family.id,
        master_document=map_document_to_response(master_doc),
        related_documents=[map_document_to_response(d) for d in related_docs],
        relations=[],
    )

