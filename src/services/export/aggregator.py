"""
Export Aggregator Service.

Собирает результаты проверок (checks) по одному deal run и подготавливает
агрегированный срез для экспорта: сводки по серьёзности, топ‑риски,
DD‑запросы, плоские строки экспорта, условные проверки и извлечённые
структурированные значения.

Основная функция:
- aggregate_results(deal_id, deal_name, run_id, check_results, documents) →
  AggregatedResults, где:
  1) severity_counts (SeverityCounts) — количество fail/pass/unclear
     по уровням серьёзности (critical/high/medium);
  2) rows (list[ExportRow]) — плоский список строк экспорта с:
     документом, check_id/name, result/severity, evidence_snippet, page,
     clause_uid, confidence, detector_used, quality_flags, qc_status,
     classification_level/confidence, origin, structured_data_preview и
     флагами условных проверок (conditional_check_triggered, trigger_name);
  3) top_risks (list[TopRisk]) — топ N (EXPORT_TOP_RISKS_COUNT) fail‑рисков,
     отсортированных по важности (critical/high/medium, затем по confidence),
     с вложенным structured_data и метаданными conditional checks;
  4) dd_requests (list[DDRequest]) — сформированные текстовые DD‑запросы
     из YAML‑шаблонов (dd_request_templates), сгруппированные по check_id,
     с дедупликацией по dedup_key и специальной пометкой
     `[ТРЕБУЕТ УТОЧНЕНИЯ]` для unclear‑critical/high;
  5) conditional_rows (list[ConditionalCheckRow]) — отдельный лист для
     сработавших условных проверок (если EXPORT_CONDITIONAL_CHECKS_SHEET включён);
  6) structured_value_rows (list[StructuredValueRow]) — нормализованные
     извлечённые значения из structured_data (amount/date/entity/text) для
     дальнейшего анализа/экспорта;
  7) doc_type_summaries (list[DocTypeSummary]) — сводки по типу документа:
     количество документов, уникальных проверок, распределение по severities,
     pass/unclear, средняя и низкая confidence классификации, количество
     сработавших conditional checks.

Дополнительно считает:
- quarantine_count — количество документов в статусе quarantine;
- degraded_count — число документов, где в quality_flags присутствует
  признак деградированной структуры (structure_degraded);
- evidence_validity_rate — доля fail‑проверок high/critical с непустым
  evidence_snippet;
- conditional_checks_total / conditional_checks_triggered — статистику
  по условным проверкам.

Используется export‑пайплайном для подготовки всех табличных
представлений, на основе которых далее строятся Excel/CSV‑экспорты
и DD‑репорты.
"""

import hashlib
import uuid as uuid_module
from collections import defaultdict
from typing import Any

from core.config import settings
from core.logging import get_logger
from services.export.dd_request_loader import get_dd_request_loader
from services.export.models import (
    AggregatedResults,
    ConditionalCheckRow,
    DDRequest,
    DocTypeSummary,
    ExportRow,
    SeverityCounts,
    StructuredValueRow,
    TopRisk,
)

logger = get_logger(__name__)


