# src/services/export/summary_builder.py

"""
Excel summary report builder for Deal Summary based on a single Run.

Sheets:
  1. "Overview"                — KPIs, severity breakdown, conditional checks
  2. "Top Risks"               — Top critical/high risks with evidence and structured data
  3. "By Doc Type"             — Document type summary with classification quality
  4. "Request List"            — DD requests with addressees and related document types
  5. "Classification Quality"  — Classification quality per document (optional)

Architectural principles:
  - Zero dependency on aggregator.py
  - Reads directly from check_results + documents + checks_by_id
  - Deterministic section ordering and sorting
  - Declarative localization via core.i18n.export_translator
"""

from __future__ import annotations

import io
from collections import defaultdict
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from core.config import settings
from core.i18n.export_translator import t_export
from core.logging import get_logger
from engine.playbook.models import CheckDefinition
from services.dd_request_rules import should_trigger_dd_request
from services.dd_request_composer import compose_dd_request

logger = get_logger(__name__)

_FONT_HEADER = Font(bold=True, size=11)
_FONT_TITLE = Font(bold=True, size=14)
_FONT_SMALL = Font(size=9, color="555555")
_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
_WRAP = Alignment(wrap_text=True, vertical="top")

_PRIORITY_FILLS = {
    "critical": PatternFill(start_color="FF4444", end_color="FF4444", fill_type="solid"),
    "high": PatternFill(start_color="FF8C00", end_color="FF8C00", fill_type="solid"),
    "medium": PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid"),
}
_FONT_WHITE = Font(color="FFFFFF", bold=True)


# ---------------------------------------------------------------------------
# Helpers — direct computation of metrics
# ---------------------------------------------------------------------------


def _count_severity(check_results: list[dict[str, Any]]) -> dict[str, int]:
    """Compute severity counts directly from check_results."""
    counts = {"critical": 0, "high": 0, "medium": 0, "pass": 0, "unclear": 0}
    for cr in check_results:
        result = cr.get("result", "unclear")
        severity = cr.get("severity", "medium")

        if result == "fail":
            if severity in counts:
                counts[severity] += 1
        elif result == "pass":
            counts["pass"] += 1
        else:
            counts["unclear"] += 1
    return counts


def _count_conditional(check_results: list[dict[str, Any]]) -> dict[str, int]:
    """Compute conditional checks statistics."""
    total = sum(1 for cr in check_results if cr.get("conditional_check_triggered"))
    triggered_fail = sum(
        1 for cr in check_results
        if cr.get("conditional_check_triggered") and cr.get("result") == "fail"
    )
    return {"total": total, "triggered_fail": triggered_fail}


