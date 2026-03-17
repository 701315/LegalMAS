# src/services/export/summary_builder.py

"""
Deal Summary Builder.

Sheets:
  1. "Overview"               — KPI, severity counts, conditional stats
  2. "Top Risks"              — top critical/high findings with evidence + structured data
  3. "By Doc Type"            — breakdown with classification quality metrics (NEW)
  4. "Request List"           — DD requests with addressee column (NEW)
  5. "Classification Quality" — per-document classification metadata (NEW)
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from core.config import settings
from core.logging import get_logger
from services.export.models import AggregatedResults

logger = get_logger(__name__)

_FONT_HEADER = Font(bold=True, size=11)
_FONT_TITLE = Font(bold=True, size=14)
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


def build_summary_excel(aggregated: AggregatedResults) -> bytes:
    wb = Workbook()

    _build_overview_sheet(wb, aggregated)
    _build_top_risks_sheet(wb, aggregated)
    _build_by_type_sheet(wb, aggregated)
    _build_requests_sheet(wb, aggregated)

    if settings.EXPORT_CLASSIFICATION_METADATA:
        _build_classification_quality_sheet(wb, aggregated)

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    logger.info("Deal Summary Excel built", sheets=len(wb.sheetnames))
    return output.read()


def _build_overview_sheet(wb: Workbook, agg: AggregatedResults) -> None:
    ws = wb.active
    ws.title = "Overview"
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 20

    ws.cell(row=1, column=1, value=f"Deal Summary: {agg.deal_name}").font = _FONT_TITLE

    data = [
        ("Документов", agg.total_documents),
        ("Проверок выполнено", agg.total_checks),
        ("Critical", agg.severity_counts.critical),
        ("High", agg.severity_counts.high),
        ("Medium", agg.severity_counts.medium),
        ("Pass", agg.severity_counts.pass_count),
        ("Unclear", agg.severity_counts.unclear),
        ("В карантине", agg.quarantine_count),
        ("DD Requests", len(agg.dd_requests)),
        ("Evidence validity", f"{agg.evidence_validity_rate:.0%}"),
        # NEW:
        ("Условных проверок (FAIL)", agg.conditional_checks_triggered),
        ("Извлечённых значений", len(agg.structured_value_rows)),
    ]

    for i, (label, value) in enumerate(data, 3):
        ws.cell(row=i, column=1, value=label).font = Font(bold=True)
        ws.cell(row=i, column=2, value=value)


def _build_top_risks_sheet(wb: Workbook, agg: AggregatedResults) -> None:
    ws = wb.create_sheet("Top Risks")

    # NEW: Added "Структ. данные" and "Триггер" columns
    headers = [
        "#",
        "Severity",
        "Проверка",
        "Документ",
        "Тип",
        "Evidence",
        "Стр.",
        "Пункт",
        "Структ. данные",
        "Триггер",
    ]
    widths = [5, 12, 30, 30, 12, 45, 6, 10, 25, 18]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    for i, risk in enumerate(agg.top_risks, 2):
        ws.cell(row=i, column=1, value=i - 1)
        sev_cell = ws.cell(row=i, column=2, value=risk.severity.upper())
        sev_cell.fill = _PRIORITY_FILLS.get(risk.severity, PatternFill())
        if risk.severity == "critical":
            sev_cell.font = _FONT_WHITE
        ws.cell(row=i, column=3, value=risk.check_name)
        ws.cell(row=i, column=4, value=risk.document_name)
        ws.cell(row=i, column=5, value=risk.doc_type)
        ws.cell(row=i, column=6, value=risk.evidence_snippet[:200]).alignment = _WRAP
        ws.cell(row=i, column=7, value=risk.page or "")
        ws.cell(row=i, column=8, value=risk.clause_uid)
        # NEW: structured data preview
        sd_preview = (
            "; ".join(f"{k}={v}" for k, v in list(risk.structured_data.items())[:3])
            if risk.structured_data
            else ""
        )
        ws.cell(row=i, column=9, value=sd_preview)
        # NEW: trigger name
        ws.cell(row=i, column=10, value=risk.trigger_name or "")


def _build_by_type_sheet(wb: Workbook, agg: AggregatedResults) -> None:
    ws = wb.create_sheet("By Doc Type")

    # NEW: Added classification quality columns
    headers = [
        "Тип документа",
        "Документов",
        "Проверок",
        "Critical",
        "High",
        "Medium",
        "Pass",
        "Unclear",
        "Avg Conf. класс.",
        "Низк. уверен.",
        "Условн. FAIL",
    ]
    widths = [22, 12, 12, 10, 10, 10, 10, 10, 16, 14, 14]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    for row_num, summary in enumerate(agg.doc_type_summaries, 2):
        ws.cell(row=row_num, column=1, value=summary.doc_type)
        ws.cell(row=row_num, column=2, value=summary.document_count)
        ws.cell(row=row_num, column=3, value=summary.check_count)
        ws.cell(row=row_num, column=4, value=summary.critical)
        ws.cell(row=row_num, column=5, value=summary.high)
        ws.cell(row=row_num, column=6, value=summary.medium)
        ws.cell(row=row_num, column=7, value=summary.pass_count)
        ws.cell(row=row_num, column=8, value=summary.unclear)
        ws.cell(
            row=row_num,
            column=9,
            value=f"{summary.avg_classification_confidence:.0%}"
            if summary.avg_classification_confidence
            else "",
        )
        ws.cell(row=row_num, column=10, value=summary.low_confidence_count)
        ws.cell(row=row_num, column=11, value=summary.conditional_checks_triggered)


def _build_requests_sheet(wb: Workbook, agg: AggregatedResults) -> None:
    ws = wb.create_sheet("Request List")

    # NEW: Added "Адресат" and "Типы документов" columns
    headers = [
        "#",
        "Priority",
        "Проверка",
        "Адресат",
        "Текст запроса",
        "Типы документов",
        "Документы",
        "Кол-во",
    ]
    widths = [5, 12, 25, 25, 55, 20, 35, 8]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    for i, req in enumerate(agg.dd_requests, 2):
        ws.cell(row=i, column=1, value=i - 1)
        prio_cell = ws.cell(row=i, column=2, value=req.priority.upper())
        prio_cell.fill = _PRIORITY_FILLS.get(req.priority, PatternFill())
        if req.priority == "critical":
            prio_cell.font = _FONT_WHITE
        ws.cell(row=i, column=3, value=req.check_name)
        ws.cell(row=i, column=4, value=req.addressee)  # NEW
        ws.cell(row=i, column=5, value=req.text).alignment = _WRAP
        ws.cell(row=i, column=6, value=", ".join(req.doc_types)).alignment = _WRAP  # NEW
        ws.cell(row=i, column=7, value=", ".join(req.document_names[:5])).alignment = _WRAP
        ws.cell(row=i, column=8, value=req.document_count)


def _build_classification_quality_sheet(wb: Workbook, agg: AggregatedResults) -> None:
    """Sheet showing per-document classification quality."""
    ws = wb.create_sheet("Classification Quality")
    ws.freeze_panes = "A2"

    headers = [
        "Документ",
        "Тип документа",
        "Уровень классиф.",
        "Confidence",
        "Применённые триггеры",
    ]
    widths = [40, 22, 18, 14, 35]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        ws.cell(row=1, column=col, value=h).font = _FONT_HEADER
        ws.column_dimensions[chr(64 + col)].width = w

    seen = {}
    for row in agg.rows:
        if row.document_id not in seen:
            seen[row.document_id] = row

    low_conf_fill = PatternFill(start_color="FFF0C0", end_color="FFF0C0", fill_type="solid")

    for row_num, row in enumerate(sorted(seen.values(), key=lambda r: r.doc_type), 2):
        ws.cell(row=row_num, column=1, value=row.document_name)
        ws.cell(row=row_num, column=2, value=row.doc_type)
        ws.cell(row=row_num, column=3, value=row.classification_level)
        conf_cell = ws.cell(
            row=row_num,
            column=4,
            value=f"{row.classification_confidence:.0%}" if row.classification_confidence else "",
        )
        # Highlight low-confidence classifications
        if row.classification_confidence and row.classification_confidence < 0.6:
            conf_cell.fill = low_conf_fill
        # Trigger names from conditional rows for this doc
        triggers = sorted(
            set(
                cr.trigger_name
                for cr in agg.conditional_rows
                if cr.document_name == row.document_name
            )
        )
        ws.cell(row=row_num, column=5, value=", ".join(triggers))
