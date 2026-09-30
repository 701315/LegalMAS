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

from engine.playbook.models import CheckDefinition
from services.dd_request_rules import should_trigger_dd_request


def build_dd_requests(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, CheckDefinition],
) -> list[DDRequestDTO]:
    """
    Построить список DD-запросов для UI.

    Триггер: check_result.result ∈ {missing_required_cla, unclear}.
    Опциональный per-check override — CheckDefinition.dd_request_when_result.
    Источник: прямое чтение check_results + CheckDefinition.
    Aggregator больше не нужен для этой фичи.

    Args:
        check_results: Список результатов проверок из БД.
        documents: Словарь {document_id: {name, doc_type, ...}}.
        checks_by_id: Словарь {check_id: CheckDefinition} для доступа к required полям.
    """
    from services.export.dd_request_loader import get_dd_request_loader

    loader = get_dd_request_loader()

    # Группируем check_results по check_id
    results_by_check: dict[str, list[dict]] = {}
    for cr in check_results:
        check_id = cr.get("check_id", "")
        if not check_id:
            continue
        results_by_check.setdefault(check_id, []).append(cr)

    dd_requests: list[DDRequestDTO] = []

    for check_id, cr_list in results_by_check.items():
        check_def = checks_by_id.get(check_id)
        if not check_def:
            continue

        # B7.9.2 / Variant B: DD-request trigger via rules engine.
        # Fires when check_result.result ∈ DD_REQUEST_DEFAULT_RESULTS
        # (missing_required_cla, unclear) or per-check YAML override
        # (CheckDefinition.dd_request_when_result).
        override_results = getattr(check_def, "dd_request_when_result", None)

        triggered_docs: list[dict] = []
        for cr in cr_list:
            if not should_trigger_dd_request(
                check_result=cr,
                override_results=override_results,
            ):
                continue
            doc_id = cr.get("document_id", "")
            structured_data = cr.get("structured_data") or {}
            triggered_docs.append({
                "document_id": doc_id,
                "document_name": documents.get(doc_id, {}).get("name", "Unknown"),
                "doc_type": documents.get(doc_id, {}).get("doc_type", "Generic"),
                "structured_data": structured_data,
                "segment_id": cr.get("segment_id"),
                "segment_type": cr.get("segment_type"),
                "segment_title": cr.get("segment_title"),
                "segment_order": cr.get("segment_order"),
                "is_primary_segment": cr.get("is_primary_segment"),
                "chunk_id": cr.get("chunk_id"),
                "chunk_index": cr.get("chunk_index"),
            })

        if not triggered_docs:
            continue

        # Сортируем по приоритету (critical/high/medium из check_def.severity)
        severity_order = {"critical": 0, "high": 1, "medium": 2}
        triggered_docs.sort(key=lambda d: severity_order.get(check_def.severity, 9))

        # Берём provenance из первого документа
        first_doc = triggered_docs[0]

        # Рендерим текст из YAML шаблона
        doc_names = [d["document_name"] for d in triggered_docs]
        text, addressee = loader.render(check_id, check_def.name, doc_names)

        # required_fields — только для сбора structured_values (best-effort),
        # НЕ для триггера. У check без extraction список пуст.
        required_fields: list[str] = []
        extraction = check_def.extraction
        if extraction is not None and getattr(extraction, "enabled", False):
            required_fields = [
                f.name for f in extraction.fields
                if getattr(f, "required", False)
            ]

        # Собираем structured_values только из required полей
        structured_values: list[dict] = []
        for doc in triggered_docs:
            for field_name in required_fields:
                field_value = doc["structured_data"].get(field_name)
                if field_value:
                    if isinstance(field_value, dict) and "value" in field_value:
                        display_value = str(field_value.get("value", ""))
                    else:
                        display_value = str(field_value)
                    if display_value and display_value not in ("not_found", "not_defined", "None", ""):
                        structured_values.append({
                            "field": field_name,
                            "value": display_value,
                            "doc": doc["document_id"],
                        })

        # Use localized check_name from check_results if available, fallback to playbook
        localized_check_name = cr_list[0].get("check_name", check_def.name) if cr_list else check_def.name

        dd_requests.append(
            DDRequestDTO(
                request_id="",  # UUID генерируется на фронте или в API
                priority=check_def.severity,
                check_id=check_id,
                check_name=localized_check_name,
                addressee=addressee,
                text=text,
                document_ids=[d["document_id"] for d in triggered_docs],
                document_names=doc_names,
                doc_types=list(set(d["doc_type"] for d in triggered_docs)),
                structured_values=structured_values,
                segment_id=first_doc["segment_id"] or None,
                segment_type=first_doc["segment_type"] or None,
                segment_title=first_doc["segment_title"] or None,
                segment_order=first_doc["segment_order"],
                is_primary_segment=first_doc["is_primary_segment"],
                chunk_id=first_doc["chunk_id"] or None,
                chunk_index=first_doc["chunk_index"],
            )
        )

    # Сортировка по приоритету
    severity_order = {"critical": 0, "high": 1, "medium": 2}
    dd_requests.sort(key=lambda r: severity_order.get(r.priority, 9))

    return dd_requests