def aggregate_results(
    deal_id: str,
    deal_name: str,
    run_id: str,
    check_results: list[dict],
    documents: dict[str, dict],
) -> AggregatedResults:
    """
    Aggregate all check results for a deal run.

    Args:
        check_results: List of check result dicts from DB. Keys:
            check_id, check_name, result, severity, value_text,
            confidence, detector_used, quality_flags, qc_status,
            document_id,
            structured_data (NEW),
            conditional_check_triggered (NEW),
            trigger_name (NEW),
            segment_id (NEW),
            segment_type (NEW),
            segment_title (NEW),
            segment_order (NEW),
            is_primary_segment (NEW),
            chunk_id (NEW),
            chunk_index (NEW)
        documents: Dict of document_id → {
            name, folder_path, doc_type, status,
            classification_level (NEW),
            classification_confidence (NEW),
            applicable_triggers (NEW)
        }
    """
    logger.info(
        "Aggregate results starting",
        extra={
            "deal_id": deal_id,
            "run_id": run_id,
            "check_results_count": len(check_results),
            "documents_count": len(documents),
        },
    )

    agg = AggregatedResults(
        deal_id=deal_id,
        deal_name=deal_name,
        run_id=run_id,
        total_documents=len(documents),
        total_checks=len(check_results),
    )

    if not check_results:
        logger.info(
            "Aggregate results completed",
            extra={
                "deal_id": deal_id,
                "run_id": run_id,
                "structured_values": len(agg.structured_value_rows),
                "dd_requests": len(agg.dd_requests),
            },
        )
        return agg

    # --- Step 1: Build ExportRows and count severities ---
    rows: list[ExportRow] = []
    conditional_rows: list[ConditionalCheckRow] = []
    structured_value_rows: list[StructuredValueRow] = []
    counts = SeverityCounts()

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        doc_info = documents.get(doc_id, {})
        result = cr.get("result", "unclear")
        severity = cr.get("severity", "medium")

        # Count by severity
        if result == "fail":
            if severity == "critical":
                counts.critical += 1
            elif severity == "high":
                counts.high += 1
            else:
                counts.medium += 1
        elif result == "pass":
            counts.pass_count += 1
        else:
            counts.unclear += 1

        flags = cr.get("quality_flags", {})
        flags_str = (
            ", ".join(k for k, v in flags.items() if v is True)
            if isinstance(flags, dict)
            else ""
        )

        structured_data = cr.get("structured_data") or {}
        structured_preview = ""
        if structured_data and settings.EXPORT_STRUCTURED_DATA_ENABLED:
            parts = [f"{k}={v}" for k, v in list(structured_data.items())[:3]]
            structured_preview = "; ".join(parts)

        is_conditional = bool(cr.get("conditional_check_triggered"))
        trigger_name = cr.get("trigger_name", "")

        row = ExportRow(
            document_name=doc_info.get("name", "Unknown"),
            folder_path=doc_info.get("folder_path", ""),
            doc_type=doc_info.get("doc_type", "Generic"),
            check_name=cr.get("check_name", ""),
            check_id=cr.get("check_id", ""),
            result=result,
            severity=severity if result == "fail" else ("pass" if result == "pass" else severity),
            evidence_snippet=_truncate(
                cr.get("value_text", ""),
                settings.EXPORT_EVIDENCE_MAX_LENGTH,
            ),
            page=cr.get("page"),
            clause_uid=cr.get("clause_uid", ""),
            confidence=cr.get("confidence", 0.0),
            detector_used=cr.get("detector_used", ""),
            quality_flags=flags_str,
            qc_status=cr.get("qc_status", "pending"),
            qc_by=cr.get("qc_by"),
            qc_comment=cr.get("qc_comment"),
            qc_at=cr.get("qc_at").isoformat() if cr.get("qc_at") else None,
            document_id=doc_id,
            run_id=run_id,
            structured_data_preview=structured_preview,
            conditional_check_triggered=is_conditional,
            trigger_name=trigger_name,
            classification_level=doc_info.get("classification_level", ""),
            classification_confidence=doc_info.get("classification_confidence", 0.0),
            origin=cr.get("origin"),
            segment_id=cr.get("segment_id") or "",
            segment_type=cr.get("segment_type") or "",
            segment_title=cr.get("segment_title") or "",
            segment_order=cr.get("segment_order"),
            is_primary_segment=cr.get("is_primary_segment"),
            chunk_id=cr.get("chunk_id") or "",
            chunk_index=cr.get("chunk_index"),
        )
        rows.append(row)

        if is_conditional and settings.EXPORT_CONDITIONAL_CHECKS_SHEET:
            conditional_rows.append(
                ConditionalCheckRow(
                    document_name=doc_info.get("name", "Unknown"),
                    doc_type=doc_info.get("doc_type", "Generic"),
                    trigger_name=trigger_name,
                    check_id=cr.get("check_id", ""),
                    check_name=cr.get("check_name", ""),
                    result=result,
                    severity=severity,
                    evidence_snippet=_truncate(
                        cr.get("value_text", ""),
                        settings.EXPORT_EVIDENCE_MAX_LENGTH,
                    ),
                    page=cr.get("page"),
                    confidence=cr.get("confidence", 0.0),
                    quality_flags=flags_str,
                )
            )

        if structured_data and settings.EXPORT_STRUCTURED_DATA_ENABLED:
            for field_name, field_value in structured_data.items():
                if not field_value or str(field_value) in ("not_found", "None", ""):
                    continue

                if isinstance(field_value, dict) and "value" in field_value:
                    display_value = str(field_value["value"])
                else:
                    display_value = str(field_value)

                structured_value_rows.append(
                    StructuredValueRow(
                        document_name=doc_info.get("name", "Unknown"),
                        doc_type=doc_info.get("doc_type", "Generic"),
                        check_name=cr.get("check_name", ""),
                        field_name=field_name,
                        field_value=display_value,
                        field_format=_infer_format(field_name, display_value),
                        page=cr.get("page"),
                        clause_uid=cr.get("clause_uid", ""),
                        document_id=doc_id,
                        check_id=cr.get("check_id", ""),
                        segment_id=cr.get("segment_id") or "",
                        segment_type=cr.get("segment_type") or "",
                        segment_title=cr.get("segment_title") or "",
                        segment_order=cr.get("segment_order"),
                        is_primary_segment=cr.get("is_primary_segment"),
                        chunk_id=cr.get("chunk_id") or "",
                        chunk_index=cr.get("chunk_index"),
                    )
                )

    agg.severity_counts = counts
    agg.rows = rows
    agg.conditional_rows = conditional_rows
    agg.structured_value_rows = structured_value_rows

    # --- Step 2: Top Risks ---
    fail_rows = [r for r in rows if r.result == "fail"]
    severity_order = {"critical": 0, "high": 1, "medium": 2}
    fail_rows.sort(key=lambda r: (severity_order.get(r.severity, 9), -r.confidence))

    agg.top_risks = [
        TopRisk(
            check_id=r.check_id,
            check_name=r.check_name,
            severity=r.severity,
            document_name=r.document_name,
            document_id=r.document_id,
            doc_type=r.doc_type,
            evidence_snippet=r.evidence_snippet,
            page=r.page,
            clause_uid=r.clause_uid,
            confidence=r.confidence,
            structured_data=next(
                (
                    cr.get("structured_data") or {}
                    for cr in check_results
                    if cr.get("check_id") == r.check_id
                    and cr.get("document_id") == r.document_id
                    and (cr.get("segment_id") or "") == (r.segment_id or "")
                    and (cr.get("chunk_id") or "") == (r.chunk_id or "")
                ),
                {},
            ),
            conditional_check_triggered=r.conditional_check_triggered,
            trigger_name=r.trigger_name,
            segment_id=r.segment_id or "",
            segment_type=r.segment_type or "",
            segment_title=r.segment_title or "",
            segment_order=r.segment_order,
            is_primary_segment=r.is_primary_segment,
            chunk_id=r.chunk_id or "",
            chunk_index=r.chunk_index,
        )
        for r in fail_rows[: settings.EXPORT_TOP_RISKS_COUNT]
    ]

    # --- Step 3: DD Requests ---
    unclear_important = [
        r for r in rows
        if r.result == "unclear" and r.severity in ("critical", "high")
    ]
    all_rows_for_requests = fail_rows + unclear_important
    agg.dd_requests = _generate_dd_requests(all_rows_for_requests, check_results)

    # --- Step 4: Doc Type Summaries ---
    agg.doc_type_summaries = _build_doc_type_summaries(rows, documents)

    # --- Step 5: Quality metrics ---
    for doc_info in documents.values():
        if doc_info.get("status") == "quarantine":
            agg.quarantine_count += 1

    agg.degraded_count = len(
        set(r.document_id for r in rows if "structure_degraded" in r.quality_flags)
    )

    fail_high_crit = [r for r in rows if r.result == "fail" and r.severity in ("critical", "high")]
    agg.evidence_validity_rate = (
        sum(1 for r in fail_high_crit if r.evidence_snippet.strip()) / len(fail_high_crit)
        if fail_high_crit
        else 1.0
    )

    # --- Step 6: Conditional checks stats ---
    agg.conditional_checks_total = len(conditional_rows)
    agg.conditional_checks_triggered = sum(1 for r in conditional_rows if r.result == "fail")

    logger.info(
        "Aggregation complete",
        deal_id=deal_id,
        total_checks=agg.total_checks,
        severity=counts.to_dict(),
        top_risks=len(agg.top_risks),
        dd_requests=len(agg.dd_requests),
        conditional_rows=len(conditional_rows),
        structured_values=len(structured_value_rows),
    )

    return agg


