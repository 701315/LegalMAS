# src/api/endpoints/documents/extracted_values.py

"""
Document extracted values endpoints.

Прямое чтение из check_results — без aggregator.
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

router = APIRouter()


def _extract_structured_values_from_check_results(
    check_results: list[dict],
    document_id: str,
) -> list[ExtractedValue]:
    """
    Извлечь structured values напрямую из check_results для одного документа.
    
    Аналог aggregate_results().structured_value_rows — но без агрегатора.
    """
    extracted_values: list[ExtractedValue] = []
    
    for cr in check_results:
        if cr.get("document_id") != document_id:
            continue
        
        structured_data = cr.get("structured_data") or {}
        if not structured_data:
            continue
        
        for field_name, field_value in structured_data.items():
            # Нормализация значения
            if isinstance(field_value, dict) and "value" in field_value:
                raw_display_value = field_value.get("value")
            else:
                raw_display_value = field_value
            
            if raw_display_value is None or str(raw_display_value) in ("not_found", "not_defined", "None", ""):
                continue
            
            display_value = str(raw_display_value)
            
            # Infer format
            name_lower = field_name.lower()
            if any(x in name_lower for x in ("amount", "price", "sum", "cost")):
                field_format = "money"
            elif any(x in name_lower for x in ("date", "expiry", "term")):
                field_format = "date"
            elif any(x in name_lower for x in ("party", "parties", "entity")):
                field_format = "entity_name"
            else:
                field_format = "text"
            
            extracted_values.append(
                ExtractedValue(
                    check_id=cr.get("check_id", ""),
                    check_name=cr.get("check_name", ""),
                    field_name=field_name,
                    field_value=display_value,
                    field_format=field_format,
                    page=cr.get("page"),
                    clause_uid=cr.get("clause_uid", ""),
                )
            )
    
    return extracted_values


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
        extracted_values: list[ExtractedValue] = []
    else:
        runner_repo = RunnerRepository(db)
        check_results = await runner_repo.load_check_results_for_run(run.id)
        
        # Прямое извлечение structured values — без aggregator
        extracted_values = _extract_structured_values_from_check_results(
            check_results,
            str(doc_id),
        )

    return DocumentExtractedValuesResponse(
        document_id=str(doc_id),
        filename=doc.filename,
        doc_type=doc.doc_type,
        extracted_values=extracted_values,
        total_extracted=len(extracted_values),
    )


    