def _count_quality_metrics(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute analysis quality metrics."""
    quarantine_count = sum(
        1 for doc in documents.values()
        if doc.get("status") == "quarantine"
    )

    degraded_docs = set()
    for cr in check_results:
        quality_flags = cr.get("quality_flags") or {}
        if isinstance(quality_flags, dict) and quality_flags.get("structure_degraded"):
            degraded_docs.add(cr.get("document_id", ""))

    fail_high_crit = [
        cr for cr in check_results
        if cr.get("result") == "fail" and cr.get("severity") in ("critical", "high")
    ]

    evidence_valid = sum(
        1 for cr in fail_high_crit
        if (cr.get("display_text") or cr.get("value_text") or "").strip()
    )

    evidence_validity_rate = (
        evidence_valid / len(fail_high_crit) if fail_high_crit else 1.0
    )

    return {
        "quarantine_count": quarantine_count,
        "degraded_count": len(degraded_docs),
        "evidence_validity_rate": evidence_validity_rate,
    }


def _get_top_risks(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    limit: int = 50,
    locale: str = "en",
) -> list[dict]:
    """Retrieve top risks from check_results."""
    severity_order = {"critical": 0, "high": 1, "medium": 2}

    fail_rows = [
        cr for cr in check_results
        if cr.get("result") == "fail" and cr.get("severity") in ("critical", "high")
    ]

    fail_rows.sort(key=lambda r: (
        severity_order.get(r.get("severity", "medium"), 9),
        -r.get("confidence", 0.0),
    ))

    risks = []
    for cr in fail_rows[:limit]:
        doc_id = cr.get("document_id", "")
        doc_info = documents.get(doc_id, {})

        risks.append({
            "check_name": cr.get("check_name", ""),
            "severity": cr.get("severity", "medium"),
            "document_name": doc_info.get("name", t_export("fallback.unknown", locale)),
            "doc_type": doc_info.get("doc_type", t_export("fallback.generic", locale)),
            "clause_uid": cr.get("clause_uid", ""),
            "page": cr.get("page"),
            "evidence_snippet": (cr.get("display_text") or cr.get("value_text", ""))[:200],
            "structured_data": cr.get("structured_data") or {},
            "conditional_check_triggered": cr.get("conditional_check_triggered", False),
            "trigger_name": cr.get("trigger_name", ""),
        })

    return risks


def _build_doc_type_summaries(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    locale: str = "en",
) -> list[dict]:
    """Build document type summaries."""
    by_type: dict[str, dict] = defaultdict(lambda: {
        "documents": set(),
        "checks": set(),
        "critical": 0,
        "high": 0,
        "medium": 0,
        "pass": 0,
        "unclear": 0,
        "conditional_fail": 0,
        "confidences": [],
        "low_confidence_count": 0,
    })

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        doc_type = documents.get(doc_id, {}).get("doc_type", t_export("fallback.generic", locale))

        by_type[doc_type]["documents"].add(doc_id)
        by_type[doc_type]["checks"].add(cr.get("check_id", ""))

        result = cr.get("result", "unclear")
        severity = cr.get("severity", "medium")

        if result == "fail":
            if severity in ("critical", "high", "medium"):
                by_type[doc_type][severity] += 1
        elif result == "pass":
            by_type[doc_type]["pass"] += 1
        else:
            by_type[doc_type]["unclear"] += 1

        if cr.get("conditional_check_triggered") and result == "fail":
            by_type[doc_type]["conditional_fail"] += 1

    for doc_id, doc_info in documents.items():
        doc_type = doc_info.get("doc_type", t_export("fallback.generic", locale))
        conf = doc_info.get("classification_confidence", 0.0)
        if conf:
            by_type[doc_type]["confidences"].append(conf)
            if conf < 0.6:
                by_type[doc_type]["low_confidence_count"] += 1

    summaries = []
    for doc_type, stats in by_type.items():
        confidences = stats["confidences"]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        summaries.append({
            "doc_type": doc_type,
            "document_count": len(stats["documents"]),
            "check_count": len(stats["checks"]),
            "critical": stats["critical"],
            "high": stats["high"],
            "medium": stats["medium"],
            "pass": stats["pass"],
            "unclear": stats["unclear"],
            "avg_classification_confidence": avg_conf,
            "low_confidence_count": stats["low_confidence_count"],
            "conditional_checks_triggered": stats["conditional_fail"],
        })

    summaries.sort(key=lambda s: -(s["critical"] + s["high"]))
    return summaries


def _build_dd_requests_for_summary(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, CheckDefinition],
    locale: str = "en",
) -> list[dict]:
    """Build DD requests for Summary (similar to Word Report)."""
    from services.export.dd_request_loader import get_dd_request_loader

    loader = get_dd_request_loader()

    results_by_check: dict[str, list[dict]] = {}
    for cr in check_results:
        check_id = cr.get("check_id", "")
        if not check_id:
            continue
        results_by_check.setdefault(check_id, []).append(cr)

    requests = []

    for check_id, cr_list in results_by_check.items():
        check_def = checks_by_id.get(check_id)
        if not check_def:
            continue

        # B7.9.2 / Variant B: DD-request trigger via rules engine.
        override_results = getattr(check_def, "dd_request_when_result", None)

        triggered_docs: list[dict] = []
        trigger_cr: dict | None = None
        for cr in cr_list:
            if not should_trigger_dd_request(
                check_result=cr,
                override_results=override_results,
            ):
                continue
            if trigger_cr is None:
                trigger_cr = cr
            doc_id = cr.get("document_id", "")
            structured_data = cr.get("structured_data") or {}
            triggered_docs.append({
                "document_id": doc_id,
                "document_name": documents.get(doc_id, {}).get("name", t_export("fallback.unknown", locale)),
                "doc_type": documents.get(doc_id, {}).get("doc_type", t_export("fallback.generic", locale)),
                "structured_data": structured_data,
            })

        if not triggered_docs:
            continue

        doc_names = [d["document_name"] for d in triggered_docs]
        text, addressee = compose_dd_request(
            check_result=trigger_cr,
            check_def=check_def,
            doc_names=doc_names,
            loader=loader,
            locale=locale,
        )

        # required_fields — только для structured_values (best-effort).
        required_fields: list[str] = []
        extraction = check_def.extraction
        if extraction is not None and getattr(extraction, "enabled", False):
            required_fields = [
                f.name for f in extraction.fields
                if getattr(f, "required", False)
            ]

        structured_values = []
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
                        })

        requests.append({
            "priority": check_def.severity,
            "check_name": check_def.name,
            "addressee": addressee,
            "text": text,
            "document_count": len(triggered_docs),
            "document_names": doc_names[:5],
            "doc_types": list(set(d["doc_type"] for d in triggered_docs)),
            "structured_values": structured_values[:5],
        })

    severity_order = {"critical": 0, "high": 1, "medium": 2}
    requests.sort(key=lambda r: severity_order.get(r["priority"], 9))

    return requests


def _get_extracted_values(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    limit: int = 500,
    locale: str = "en",
) -> list[dict]:
    """Extract structured values for Classification Quality sheet."""
    rows = []

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        doc_info = documents.get(doc_id, {})
        structured_data = cr.get("structured_data") or {}

        for field_name, field_value in structured_data.items():
            if isinstance(field_value, dict) and "value" in field_value:
                raw_display_value = field_value.get("value")
            else:
                raw_display_value = field_value

            if raw_display_value is None or str(raw_display_value) in ("not_found", "not_defined", "None", ""):
                continue

            rows.append({
                "document_name": doc_info.get("name", t_export("fallback.unknown", locale)),
                "doc_type": doc_info.get("doc_type", t_export("fallback.generic", locale)),
                "field_name": field_name,
                "field_value": str(raw_display_value),
            })

            if len(rows) >= limit:
                break

        if len(rows) >= limit:
            break

    return rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_summary_excel(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, CheckDefinition],
    deal_name: str,
    checks_mode: str = "",
    pipeline_strategy: str = "",
    locale: str = "en",
) -> bytes:
    """
    Build Excel file for Deal Summary based on a single Run.

    checks_mode and pipeline_strategy are displayed in the "Overview" sheet header.
    """
    wb = Workbook()

    _build_overview_sheet(
        wb,
        check_results=check_results,
        documents=documents,
        deal_name=deal_name,
        checks_mode=checks_mode,
        pipeline_strategy=pipeline_strategy,
        locale=locale,
    )
    _build_top_risks_sheet(wb, check_results, documents, locale=locale)
    _build_by_type_sheet(wb, check_results, documents, locale=locale)
    _build_requests_sheet(wb, check_results, documents, checks_by_id, locale=locale)

    if settings.EXPORT_CLASSIFICATION_METADATA:
        _build_classification_quality_sheet(wb, check_results, documents, locale=locale)

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    logger.info("Deal Summary Excel built (V1 path)", sheets=len(wb.sheetnames), locale=locale)
    return output.read()


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------


def _build_overview_sheet(
    wb: Workbook,
    *,
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    deal_name: str,
    checks_mode: str = "",
    pipeline_strategy: str = "",
    locale: str = "en",
) -> None:
    ws = wb.active
    ws.title = t_export("sheets.overview", locale)
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 22

    ws.cell(row=1, column=1, value=t_export("summary.title", locale, deal_name=deal_name)).font = _FONT_TITLE

    meta_parts: list[str] = []
    if checks_mode:
        meta_parts.append(t_export("summary.checks_mode", locale, checks_mode=checks_mode))
    if pipeline_strategy:
        meta_parts.append(t_export("summary.pipeline_strategy", locale, pipeline_strategy=pipeline_strategy))

    if meta_parts:
        meta_text = " | ".join(meta_parts)
        meta_cell = ws.cell(row=2, column=1, value=meta_text)
        meta_cell.font = _FONT_SMALL
        meta_cell.alignment = _WRAP

    counts = _count_severity(check_results)
    conditional_stats = _count_conditional(check_results)
    quality_metrics = _count_quality_metrics(check_results, documents)
    extracted_values = _get_extracted_values(check_results, documents, limit=1, locale=locale)

    data = [
        (t_export("summary.total_documents", locale), len(documents)),
        (t_export("summary.total_checks", locale), len(check_results)),
        ("Critical", counts["critical"]),
        ("High", counts["high"]),
        ("Medium", counts["medium"]),
        ("Pass", counts["pass"]),
        ("Unclear", counts["unclear"]),
        (t_export("summary.in_quarantine", locale), quality_metrics["quarantine_count"]),
        (t_export("summary.dd_requests", locale), 0),  # Hydrated dynamically in _build_requests_sheet
        (t_export("summary.evidence_validity", locale), f"{quality_metrics['evidence_validity_rate']:.0%}"),
        (t_export("summary.conditional_fail", locale), conditional_stats["triggered_fail"]),
        (t_export("summary.extracted_values", locale), len(extracted_values)),
    ]

    start_row = 4
    for i, (label, value) in enumerate(data, start_row):
        ws.cell(row=i, column=1, value=label).font = Font(bold=True)
        ws.cell(row=i, column=2, value=value)


def _build_top_risks_sheet(
    wb: Workbook,
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    locale: str = "en",
) -> None:
    ws = wb.create_sheet(t_export("sheets.top_risks", locale))

    headers = [
        "#",
        "Severity",
        t_export("columns.check", locale),
        t_export("columns.document", locale),
        t_export("columns.doc_type_short", locale),
        t_export("columns.evidence", locale),
        t_export("columns.page", locale),
        t_export("columns.clause", locale),
        t_export("columns.structured_data", locale),
        t_export("columns.trigger", locale),
    ]
    widths = [5, 12, 30, 30, 12, 45, 6, 10, 25, 18]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    risks = _get_top_risks(check_results, documents, limit=50, locale=locale)

    for i, risk in enumerate(risks, 2):
        ws.cell(row=i, column=1, value=i - 1)
        prio_cell = ws.cell(row=i, column=2, value=risk["severity"].upper())
        prio_cell.fill = _PRIORITY_FILLS.get(risk["severity"], PatternFill())
        if risk["severity"] == "critical":
            prio_cell.font = _FONT_WHITE
        ws.cell(row=i, column=3, value=risk["check_name"])
        ws.cell(row=i, column=4, value=risk["document_name"])
        ws.cell(row=i, column=5, value=risk["doc_type"])
        ws.cell(row=i, column=6, value=risk["evidence_snippet"]).alignment = _WRAP
        ws.cell(row=i, column=7, value=risk["page"] or "")
        ws.cell(row=i, column=8, value=risk["clause_uid"])
        sd_preview = (
            "; ".join(f"{k}={v}" for k, v in list(risk["structured_data"].items())[:3])
            if risk["structured_data"]
            else ""
        )
        ws.cell(row=i, column=9, value=sd_preview)
        ws.cell(row=i, column=10, value=risk["trigger_name"] or "")


def _build_by_type_sheet(
    wb: Workbook,
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    locale: str = "en",
) -> None:
    ws = wb.create_sheet(t_export("sheets.by_doc_type", locale))

    headers = [
        t_export("columns.doc_type", locale),
        t_export("columns.documents_count", locale),
        t_export("columns.checks_count", locale),
        "Critical",
        "High",
        "Medium",
        "Pass",
        "Unclear",
        t_export("columns.avg_conf", locale),
        t_export("columns.low_conf", locale),
        t_export("columns.conditional_fail", locale),
    ]
    widths = [22, 12, 12, 10, 10, 10, 10, 10, 16, 14, 14]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    summaries = _build_doc_type_summaries(check_results, documents, locale=locale)

    for row_num, summary in enumerate(summaries, 2):
        ws.cell(row=row_num, column=1, value=summary["doc_type"])
        ws.cell(row=row_num, column=2, value=summary["document_count"])
        ws.cell(row=row_num, column=3, value=summary["check_count"])
        ws.cell(row=row_num, column=4, value=summary["critical"])
        ws.cell(row=row_num, column=5, value=summary["high"])
        ws.cell(row=row_num, column=6, value=summary["medium"])
        ws.cell(row=row_num, column=7, value=summary["pass"])
        ws.cell(row=row_num, column=8, value=summary["unclear"])
        ws.cell(
            row=row_num,
            column=9,
            value=(
                f"{summary['avg_classification_confidence']:.0%}"
                if summary["avg_classification_confidence"]
                else ""
            ),
        )
        ws.cell(row=row_num, column=10, value=summary["low_confidence_count"])
        ws.cell(row=row_num, column=11, value=summary["conditional_checks_triggered"])


def _build_requests_sheet(
    wb: Workbook,
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, CheckDefinition],
    locale: str = "en",
) -> None:
    ws = wb.create_sheet(t_export("sheets.request_list", locale))

    headers = [
        "#",
        "Priority",
        t_export("columns.check", locale),
        t_export("columns.addressee", locale),
        t_export("columns.request_text", locale),
        t_export("columns.doc_types", locale),
        t_export("columns.documents", locale),
        t_export("columns.count", locale),
    ]
    widths = [5, 12, 25, 25, 55, 20, 35, 8]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    requests = _build_dd_requests_for_summary(check_results, documents, checks_by_id, locale=locale)

    # Update counter in Overview sheet
    overview_sheet_name = t_export("sheets.overview", locale)
    if overview_sheet_name in wb.sheetnames:
        overview_ws = wb[overview_sheet_name]
        dd_requests_label = t_export("summary.dd_requests", locale)
        for row in range(4, 20):
            if overview_ws.cell(row=row, column=1).value == dd_requests_label:
                overview_ws.cell(row=row, column=2, value=len(requests))
                break

    for i, req in enumerate(requests, 2):
        ws.cell(row=i, column=1, value=i - 1)
        prio_cell = ws.cell(row=i, column=2, value=req["priority"].upper())
        prio_cell.fill = _PRIORITY_FILLS.get(req["priority"], PatternFill())
        if req["priority"] == "critical":
            prio_cell.font = _FONT_WHITE
        ws.cell(row=i, column=3, value=req["check_name"])
        ws.cell(row=i, column=4, value=req["addressee"])
        ws.cell(row=i, column=5, value=req["text"]).alignment = _WRAP
        ws.cell(row=i, column=6, value=", ".join(req["doc_types"])).alignment = _WRAP
        ws.cell(row=i, column=7, value=", ".join(req["document_names"][:5])).alignment = _WRAP
        ws.cell(row=i, column=8, value=req["document_count"])


def _build_classification_quality_sheet(
    wb: Workbook,
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    locale: str = "en",
) -> None:
    """Sheet showing per-document classification quality."""
    ws = wb.create_sheet(t_export("sheets.classification_quality", locale))
    ws.freeze_panes = "A2"

    headers = [
        t_export("columns.document", locale),
        t_export("columns.doc_type", locale),
        t_export("columns.class_level", locale),
        t_export("columns.confidence", locale),
        t_export("columns.applied_triggers", locale),
    ]
    widths = [40, 22, 18, 14, 35]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    seen = {}
    for cr in check_results:
        doc_id = cr.get("document_id", "")
        if doc_id and doc_id not in seen:
            doc_info = documents.get(doc_id, {})
            seen[doc_id] = {
                "document_id": doc_id,
                "document_name": doc_info.get("name", t_export("fallback.unknown", locale)),
                "doc_type": doc_info.get("doc_type", t_export("fallback.generic", locale)),
                "classification_level": doc_info.get("classification_level", ""),
                "classification_confidence": doc_info.get("classification_confidence", 0.0),
            }

    triggers_by_doc: dict[str, list[str]] = defaultdict(list)
    for cr in check_results:
        if cr.get("conditional_check_triggered") and cr.get("trigger_name"):
            doc_id = cr.get("document_id", "")
            triggers_by_doc[doc_id].append(cr.get("trigger_name", ""))

    low_conf_fill = PatternFill(start_color="FFF0C0", end_color="FFF0C0", fill_type="solid")

    for row_num, row_data in enumerate(sorted(seen.values(), key=lambda r: r["doc_type"]), 2):
        ws.cell(row=row_num, column=1, value=row_data["document_name"])
        ws.cell(row=row_num, column=2, value=row_data["doc_type"])
        ws.cell(row=row_num, column=3, value=row_data["classification_level"])
        conf_cell = ws.cell(
            row=row_num,
            column=4,
            value=(
                f"{row_data['classification_confidence']:.0%}"
                if row_data["classification_confidence"]
                else ""
            ),
        )
        if row_data["classification_confidence"] and row_data["classification_confidence"] < 0.6:
            conf_cell.fill = low_conf_fill
        triggers = sorted(set(triggers_by_doc.get(row_data["document_id"], [])))
        ws.cell(row=row_num, column=5, value=", ".join(triggers))


        