def _generate_dd_requests(
    fail_rows: list[ExportRow],
    check_results: list[dict],
) -> list[DDRequest]:
    """
    Generate deduplicated DD requests with segment/chunk provenance.

    Text from YAML templates.

    Provenance strategy:
    - При дедупликации берётся provenance ПЕРВОГО наиболее важного результата
      для check_id (severity asc, confidence desc)
    - Если чек сработал в нескольких сегментах/чанках, viewer откроется
      на первом наиболее приоритетном результате
    - Для полной картины юрист должен смотреть DD Matrix
    """
    loader = get_dd_request_loader()
    severity_order = {"critical": 0, "high": 1, "medium": 2}

    rows_for_requests = fail_rows

    if not settings.EXPORT_DD_REQUEST_DEDUP:
        # Non-dedup mode: один запрос на каждый fail/unclear-important
        result: list[DDRequest] = []
        for r in rows_for_requests:
            text, addressee = loader.render(r.check_id, r.check_name, [r.document_name])

            if r.result == "unclear" and r.severity in ("critical", "high"):
                text = f"[ТРЕБУЕТ УТОЧНЕНИЯ] {text}"

            max_ev = getattr(settings, "EXPORT_EVIDENCE_MAX_LENGTH", 300)
            result.append(
                DDRequest(
                    request_id=str(uuid_module.uuid4()),
                    check_id=r.check_id,
                    check_name=r.check_name,
                    priority=r.severity,
                    text=text,
                    addressee=addressee,
                    document_ids=[r.document_id],
                    document_names=[r.document_name],
                    doc_types=[r.doc_type],
                    evidence_refs=[r.evidence_snippet[:max_ev]],
                    segment_id=r.segment_id or "",
                    segment_type=r.segment_type or "",
                    segment_title=r.segment_title or "",
                    segment_order=r.segment_order,
                    is_primary_segment=r.is_primary_segment,
                    chunk_id=r.chunk_id or "",
                    chunk_index=r.chunk_index,
                )
            )
        return result

    # Dedup mode: группируем по check_id
    by_check: dict[str, list[ExportRow]] = defaultdict(list)
    for row in rows_for_requests:
        by_check[row.check_id].append(row)

    structured_by_check: dict[str, list[dict]] = defaultdict(list)
    for cr in check_results:
        sd = cr.get("structured_data") or {}
        if sd and cr.get("result") in ("fail", "unclear"):
            for k, v in sd.items():
                if v and str(v) not in ("not_found", "None", ""):
                    structured_by_check[cr.get("check_id", "")].append(
                        {
                            "field": k,
                            "value": str(v),
                            "doc": cr.get("document_id", ""),
                            "segment_id": cr.get("segment_id") or "",
                            "chunk_id": cr.get("chunk_id") or "",
                            "chunk_index": cr.get("chunk_index"),
                        }
                    )

    requests: list[DDRequest] = []
    seen_keys: set[str] = set()
    max_ev = getattr(settings, "EXPORT_EVIDENCE_MAX_LENGTH", 300)

    for check_id, group in by_check.items():
        # Сортируем группу: сначала critical, потом high, потом medium,
        # затем по confidence DESC. Provenance берётся из first_result.
        group_sorted = sorted(
            group,
            key=lambda r: (severity_order.get(r.severity, 9), -r.confidence),
        )

        first_result = group_sorted[0]
        best_severity = first_result.severity

        doc_ids = list(dict.fromkeys(r.document_id for r in group))
        doc_names = list(dict.fromkeys(r.document_name for r in group))
        doc_types = list(dict.fromkeys(r.doc_type for r in group))
        evidence_refs = [
            r.evidence_snippet[:max_ev] for r in group if r.evidence_snippet
        ]

        text, addressee = loader.render(check_id, group[0].check_name, doc_names)

        if all(r.result == "unclear" for r in group) and any(
            r.severity in ("critical", "high") for r in group
        ):
            text = f"[ТРЕБУЕТ УТОЧНЕНИЯ] {text}"

        dedup_key = hashlib.md5(
            f"{check_id}:{','.join(sorted(doc_ids))}".encode()
        ).hexdigest()[:12]

        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        requests.append(
            DDRequest(
                request_id=str(uuid_module.uuid4()),
                check_id=check_id,
                check_name=group[0].check_name,
                priority=best_severity,
                text=text,
                addressee=addressee,
                document_ids=doc_ids,
                document_names=doc_names,
                doc_types=doc_types,
                evidence_refs=evidence_refs,
                structured_values=structured_by_check.get(check_id, []),
                dedup_key=dedup_key,
                segment_id=first_result.segment_id or "",
                segment_type=first_result.segment_type or "",
                segment_title=first_result.segment_title or "",
                segment_order=first_result.segment_order,
                is_primary_segment=first_result.is_primary_segment,
                chunk_id=first_result.chunk_id or "",
                chunk_index=first_result.chunk_index,
            )
        )

    requests.sort(key=lambda r: severity_order.get(r.priority, 9))
    return requests


