# src/api/endpoints/documents/pii_reveal.py

"""
PII Reveal endpoint.

Позволяет привилегированным пользователям восстановить оригинальные
PII-данные из sanitized layout документа.

Требования доступа:
- Минимум роль 'editor' в проекте.
- superadmin и tenant_admin — по стандартным RBAC правилам.
- Каждый вызов логируется в audit log.

Архитектурное решение:
- Reveal не возвращает полный layout с PII по умолчанию в публичных read-API.
- Reveal — отдельный явный endpoint с обязательным аудитом.
- Мы не возвращаем сырой mapping — только восстановленный layout.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.rate_limit import check_pii_reveal_rate_limit
from api.deps.security import require_project_role
from core.logging import get_logger
from db.repositories.audit_repo import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db
from services.pii_reveal_service import PIIRevealError, reveal_document_pii
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

router = APIRouter()


class PIIRevealResponse(BaseModel):
    """Ответ с восстановленным layout документа."""
    document_id: str
    document_version_id: str
    elements_count: int
    layout: dict


@router.get(
    "/{doc_id}/pii-reveal",
    response_model=PIIRevealResponse,
    summary="Восстановить оригинальный текст документа (раскрыть PII)",
    description=(
        "Возвращает layout документа с восстановленными PII-данными. "
        "Требует роль editor или выше. Каждый вызов логируется в audit log."
    ),
)
async def reveal_document_pii_endpoint(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    _rate_limit: None = Depends(check_pii_reveal_rate_limit),
) -> PIIRevealResponse:
    """
    Восстановить оригинальный текст документа из sanitized layout.

    Только для editor/admin/tenant_admin/superadmin.
    Каждый вызов записывается в audit log.
    """
    # 1. Загрузить документ
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # 2. ACL — минимум editor (viewer не должен видеть PII)
    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("editor", "admin"),
    )

    # 3. Получить версию
    ver_repo = DocumentVersionRepository(db)
    version = await ver_repo.get_latest(doc_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not found",
        )

    # 4. Проверить наличие обоих артефактов
    sanitized_ref = getattr(version, "layout_primary_sanitized_ref", None)
    mapping_ref = getattr(version, "pii_mapping_ref", None)

    if not sanitized_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sanitized layout not available for this document",
        )

    if not mapping_ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "PII mapping not available for this document. "
                "Document may have been processed before PII reveal support was added."
            ),
        )

    # 5. Audit log — до выполнения reveal.
    # Для PII reveal pre-audit обязателен: если аудит недоступен,
    # чувствительная операция не должна выполняться.
    audit_repo = AuditRepository(db)
    try:
        await audit_repo.log(
            tenant_id=user.tenant_id,
            deal_id=doc.deal_id,
            action="PII_REVEAL_REQUESTED",
            actor=str(user.id),
            actor_role=user.global_role,
            details={
                "document_id": str(doc_id),
                "document_version_id": str(version.id),
                "sanitized_layout_ref": sanitized_ref,
                "pii_mapping_ref": mapping_ref,
                "requester_email": getattr(user, "email", None),
            },
        )
    except Exception as e:
        logger.error(
            "PII reveal: failed to write mandatory pre-audit log",
            document_id=str(doc_id),
            document_version_id=str(version.id),
            actor=str(user.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PII reveal audit unavailable",
        ) from e

    # 6. Выполнить reveal
    store = ArtifactStore()
    try:
        restored_layout = await reveal_document_pii(
            store=store,
            sanitized_layout_ref=sanitized_ref,
            pii_mapping_ref=mapping_ref,
            document_id=doc_id,
        )
    except PIIRevealError as e:
        logger.error(
            "PII reveal failed",
            document_id=str(doc_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PII reveal failed: {e}",
        )

    elements = restored_layout.get("elements", [])

    # 7. Audit log — после успешного reveal
    try:
        await audit_repo.log(
            tenant_id=user.tenant_id,
            deal_id=doc.deal_id,
            action="PII_REVEAL_COMPLETED",
            actor=str(user.id),
            actor_role=user.global_role,
            details={
                "document_id": str(doc_id),
                "document_version_id": str(version.id),
                "elements_count": len(elements),
            },
        )
    except Exception:
        logger.warning(
            "PII reveal: failed to write audit log after reveal",
            document_id=str(doc_id),
        )

    logger.info(
        "PII reveal completed",
        document_id=str(doc_id),
        document_version_id=str(version.id),
        elements_count=len(elements),
        actor=str(user.id),
    )

    return PIIRevealResponse(
        document_id=str(doc_id),
        document_version_id=str(version.id),
        elements_count=len(elements),
        layout=restored_layout,
    )


