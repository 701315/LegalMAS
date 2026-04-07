# src/api/endpoints/documents/reclassify.py

"""
Document reclassification endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from classifiers.yaml_registry import YAMLRegistry
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.session import get_db
from api.schemas.documents import ReclassifyRequest, ReclassifyResponse

router = APIRouter()


@router.post(
    "/{doc_id}/reclassify",
    response_model=ReclassifyResponse,
    summary="Ручная переклассификация документа",
)
async def reclassify_document(
    doc_id: uuid.UUID,
    data: ReclassifyRequest,
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

    previous_doc_type = doc.doc_type

    registry = YAMLRegistry.get_instance()
    cfg = registry.get_config(data.doc_type)

    if cfg is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown document type: '{data.doc_type}'. "
                "Проверьте, что тип существует в YAML-реестре."
            ),
        )

    yaml_found = True

    trigger_ids = getattr(cfg, "trigger_ids", None)
    if trigger_ids is not None:
        new_triggers: list[str] = list(trigger_ids)
    else:
        new_triggers = list(getattr(cfg, "trigger_definitions", {}).keys())

    await doc_repo.update_classification(
        doc_id=doc_id,
        doc_type=data.doc_type,
        classification_confidence=1.0,
        classification_level="L_manual",
        classification_details=doc.classification_details or {},
        applicable_triggers=new_triggers,
    )

    checks_requeued = False
    rerun_checks_requested = bool(getattr(data, "rerun_checks", False))

    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=user.tenant_id,
        action="RECLASSIFY",
        actor=str(getattr(user, "id", "unknown")),
        deal_id=doc.deal_id,
        actor_role=getattr(user, "global_role", None),
        details={
            "document_id": str(doc_id),
            "previous_doc_type": previous_doc_type,
            "new_doc_type": data.doc_type,
            "reason": data.reason,
            "yaml_instruction_found": yaml_found,
            "new_applicable_triggers": new_triggers,
            "checks_requeued": checks_requeued,
            "rerun_checks_flag_requested": rerun_checks_requested,
            "rerun_checks_behavior": "deprecated_no_action",
        },
    )

    deal_repo = DealRepository(db)
    await deal_repo.set_has_pending_manual_reclassifications(
        deal_id=doc.deal_id,
        value=True,
    )

    return ReclassifyResponse(
        document_id=doc_id,
        previous_doc_type=previous_doc_type,
        new_doc_type=data.doc_type,
        new_applicable_triggers=new_triggers,
        yaml_instruction_found=yaml_found,
        checks_requeued=checks_requeued,
    )

