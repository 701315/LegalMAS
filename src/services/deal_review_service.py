# src/services/deal_review_service.py

"""
Сервис для UI-обзора сделки (deal review).

Задачи:
- загрузить из БД документы и результаты проверок для run;
- построить AggregatedResults через уже существующий Aggregator;
- преобразовать AggregatedResults в простые DTO для фронта.
"""

from typing import Any, Dict, List, Tuple

from core.logging import get_logger

from db.uow import db_uow
from db.repositories.runner_repo import RunnerRepository

from services.export.aggregator import aggregate_results
from services.export.models import (
    AggregatedResults,
    ExportRow,
    DDRequest,
    ConditionalCheckRow,
    StructuredValueRow,
)

from api.schemas.deal_review import (
    DocumentSummaryDTO,
    DocumentDetailDTO,
    CheckItemDTO,
    DDRequestDTO,
    ConditionalCheckDTO,
    ExtractedValueDTO,
)

logger = get_logger(__name__)


# -------------------------------------------------------------------
# Загрузка AggregatedResults из БД
# -------------------------------------------------------------------


async def load_aggregated_results(
    deal_id: str,
    run_id: str,
) -> Tuple[AggregatedResults, Dict[str, Dict[str, Any]]]:
    """
    Загрузить документы и результаты проверок для сделки/рана
    и собрать AggregatedResults.

    Возвращает:
    - aggregated: AggregatedResults (используется и Exporter'ами, и UI-API);
    - documents: словарь {document_id: {name, folder_path, doc_type, status,
                                        classification_level, classification_confidence,
                                        applicable_triggers}}.
    """
    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        documents = await runner_repo.load_documents_for_run(run_id)
        check_results = await runner_repo.load_check_results_for_run(run_id)

    logger.info(
        "Building AggregatedResults for deal run",
        deal_id=deal_id,
        run_id=run_id,
        documents=len(documents),
        check_results=len(check_results),
    )

    aggregated = aggregate_results(
        deal_id=deal_id,
        deal_name=f"Deal {deal_id}",
        run_id=run_id,
        check_results=check_results,
        documents=documents,
    )
    return aggregated, documents


# -------------------------------------------------------------------
# Маппинг AggregatedResults → DTO для UI
# -------------------------------------------------------------------


def build_document_summaries(
    agg: AggregatedResults,
    documents: Dict[str, Dict[str, Any]],
) -> List[DocumentSummaryDTO]:
    """
    Построить краткие статусы документов для списка документов сделки.
    """
    by_doc: Dict[str, Dict[str, Any]] = {}

    for row in agg.rows:
        doc_id = row.document_id
        if doc_id not in by_doc:
            doc_meta = documents.get(doc_id, {})
            by_doc[doc_id] = {
                "document_id": doc_id,
                "name": row.document_name,
                "doc_type": row.doc_type,
                "status": doc_meta.get("status", ""),
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "pass_count": 0,
                "unclear_count": 0,
                "has_degraded_structure": "structure_degraded" in (row.quality_flags or ""),
                # in_quarantine можно доработать, если статус quarantine прокидывается в documents
                "in_quarantine": doc_meta.get("status", "") == "quarantine",
                "classification_level": doc_meta.get("classification_level", ""),
                "classification_confidence": float(doc_meta.get("classification_confidence", 0.0)),
            }

        if row.result == "fail":
            if row.severity == "critical":
                by_doc[doc_id]["critical_count"] += 1
            elif row.severity == "high":
                by_doc[doc_id]["high_count"] += 1
            elif row.severity == "medium":
                by_doc[doc_id]["medium_count"] += 1
        elif row.result == "pass":
            by_doc[doc_id]["pass_count"] += 1
        elif row.result == "unclear":
            by_doc[doc_id]["unclear_count"] += 1

    return [DocumentSummaryDTO(**v) for v in by_doc.values()]


