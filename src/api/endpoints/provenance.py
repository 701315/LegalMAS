# src/api/endpoints/provenance.py

"""
Decision Provenance API — Этап 4.

Endpoints:
- GET /documents/{doc_id}/processing-trace    — stage execution traces
- GET /documents/{doc_id}/classification-decision — classification explainability
- GET /checks/{check_result_id}/provenance    — check result provenance
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.provenance import (
    CheckProvenanceDTO,
    ClassificationCandidateDTO,
    ClassificationDecisionDTO,
    ContextTraceItemDTO,
    ProcessingTraceResponseDTO,
    StageTraceDTO,
)
from core.logging import get_logger
from db.models.document import Document, DocumentStageExecution
from db.models.result import CheckResult
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db

logger = get_logger(__name__)

router = APIRouter(tags=["provenance"])


# ─── Processing Trace ─────────────────────────────────────────────────────────


@router.get(
    "/documents/{doc_id}/processing-trace",
    response_model=ProcessingTraceResponseDTO,
    summary="Get full pipeline processing trace for document",
)
async def get_processing_trace(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть полную трассу pipeline обработки документа.

    Читает все строки из document_stage_executions для документа.
    Каждая строка содержит result_details с canonical Stage Trace Schema v1.

    Полезно для:
    - понять что произошло с документом на каждой стадии
    - увидеть duration каждого stage
    - найти warnings и fallbacks
    - посмотреть artifact refs каждой стадии
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

    ver_repo = DocumentVersionRepository(db)
    version = await ver_repo.get_latest(doc_id)

    # Читаем все stage executions для этого документа
    stmt = (
        select(DocumentStageExecution)
        .where(DocumentStageExecution.document_id == doc_id)
        .order_by(DocumentStageExecution.created_at.asc())
    )
    result = await db.execute(stmt)
    executions = list(result.scalars().all())

    stages = []
    for exe in executions:
        rd = exe.result_details or {}
        ed = exe.error_details or {}

        stages.append(StageTraceDTO(
            task_name=exe.task_name or "",
            status=exe.status or "",
            schema_version=rd.get("schema_version"),
            stage=rd.get("stage"),
            trace_status=rd.get("status"),
            strategy=rd.get("strategy"),
            started_at=(
                exe.started_at.isoformat()
                if exe.started_at else None
            ),
            finished_at=rd.get("finished_at"),
            duration_ms=(
                int(rd["duration_ms"])
                if rd.get("duration_ms") is not None else None
            ),
            input_summary=rd.get("input_summary"),
            output_summary=rd.get("output_summary"),
            warnings=rd.get("warnings"),
            artifact_refs=rd.get("artifact_refs"),
            decision_details=rd.get("decision_details"),
            error_details=ed if ed else None,
        ))

    return ProcessingTraceResponseDTO(
        document_id=str(doc_id),
        document_version_id=str(version.id) if version else None,
        document_status=doc.status,
        stages=stages,
    )


# ─── Classification Decision ──────────────────────────────────────────────────


@router.get(
    "/documents/{doc_id}/classification-decision",
    response_model=ClassificationDecisionDTO,
    summary="Get classification decision explainability for document",
)
async def get_classification_decision(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть explainability для решения о типе документа.

    Читает данные из Document.classification_details и Document.doc_type.

    Полезно для:
    - понять почему документ классифицирован именно так
    - увидеть альтернативные кандидаты
    - понять какой уровень каскада принял решение
    - увидеть зону уверенности (confident / low / unknown)
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

    details = doc.classification_details or {}

    # Извлечь decided_by из details (несколько possible paths)
    decided_by = None
    decision_summary = details.get("decision_summary") or {}
    if isinstance(decision_summary, dict):
        decided_by = decision_summary.get("decided_by")
    if not decided_by:
        voting = details.get("voting") or {}
        if isinstance(voting, dict):
            decided_by = voting.get("strategy")
    if not decided_by and details.get("L4"):
        decided_by = "L4_LLM"
    if not decided_by and details.get("MASTERCOPY"):
        decided_by = "COPIED"

    # Candidates
    raw_candidates = details.get("candidates") or []
    candidates = []
    for c in raw_candidates[:10]:  # limit top-10
        if isinstance(c, dict):
            candidates.append(ClassificationCandidateDTO(
                type_code=c.get("type_code") or c.get("doctype"),
                doctype=c.get("type_code") or c.get("doctype"),
                confidence=c.get("confidence"),
                level=c.get("level"),
                method=c.get("method"),
                evidence=c.get("evidence"),
            ))

    playbook_id = getattr(doc, "playbook_version_id", None)

    return ClassificationDecisionDTO(
        document_id=str(doc_id),
        doc_type=doc.doc_type,
        classification_outcome=str(doc.classification_outcome or ""),
        confidence=doc.classification_confidence,
        classification_level=doc.classification_level,
        language=doc.language,
        jurisdiction=doc.jurisdiction_guess,
        requires_manual_review=bool(doc.classification_requires_review),
        applicable_triggers=list(doc.applicable_triggers or []),
        playbook_version_id=str(playbook_id) if playbook_id else None,
        decided_by=decided_by,
        levels_tried=details.get("levels_tried") or [],
        confidence_zone=details.get("confidence_zone"),
        candidates=candidates,
        unknown_corridor_applied=details.get("unknown_corridor_applied"),
        voting_score=details.get("voting_score"),
        l4_triggered=details.get("l4_triggered"),
    )


# ─── Check Provenance ─────────────────────────────────────────────────────────


@router.get(
    "/checks/{check_result_id}/provenance",
    response_model=CheckProvenanceDTO,
    summary="Get full provenance for a check result",
)
async def get_check_provenance(
    check_result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть полный provenance для одного check result.

    Включает:
    - retrieval context trace (какие chunks были использованы)
    - evidence anchor (page, clause_uid, element_id, bbox)
    - chunk provenance (chunk_id, chunk_index, segment_id)
    - user-facing semantics (display_text, review_status, review_message)
    - structured extraction данные
    - diagnostics (quality_flags, error_details)

    Полезно для:
    - понять почему check вернул именно этот результат
    - увидеть источники evidence
    - понять какие chunks были retrieval candidates
    """
    stmt = select(CheckResult).where(CheckResult.id == check_result_id)
    result = await db.execute(stmt)
    cr = result.scalar_one_or_none()

    if cr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check result not found",
        )

    # ACL: проверяем доступ через document
    stmt_doc = select(Document).where(Document.id == cr.document_id)
    doc_result = await db.execute(stmt_doc)
    doc = doc_result.scalar_one_or_none()

    if doc:
        await require_project_role(
            db=db,
            user=user,
            deal_id=doc.deal_id,
            allowed_roles=("viewer", "editor", "admin"),
        )

    # Нормализуем context_trace
    raw_trace = cr.context_trace or []
    context_trace_items = []
    for item in raw_trace:
        if isinstance(item, dict):
            context_trace_items.append(ContextTraceItemDTO(
                rank=item.get("rank"),
                score=item.get("score"),
                score_breakdown=item.get("score_breakdown"),
                chunk_id=item.get("chunk_id"),
                chunk_index=item.get("chunk_index"),
                clause_uid=item.get("clause_uid"),
                element_id=item.get("element_id"),
                page=item.get("page"),
                segment_id=item.get("segment_id"),
                segment_type=item.get("segment_type"),
                segment_title=item.get("segment_title"),
                segment_order=item.get("segment_order"),
                is_primary_segment=item.get("is_primary_segment"),
            ))

    return CheckProvenanceDTO(
        result_id=str(cr.id),
        check_id=cr.check_id,
        check_name=cr.check_name,
        document_id=str(cr.document_id),
        run_id=str(cr.run_id),
        result=cr.result,
        severity=cr.severity,
        confidence=cr.confidence,
        detector_used=cr.detector_used,
        execution_status=cr.execution_status,
        display_text=cr.display_text,
        review_status=cr.review_status,
        review_message=cr.review_message,
        needs_manual_review=bool(cr.needs_manual_review),
        ui_mode=cr.ui_mode,
        evidence_ref=cr.evidence_ref,
        page=cr.page,
        clause_uid=cr.clause_uid,
        element_id=cr.element_id,
        bbox=cr.bbox,
        chunk_id=cr.chunk_id,
        chunk_index=cr.chunk_index,
        context_trace=context_trace_items,
        segment_id=cr.segment_id,
        segment_type=cr.segment_type,
        segment_title=cr.segment_title,
        segment_order=cr.segment_order,
        is_primary_segment=cr.is_primary_segment,
        structured_data=cr.structured_data,
        quality_flags=cr.quality_flags,
        error_details=cr.error_details,
    )


    