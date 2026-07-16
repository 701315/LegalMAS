# src/api/endpoints/results.py

"""
Эндпоинты для результатов проверок (check_results).

- GET /results — список результатов с фильтрами:
    - conditional_only: только условные проверки
    - has_structured_data: только результаты со structured_data

- GET /results/{result_id}/evidence — подробная информация о доказательствах
  (место в документе, сниппет текста, служебные поля).
"""

import uuid
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_run # Наша защищенная зависимость
from db.models.result import CheckResult
from db.models.document import Document
from db.models.deal import Deal
from db.repositories.result_repo import ResultRepository
from db.session import get_db
from ..schemas.results import CheckResultResponse

router = APIRouter(prefix="/results", tags=["results"])

# Респонс схема остается без изменений...
class EvidenceResponse(BaseModel):
    result_id: uuid.UUID
    document_id: uuid.UUID
    run_id: uuid.UUID
    severity: str
    result: str
    value_text: str | None = None
    evidence_ref: str | None = None
    page: int | None = None
    clause_uid: str | None = None
    element_id: str | None = None
    bbox: dict | None = None
    confidence: float | None = None
    detector_used: str | None = None
    origin: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    segment_id: str | None = None
    segment_type: str | None = None
    context_trace: list[dict] | None = None
    display_text: str | None = None
    review_status: str | None = None
    review_message: str | None = None
    doc_type: str | None = None
    yaml_instruction_ref: str | None = None

@router.get("", response_model=list[CheckResultResponse])
async def list_results(
    run_id: uuid.UUID = Query(...), # Сделали обязательным
    conditional_only: bool | None = Query(default=None),
    has_structured_data: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # ПРОВЕРКА ДОСТУПА
    await get_scoped_run(run_id=run_id, user=user, db=db)

    repo = ResultRepository(db)
    raw_results = await repo.get_by_run_with_docs(run_id)
    out = [CheckResultResponse.model_validate(r) for r in raw_results]

    if conditional_only:
        out = [r for r in out if r.conditional_check_triggered]
    if has_structured_data:
        out = [r for r in out if r.structured_data]
    return out

@router.get("/{result_id}/evidence", response_model=EvidenceResponse)
async def get_evidence(
    result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # ЖЕСТКАЯ ПРОВЕРКА ТЕНАНТА ЧЕРЕЗ JOIN
    stmt = (
        select(CheckResult)
        .join(Document, CheckResult.document_id == Document.id)
        .join(Deal, Document.deal_id == Deal.id)
        .where(CheckResult.id == result_id, Deal.tenant_id == user.tenant_id)
    )
    db_result = await db.execute(stmt)
    check_result = db_result.scalar_one_or_none()

    if check_result is None:
        raise HTTPException(status_code=404, detail="Evidence not found")

    return EvidenceResponse(
        result_id=check_result.id,
        document_id=check_result.document_id,
        run_id=check_result.run_id,
        severity=check_result.severity,
        result=check_result.result,
        value_text=check_result.value_text,
        evidence_ref=check_result.evidence_ref,
        page=check_result.page,
        clause_uid=check_result.clause_uid,
        element_id=check_result.element_id,
        bbox=check_result.bbox,
        confidence=check_result.confidence,
        detector_used=check_result.detector_used,
        origin=check_result.origin,
        chunk_id=check_result.chunk_id,
        chunk_index=check_result.chunk_index,
        segment_id=check_result.segment_id,
        segment_type=check_result.segment_type,
        context_trace=check_result.context_trace,
        display_text=check_result.display_text,
        review_status=check_result.review_status,
        review_message=check_result.review_message,
        doc_type=None,
        yaml_instruction_ref=None,
    )

@router.get(
    "/debug/{result_id}",
    summary="DEBUG: только для superadmin",
)
async def debug_check_result(
    result_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if user.global_role != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin only")

    stmt = select(CheckResult).where(CheckResult.id == result_id)
    db_result = await db.execute(stmt)
    obj = db_result.scalar_one_or_none()

    if obj is None:
        return {"ok": False, "reason": "not_found"}

    return {
        "ok": True,
        "result_id": str(obj.id),
        "run_id": str(obj.run_id),
        "document_id": str(obj.document_id),
    }