def build_document_detail(
    agg: AggregatedResults,
    documents: Dict[str, Dict[str, Any]],
    document_id: str,
) -> DocumentDetailDTO:
    """
    Построить детальную карточку документа (DocumentDetailDTO) по его id.
    """
    doc_meta = documents.get(document_id)
    if not doc_meta:
        raise ValueError(f"Document {document_id} not found in aggregated data")

    # --- NEW: индекс структурированных значений по документу и проверке ---
    structured_by_doc_check: Dict[tuple[str, str], dict[str, Any]] = {}

    for sv in agg.structured_value_rows:
        if sv.document_id != document_id:
            continue
        key = (sv.document_id, sv.check_id)  # мы добавили check_id в StructuredValueRow
        bucket = structured_by_doc_check.setdefault(key, {})
        bucket[sv.field_name] = sv.field_value

    checks: List[CheckItemDTO] = []
    for row in agg.rows:
        if row.document_id != document_id:
            continue

        key = (row.document_id, row.check_id)
        structured_data = structured_by_doc_check.get(key, {})  # dict по полям для этой проверки

    checks: List[CheckItemDTO] = []
    for row in agg.rows:
        if row.document_id != document_id:
            continue
        checks.append(
            CheckItemDTO(
                check_id=row.check_id,
                check_name=row.check_name,
                result=row.result,
                severity=row.severity,
                evidence_snippet=row.evidence_snippet,
                page=row.page,              # в ExportRow могут быть None — это ок
                clause_uid=row.clause_uid,
                confidence=row.confidence,
                detector_used=row.detector_used,
                # в Aggregator quality_flags — строка; для DTO делаем простую обёртку
                quality_flags={"flags": row.quality_flags} if row.quality_flags else None,
                conditional_check_triggered=row.conditional_check_triggered,
                trigger_name=row.trigger_name,
                structured_data=structured_data,
            )
        )

    return DocumentDetailDTO(
        document_id=document_id,
        name=doc_meta["name"],
        doc_type=doc_meta["doc_type"],
        status=doc_meta["status"],
        classification_level=doc_meta.get("classification_level", ""),
        classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
        applicable_triggers=doc_meta.get("applicable_triggers", []),
        checks=checks,
    )


def build_dd_requests(agg: AggregatedResults) -> List[DDRequestDTO]:
    """
    Построить список DD-запросов для UI из AggregatedResults.dd_requests.
    """
    requests: List[DDRequestDTO] = []
    for req in agg.dd_requests:
        requests.append(
            DDRequestDTO(
                request_id=req.request_id,
                priority=req.priority,
                check_id=req.check_id,
                check_name=req.check_name,
                addressee=req.addressee,
                text=req.text,
                document_names=req.document_names,
                doc_types=req.doc_types,
                structured_values=req.structured_values,
            )
        )
    return requests


def build_conditional_checks(agg: AggregatedResults) -> List[ConditionalCheckDTO]:
    """
    Построить список условных проверок для UI из AggregatedResults.conditional_rows.
    """
    out: List[ConditionalCheckDTO] = []
    for cr in agg.conditional_rows:
        out.append(
            ConditionalCheckDTO(
                document_name=cr.document_name,
                doc_type=cr.doc_type,
                trigger_name=cr.trigger_name,
                check_id=cr.check_id,
                check_name=cr.check_name,
                result=cr.result,
                severity=cr.severity,
                evidence_snippet=cr.evidence_snippet,
                page=cr.page,
                confidence=cr.confidence,
                # аналогично: quality_flags в Aggregator строка, заворачиваем в dict
                quality_flags={"flags": cr.quality_flags} if cr.quality_flags else None,
            )
        )
    return out


def build_extracted_values(agg: AggregatedResults) -> List[ExtractedValueDTO]:
    """
    Построить список извлечённых значений (structured values) для UI
    из AggregatedResults.structured_value_rows.
    """
    out: List[ExtractedValueDTO] = []
    for sv in agg.structured_value_rows:
        out.append(
            ExtractedValueDTO(
                document_name=sv.document_name,
                doc_type=sv.doc_type,
                check_name=sv.check_name,
                field_name=sv.field_name,
                field_value=sv.field_value,
                field_format=sv.field_format,
                page=sv.page,
                clause_uid=sv.clause_uid,
            )
        )
    return out