def build_conditional_checks(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> list[ConditionalCheckDTO]:
    """
    Построить список условных проверок для UI.

    Источник: прямое чтение check_results (conditional_check_triggered=True).
    Aggregator больше не нужен для этой фичи.
    """
    return [
        ConditionalCheckDTO(
            document_name=documents.get(cr.get("document_id", ""), {}).get("name", "Unknown"),
            doc_type=documents.get(cr.get("document_id", ""), {}).get("doc_type", "Generic"),
            trigger_name=cr.get("trigger_name", ""),
            check_id=cr.get("check_id", ""),
            check_name=cr.get("check_name", ""),
            result=cr.get("result", "unclear"),
            severity=cr.get("severity", "medium"),
            evidence_snippet=(cr.get("display_text") or cr.get("value_text", ""))[:300],
            page=cr.get("page"),
            confidence=cr.get("confidence", 0.0),
            quality_flags={"flags": cr.get("quality_flags")} if cr.get("quality_flags") else None,
        )
        for cr in check_results
        if cr.get("conditional_check_triggered")
    ]


def build_extracted_values(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> list[ExtractedValueDTO]:
    """
    Построить список извлечённых структурированных значений для UI.

    Источник: прямое чтение structured_data из check_results.
    Aggregator больше не нужен для этой фичи.
    """
    results: list[ExtractedValueDTO] = []

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        doc_info = documents.get(doc_id, {})
        structured_data = cr.get("structured_data") or {}

        for field_name, field_value in structured_data.items():
            # Нормализация значения (как в aggregator.py)
            if isinstance(field_value, dict) and "value" in field_value:
                raw_display_value = field_value.get("value")
            else:
                raw_display_value = field_value

            # Пропускаем пустые / служебные значения
            if raw_display_value is None or str(raw_display_value) in ("not_found", "None", ""):
                continue

            display_value = str(raw_display_value)

            results.append(
                ExtractedValueDTO(
                    document_name=doc_info.get("name", "Unknown"),
                    doc_type=doc_info.get("doc_type", "Generic"),
                    check_name=cr.get("check_name", ""),
                    field_name=field_name,
                    field_value=display_value,
                    field_format=_infer_field_format(field_name, display_value),
                    page=cr.get("page"),
                    clause_uid=cr.get("clause_uid", ""),
                    segment_id=cr.get("segment_id") or None,
                    segment_type=cr.get("segment_type") or None,
                    segment_title=cr.get("segment_title") or None,
                    segment_order=cr.get("segment_order"),
                    is_primary_segment=cr.get("is_primary_segment"),
                )
            )

    return results


def _infer_field_format(field_name: str, value: str) -> str:
    """Infer display format from field name (как в aggregator.py)."""
    name_lower = field_name.lower()
    if any(x in name_lower for x in ("amount", "price", "sum", "cost")):
        return "money"
    if any(x in name_lower for x in ("date", "expiry", "term")):
        return "date"
    if any(x in name_lower for x in ("party", "parties", "entity")):
        return "entity_name"
    return "text"