def _build_doc_type_summaries(
    rows: list[ExportRow],
    documents: dict[str, dict],
) -> list[DocTypeSummary]:
    """Build per-document-type summaries with classification metadata."""
    by_type: dict[str, list[ExportRow]] = defaultdict(list)
    for row in rows:
        by_type[row.doc_type].append(row)

    summaries = []
    for doc_type, type_rows in sorted(by_type.items()):
        unique_doc_ids = set(r.document_id for r in type_rows)
        type_docs = [documents.get(d, {}) for d in unique_doc_ids]

        confidences = [
            d.get("classification_confidence", 0.0)
            for d in type_docs
            if d.get("classification_confidence")
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        low_conf = sum(1 for c in confidences if c < 0.6)

        unique_checks = set(r.check_id for r in type_rows)

        summaries.append(
            DocTypeSummary(
                doc_type=doc_type,
                document_count=len(unique_doc_ids),
                check_count=len(unique_checks),
                critical=sum(
                    1 for r in type_rows if r.severity == "critical" and r.result == "fail"
                ),
                high=sum(1 for r in type_rows if r.severity == "high" and r.result == "fail"),
                medium=sum(
                    1 for r in type_rows if r.severity == "medium" and r.result == "fail"
                ),
                pass_count=sum(1 for r in type_rows if r.result == "pass"),
                unclear=sum(1 for r in type_rows if r.result == "unclear"),
                avg_classification_confidence=round(avg_conf, 3),
                low_confidence_count=low_conf,
                conditional_checks_triggered=sum(
                    1 for r in type_rows if r.conditional_check_triggered and r.result == "fail"
                ),
            )
        )
    return summaries


def _infer_format(field_name: str, value: Any) -> str:
    """Infer display format from field name."""
    name_lower = field_name.lower()
    if any(x in name_lower for x in ("amount", "price", "sum", "cost")):
        return "money"
    if any(x in name_lower for x in ("date", "expiry", "term")):
        return "date"
    if any(x in name_lower for x in ("party", "parties", "entity")):
        return "entity_name"
    return "text"


def _truncate(text: str, max_length: int) -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."





