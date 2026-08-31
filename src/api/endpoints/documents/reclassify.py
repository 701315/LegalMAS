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
from api.schemas.documents import ReclassifyRequest, ReclassifyResponse
from classifiers.yaml_registry import YAMLRegistry
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.session import get_db

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
    try:
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

        # Проверяем новый doc_type через YAMLRegistry.
        # Для непрофессионального программиста:
        # - registry хранит все загруженные YAML-конфиги типов документов;
        # - если get_config(...) вернул объект, значит инструкция существует;
        # - если вернул None, значит такого типа сейчас нет в реестре.
        registry = YAMLRegistry.get_instance(validate=False)
        cfg = registry.get_config(data.doc_type)
        yaml_found = cfg is not None

        if not yaml_found:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unknown document type: '{data.doc_type}'. "
                    "Проверьте, что тип существует в YAML-реестре."
                ),
            )

        trigger_ids = getattr(cfg, "trigger_ids", None)
        if trigger_ids is not None:
            new_triggers: list[str] = list(trigger_ids)
        else:
            new_triggers = list(getattr(cfg, "trigger_definitions", {}).keys())

        classification_details = dict(doc.classification_details or {})
        classification_details.pop("requires_manual_review", None)
        classification_details.pop("requires_manual_review_by_confidence", None)

        await doc_repo.update_classification(
            doc_id=doc_id,
            doc_type=data.doc_type,
            classification_confidence=1.0,
            classification_level="L_manual",
            classification_details=classification_details,
            applicable_triggers=new_triggers,
            classification_requires_review=False,
        )

        # ── Гарантируем корректный статус документа для Orchestrator ─────────
        if doc.status in {
            DocumentStatus.CHUNKED.value,
            DocumentStatus.STRUCTURED.value,
            DocumentStatus.CLASSIFIED.value,
        }:
            doc.status = DocumentStatus.CLASSIFIED.value
        # ── КОНЕЦ принудительного статуса ─────────────────────────────────────

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

        # ── FIX #5 & #6.A: Атомарный commit перед retrigger ─────────────────
        try:
            from sqlalchemy import select
            from db.models.run import Run
            from db.repositories.run_repo import RunRepository
            from core.constants import RunStatus
            from services.run_orchestrator_trigger import retrigger_run_pipeline

            run_repo = RunRepository(db)
            stmt = (
                select(Run)
                .where(Run.deal_id == doc.deal_id)
                .order_by(Run.created_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            latest_run = result.scalar_one_or_none()

            run_id_to_trigger = None
            if latest_run:
                run_id_to_trigger = str(latest_run.id)
                if latest_run.status in {
                    RunStatus.COMPLETED.value,
                    RunStatus.COMPLETED_WITH_ERRORS.value,
                }:
                    await run_repo.update_status(
                        latest_run.id,
                        RunStatus.RUNNING.value,
                    )

            # 1. СНАЧАЛА ФИКСИРУЕМ В БД (до вызова Celery)
            await db.commit()

            # 2. ТОЛЬКО ПОСЛЕ УСПЕШНОГО COMMIT — ОТПРАВЛЯЕМ В БРОКЕР
            if run_id_to_trigger:
                retrigger_run_pipeline(
                    run_id=run_id_to_trigger,
                    deal_id=str(doc.deal_id),
                    tenant_id=str(user.tenant_id),
                )
                logger.info(
                    "Retriggered run pipeline after manual reclassification",
                    run_id=run_id_to_trigger,
                    document_id=str(doc_id),
                )
        except Exception as e:
            logger.warning(
                "Failed to retrigger run after reclassify (non-fatal)",
                document_id=str(doc_id),
                error=str(e),
            )
        # ── КОНЕЦ FIX #5 & #6.A ───────────────────────────────────────────────

        return ReclassifyResponse(
            document_id=doc_id,
            previous_doc_type=previous_doc_type,
            new_doc_type=data.doc_type,
            new_applicable_triggers=new_triggers,
            yaml_instruction_found=yaml_found,
            checks_requeued=checks_requeued,
        )

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise
