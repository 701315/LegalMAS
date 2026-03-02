"""
Aggregator Service.

Collects all check results for a deal run and produces:
1. SeverityCounts
2. TopRisks — with structured_data and conditional trigger info
3. DDRequests — text from YAML dd_request_templates, with addressee
4. ExportRows — flat list with classification metadata
5. ConditionalCheckRows — only triggered conditional checks
6. StructuredValueRows — extracted amounts, dates, entities
7. DocTypeSummaries — per-type breakdown with classification quality
"""

import hashlib
import uuid as uuid_module
from collections import defaultdict
from typing import Any

from src.core.config import settings
from src.core.logging import get_logger
from src.services.export.dd_request_loader import get_dd_request_loader
from src.services.export.models import (
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
            trigger_name (NEW)
        documents: Dict of document_id → {
            name, folder_path, doc_type, status,
            classification_level (NEW),
            classification_confidence (NEW),
            applicable_triggers (NEW)
        }
    """
    agg = AggregatedResults(
        deal_id=deal_id,
        deal_name=deal_name,
        run_id=run_id,
        total_documents=len(documents),
        total_checks=len(check_results),
    )

    if not check_results:
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
            ", ".join(k for k, v in flags.items() if v is True) if isinstance(flags, dict) else ""
        )

        # NEW: structured_data preview
        structured_data = cr.get("structured_data") or {}
        structured_preview = ""
        if structured_data and settings.EXPORT_STRUCTURED_DATA_ENABLED:
            parts = [f"{k}={v}" for k, v in list(structured_data.items())[:3]]
            structured_preview = "; ".join(parts)

        # NEW: conditional check metadata
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
            document_id=doc_id,
            run_id=run_id,
            structured_data_preview=structured_preview,
            conditional_check_triggered=is_conditional,
            trigger_name=trigger_name,
            classification_level=doc_info.get("classification_level", ""),
            classification_confidence=doc_info.get("classification_confidence", 0.0),
        )
        rows.append(row)

        # NEW: Conditional checks sheet rows
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
                    evidence_snippet=_truncate(cr.get("value_text", ""), 200),
                    page=cr.get("page"),
                    confidence=cr.get("confidence", 0.0),
                    quality_flags=flags_str,
                )
            )

        # NEW: Structured value rows
        if structured_data and settings.EXPORT_STRUCTURED_DATA_ENABLED:
            for field_name, field_value in structured_data.items():
                if field_value and str(field_value) not in ("not_found", "None", ""):
                    structured_value_rows.append(
                        StructuredValueRow(
                            document_name=doc_info.get("name", "Unknown"),
                            doc_type=doc_info.get("doc_type", "Generic"),
                            check_name=cr.get("check_name", ""),
                            field_name=field_name,
                            field_value=str(field_value),
                            field_format=_infer_format(field_name, field_value),
                            page=cr.get("page"),
                            clause_uid=cr.get("clause_uid", ""),
                            document_id=doc_id,
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
                    if cr.get("check_id") == r.check_id and cr.get("document_id") == r.document_id
                ),
                {},
            ),
            conditional_check_triggered=r.conditional_check_triggered,
            trigger_name=r.trigger_name,
        )
        for r in fail_rows[: settings.EXPORT_TOP_RISKS_COUNT]
    ]

    # --- Step 3: DD Requests (text from YAML templates) ---
    agg.dd_requests = _generate_dd_requests(fail_rows, check_results)

    # --- Step 4: Doc Type Summaries (with classification metadata) ---
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
    """Generate deduplicated DD requests. Text from YAML templates."""
    loader = get_dd_request_loader()
    severity_order = {"critical": 0, "high": 1, "medium": 2}

    if not settings.EXPORT_DD_REQUEST_DEDUP:
        result = []
        for r in fail_rows:
            text, addressee = loader.render(r.check_id, r.check_name, [r.document_name])
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
                    evidence_refs=[r.evidence_snippet[:100]],
                )
            )
        return result

    # Group by check_id
    by_check: dict[str, list[ExportRow]] = defaultdict(list)
    for row in fail_rows:
        by_check[row.check_id].append(row)

    # Map check_id → structured values from results
    structured_by_check: dict[str, list[dict]] = defaultdict(list)
    for cr in check_results:
        sd = cr.get("structured_data") or {}
        if sd and cr.get("result") == "fail":
            for k, v in sd.items():
                if v and str(v) not in ("not_found", "None", ""):
                    structured_by_check[cr.get("check_id", "")].append(
                        {"field": k, "value": str(v), "doc": cr.get("document_id", "")}
                    )

    requests: list[DDRequest] = []
    for check_id, group in by_check.items():
        best_severity = min(
            group,
            key=lambda r: severity_order.get(r.severity, 9),
        ).severity

        doc_ids = list(dict.fromkeys(r.document_id for r in group))
        doc_names = list(dict.fromkeys(r.document_name for r in group))
        doc_types = list(dict.fromkeys(r.doc_type for r in group))
        evidence_refs = [r.evidence_snippet[:100] for r in group if r.evidence_snippet]

        text, addressee = loader.render(check_id, group[0].check_name, doc_names)

        dedup_key = hashlib.md5(f"{check_id}:{','.join(sorted(doc_ids))}".encode()).hexdigest()[:12]

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

        # Classification confidence stats
        confidences = [
            d.get("classification_confidence", 0.0)
            for d in type_docs
            if d.get("classification_confidence")
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        low_conf = sum(1 for c in confidences if c < 0.6)

        summaries.append(
            DocTypeSummary(
                doc_type=doc_type,
                document_count=len(unique_doc_ids),
                check_count=len(type_rows),
                critical=sum(
                    1 for r in type_rows if r.severity == "critical" and r.result == "fail"
                ),
                high=sum(1 for r in type_rows if r.severity == "high" and r.result == "fail"),
                medium=sum(1 for r in type_rows if r.severity == "medium" and r.result == "fail"),
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
