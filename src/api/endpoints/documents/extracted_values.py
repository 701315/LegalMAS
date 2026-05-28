# src/api/endpoints/documents/extracted_values.py

"""
Document extracted values endpoints.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.documents import DocumentExtractedValuesResponse, ExtractedValue
from db.repositories.document_repo import DocumentRepository
from db.repositories.run_repo import RunRepository
from db.repositories.runner_repo import RunnerRepository
from db.session import get_db
from services.export.aggregator import aggregate_results
from services.export.models import StructuredValueRow

router = APIRouter()


@router.get(
    "/{doc_id}/extracted-values",
    response_model=DocumentExtractedValuesResponse,
    summary="Получить извлечённые структурированные значения для документа",
)
async def get_document_extracted_values(
    doc_id: UUID,
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
        allowed_roles=("viewer", "editor", "admin"),
    )

    run_repo = RunRepository(db)
    run = await run_repo.get_latest_for_deal(doc.deal_id)

    if not run:
        rows: list[StructuredValueRow] = []
    else:
        runner_repo = RunnerRepository(db)
        documents_dict = await runner_repo.load_documents_for_run(run.id)
        check_results = await runner_repo.load_check_results_for_run(run.id)

        deal_name = ""

        agg = aggregate_results(
            deal_id=str(doc.deal_id),
            deal_name=deal_name,
            run_id=str(run.id),
            check_results=check_results,
            documents=documents_dict,
        )

        rows = [r for r in agg.structured_value_rows if r.document_id == str(doc_id)]

    if not rows:
        return DocumentExtractedValuesResponse(
            document_id=str(doc_id),
            filename=doc.filename,
            doc_type=doc.doc_type,
            extracted_values=[],
            total_extracted=0,
        )

    extracted_values = [
        ExtractedValue(
            check_id=r.check_id,
            check_name=r.check_name,
            field_name=r.field_name,
            field_value=r.field_value,
            field_format=r.field_format,
            page=r.page,
            clause_uid=r.clause_uid or "",
        )
        for r in rows
    ]

    return DocumentExtractedValuesResponse(
        document_id=str(doc_id),
        filename=doc.filename,
        doc_type=doc.doc_type,
        extracted_values=extracted_values,
        total_extracted=len(extracted_values),
    )
