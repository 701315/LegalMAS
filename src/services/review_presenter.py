"""
Review Presenter.

Тонкие маппер-функции из AggregatedResults в API DTO.

Принципы:
- Никакой бизнес-логики, только проекция данных.
- Никаких обращений к БД.
- Каждая функция соответствует одному API-эндпоинту.
"""

from __future__ import annotations

from typing import Any

from api.schemas.deal_review import (
    CheckItemDTO,
    ConditionalCheckDTO,
    DDRequestDTO,
    DocumentDetailDTO,
    DocumentSummaryDTO,
    ExtractedValueDTO,
)
from services.export.models import AggregatedResults


def build_document_summaries(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
) -> list[DocumentSummaryDTO]:
    """
    Построить краткие статусы документов.

    Счётчики рисков:
    - critical_count, high_count, medium_count: количество fail по severity
    - pass_count: количество pass
    - unclear_count: количество unclear
    Документы сортируются по имени (A→Z).
    """
    by_doc: dict[str, dict[str, Any]] = {}

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
                # ИСПРАВЛЕНО: добавлено отсутствующее поле in_quarantine
                "in_quarantine": doc_meta.get("status", "") == "quarantine",
                "classification_level": doc_meta.get("classification_level", ""),
                "classification_confidence": float(
                    doc_meta.get("classification_confidence", 0.0)
                ),
            }

        # ИСПРАВЛЕНО: явная обработка каждого case без f-string магии.
        # Оригинальный код использовал f"{row.severity}_count" для fail-строк,
        # что приводило к созданию ключей типа "low_count", "unclear_count"
        # которых нет в DocumentSummaryDTO → ValidationError.
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
        # Прочие result (missing_required_clause и т.д.) — не считаем,
        # чтобы не создавать невалидные ключи в by_doc.

    return [
        DocumentSummaryDTO(**v)
        for v in sorted(by_doc.values(), key=lambda x: x["name"].lower())
    ]


def build_document_detail(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
    document_id: str,
) -> DocumentDetailDTO:
    """
    Построить детальную карточку документа по его id.

    Карточка содержит все check-результаты для данного документа
    в том порядке, в котором они хранятся в AggregatedResults.
    """
    doc_meta = documents.get(document_id)
    if not doc_meta:
        raise ValueError(f"Document {document_id} not found in aggregated data")

    checks: list[CheckItemDTO] = []

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
                page=row.page,
                clause_uid=row.clause_uid or "",
                confidence=row.confidence,
                detector_used=row.detector_used,
                quality_flags={"flags": row.quality_flags} if row.quality_flags else None,
                conditional_check_triggered=row.conditional_check_triggered,
                trigger_name=row.trigger_name,
                structured_data=row.structured_data or {},
                origin=row.origin,
                segment_id=row.segment_id or None,
                segment_type=row.segment_type or None,
                segment_title=row.segment_title or None,
                segment_order=row.segment_order,
                is_primary_segment=row.is_primary_segment,
                display_text=row.display_text,
                review_status=row.review_status,
                review_message=row.review_message,
                needs_manual_review=row.needs_manual_review,
                ui_mode=row.ui_mode,
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


def build_dd_requests(agg: AggregatedResults) -> list[DDRequestDTO]:
    """
    Построить список DD-запросов для UI.
    Передаёт segment provenance для навигации во viewer.
    """
    return [
        DDRequestDTO(
            request_id=req.request_id,
            priority=req.priority,
            check_id=req.check_id,
            check_name=req.check_name,
            addressee=req.addressee,
            text=req.text,
            document_ids=req.document_ids,
            document_names=req.document_names,
            doc_types=req.doc_types,
            structured_values=req.structured_values,
            segment_id=req.segment_id or None,
            segment_type=req.segment_type or None,
            segment_title=req.segment_title or None,
            segment_order=req.segment_order,
            is_primary_segment=req.is_primary_segment,
            chunk_id=req.chunk_id or None,
            chunk_index=req.chunk_index,
        )
        for req in agg.dd_requests
    ]


def build_conditional_checks(agg: AggregatedResults) -> list[ConditionalCheckDTO]:
    """Построить список условных проверок для UI."""
    return [
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
            quality_flags={"flags": cr.quality_flags} if cr.quality_flags else None,
        )
        for cr in agg.conditional_rows
    ]


def build_extracted_values(agg: AggregatedResults) -> list[ExtractedValueDTO]:
    """Построить список извлечённых структурированных значений для UI."""
    return [
        ExtractedValueDTO(
            document_name=sv.document_name,
            doc_type=sv.doc_type,
            check_name=sv.check_name,
            field_name=sv.field_name,
            field_value=sv.field_value,
            field_format=sv.field_format,
            page=sv.page,
            clause_uid=sv.clause_uid or "",
            segment_id=sv.segment_id or None,
            segment_type=sv.segment_type or None,
            segment_title=sv.segment_title or None,
            segment_order=sv.segment_order,
            is_primary_segment=sv.is_primary_segment,
        )
        for sv in agg.structured_value_rows
    ]


