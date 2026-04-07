# src/api/endpoints/documents/moderation.py

"""
Document moderation endpoints.

Замена файла, мягкое удаление и флаг ручной проверки юристом.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.documents import DocumentResponse, DocumentReviewedUpdateRequest
from core.constants import DocumentStatus
from db.repositories.audit_repo import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.session import get_db
from services.document_service import DocumentNotFoundError, DocumentService
from storage.artifact_store import ArtifactPath, ArtifactStore

router = APIRouter()


@router.post(
    "/{doc_id}/replace",
    summary="Replace a quarantined document with a new file",
)
async def replace_document(
    doc_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != DocumentStatus.QUARANTINE.value:
        raise HTTPException(
            status_code=422,
            detail="Only quarantined documents can be replaced",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor"),
    )

    store = ArtifactStore()
    file_bytes = await file.read()
    file_ref = store.put_file(
        ArtifactPath.original(str(user.tenant_id), str(doc.deal_id), str(doc.id)),
        file_bytes,
    )

    await doc_repo.reset_for_reprocessing(
        doc.id,
        new_status=DocumentStatus.PENDING.value,
        clear_classification=True,
    )

    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=user.tenant_id,
        deal_id=doc.deal_id,
        action="DOCUMENT_REPLACE",
        actor=str(getattr(user, "id", "unknown")),
        actor_role=getattr(user, "global_role", None),
        details={
            "document_id": str(doc.id),
            "filename": file.filename,
            "previous_doc_type": doc.doc_type,
            "classification_reset": True,
            "artifact_ref": file_ref,
        },
    )

    return {
        "status": "ok",
        "document_id": str(doc.id),
        "new_status": DocumentStatus.PENDING.value,
        "classification_reset": True,
    }


@router.post(
    "/{doc_id}/delete",
    summary="Soft-delete документа (пометить как deleted)",
)
async def soft_delete_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor"),
    )

    if doc.status == DocumentStatus.DELETED.value:
        return {
            "status": "ok",
            "document_id": str(doc.id),
            "new_status": doc.status,
            "already_deleted": True,
        }

    await doc_repo.update_status(
        doc_id=doc.id,
        status=DocumentStatus.DELETED.value,
    )

    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=user.tenant_id,
        deal_id=doc.deal_id,
        action="DOCUMENT_SOFT_DELETE",
        actor=str(getattr(user, "id", "unknown")),
        actor_role=getattr(user, "global_role", None),
        details={
            "document_id": str(doc.id),
            "previous_status": doc.status,
            "new_status": DocumentStatus.DELETED.value,
        },
    )

    await db.commit()

    return {
        "status": "ok",
        "document_id": str(doc.id),
        "new_status": DocumentStatus.DELETED.value,
        "already_deleted": False,
    }


@router.patch(
    "/{doc_id}/reviewed",
    response_model=DocumentResponse,
    summary="Обновить флаг проверки документа юристом",
)
async def update_document_reviewed_flag(
    doc_id: uuid.UUID,
    body: DocumentReviewedUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    service = DocumentService(db)

    try:
        updated_document = await service.set_reviewed_flag(
            doc_id=doc_id,
            reviewed_by_person=body.reviewed_by_person,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")

    return updated_document