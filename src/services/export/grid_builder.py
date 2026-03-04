"""
DD Grid Builder.

Sheets:
  1. "DD Grid"           — full results, 15 columns (+ structured data, classification)
  2. "Summary"           — KPI with conditional checks stats
  3. "Conditional Checks"— only triggered conditional check results (if enabled)
  4. "Extracted Values"  — structured data extracted (amounts, dates, etc.)
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.config import settings
from core.logging import get_logger
from services.export.models import AggregatedResults

logger = get_logger(__name__)

_FILLS = {
    "critical": PatternFill(start_color="FF4444", end_color="FF4444", fill_type="solid"),
    "high": PatternFill(start_color="FF8C00", end_color="FF8C00", fill_type="solid"),
    "medium": PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid"),
    "pass": PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid"),
    "unclear": PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid"),
}
_FONT_WHITE = Font(color="FFFFFF", bold=True)
_FONT_BLACK = Font(color="000000")
_FONT_HEADER = Font(bold=True, size=11)
_FONT_TITLE = Font(bold=True, size=14)
_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
_WRAP = Alignment(wrap_text=True, vertical="top")

# Base columns (always present)
_BASE_COLUMNS = [
    ("Документ", 35, "document_name"),
    ("Папка", 25, "folder_path"),
    ("Тип документа", 18, "doc_type"),
    ("Проверка", 30, "check_name"),
    ("Результат", 12, "result"),
    ("Severity", 12, "severity"),
    ("Evidence / Значение", 50, "evidence_snippet"),
    ("Стр.", 6, "page"),
    ("Пункт", 10, "clause_uid"),
    ("Confidence", 12, "confidence"),
    ("Детектор", 10, "detector_used"),
    ("Флаги", 22, "quality_flags"),
    ("QC", 12, "qc_status"),
]

# Optional columns (added when settings enabled)
_STRUCTURED_COLUMN = ("Извлечённые данные", 30, "structured_data_preview")
_CLASSIFIER_COLUMNS = [
    ("Уровень классиф.", 15, "classification_level"),
    ("Conf. классиф.", 14, "classification_confidence"),
]
_CONDITIONAL_COLUMN = ("Триггер", 18, "trigger_name")


def build_grid_excel(aggregated: AggregatedResults) -> bytes:
    wb = Workbook()

    _build_grid_sheet(wb, aggregated)
    _build_summary_sheet(wb, aggregated)

    if settings.EXPORT_CONDITIONAL_CHECKS_SHEET and aggregated.conditional_rows:
        _build_conditional_sheet(wb, aggregated)

    if settings.EXPORT_STRUCTURED_DATA_ENABLED and aggregated.structured_value_rows:
        _build_extracted_values_sheet(wb, aggregated)

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    logger.info("DD Grid Excel built", rows=len(aggregated.rows), sheets=len(wb.sheetnames))
    return output.read()


def _get_columns(aggregated: AggregatedResults) -> list[tuple]:
    cols = list(_BASE_COLUMNS)
    if settings.EXPORT_STRUCTURED_DATA_ENABLED and aggregated.structured_value_rows:
        cols.append(_STRUCTURED_COLUMN)
    if settings.EXPORT_CLASSIFICATION_METADATA:
        cols.extend(_CLASSIFIER_COLUMNS)
    if aggregated.conditional_rows:
        cols.append(_CONDITIONAL_COLUMN)
    return cols


def _build_grid_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    ws = wb.active
    ws.title = "DD Grid"
    ws.freeze_panes = "A2"

    columns = _get_columns(aggregated)

    for col_idx, (header, width, _) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _FONT_HEADER
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    severity_order = {"critical": 0, "high": 1, "medium": 2, "unclear": 3, "pass": 4}
    sorted_rows = sorted(
        aggregated.rows,
        key=lambda r: (severity_order.get(r.severity, 9), r.document_name, r.check_name),
    )

    for row_idx, row in enumerate(sorted_rows, 2):
        for col_idx, (_, _, field) in enumerate(columns, 1):
            value = getattr(row, field, "")
            if field == "confidence" and isinstance(value, float):
                value = f"{value:.0%}"
            if field == "classification_confidence" and isinstance(value, float):
                value = f"{value:.0%}" if value > 0 else ""
            if field in ("page",) and value is None:
                value = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value else "")
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP

        fill = _FILLS.get(row.severity, _FILLS["unclear"])
        for col_idx in range(1, len(columns) + 1):
            ws.cell(row=row_idx, column=col_idx).fill = fill
            if row.severity == "critical":
                ws.cell(row=row_idx, column=col_idx).font = _FONT_WHITE

    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(sorted_rows) + 1}"


def _build_summary_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 15

    ws.cell(row=1, column=1, value=f"DD Summary: {aggregated.deal_name}").font = _FONT_TITLE
    ws.merge_cells("A1:B1")

    kpi_data = [
        ("Всего документов", aggregated.total_documents),
        ("Всего проверок", aggregated.total_checks),
        ("", ""),
        ("🔴 Critical", aggregated.severity_counts.critical),
        ("🟠 High", aggregated.severity_counts.high),
        ("🟡 Medium", aggregated.severity_counts.medium),
        ("🟢 Pass", aggregated.severity_counts.pass_count),
        ("⚪ Unclear", aggregated.severity_counts.unclear),
        ("", ""),
        ("Документов в карантине", aggregated.quarantine_count),
        ("Документов с degraded структурой", aggregated.degraded_count),
        ("Evidence validity rate", f"{aggregated.evidence_validity_rate:.0%}"),
        ("", ""),
        ("DD Requests (дедупл.)", len(aggregated.dd_requests)),
        # NEW:
        ("Условных проверок (всего)", aggregated.conditional_checks_total),
        ("Условных проверок (FAIL)", aggregated.conditional_checks_triggered),
        ("Извлечённых значений", len(aggregated.structured_value_rows)),
    ]

    for row, (label, value) in enumerate(kpi_data, 3):
        ws.cell(row=row, column=1, value=label).font = Font(bold=True) if label else Font()
        cell_val = ws.cell(row=row, column=2, value=value)
        cell_val.alignment = Alignment(horizontal="right")
        if "Critical" in str(label):
            cell_val.fill = _FILLS["critical"]
            cell_val.font = _FONT_WHITE
        elif "High" in str(label):
            cell_val.fill = _FILLS["high"]
        elif "Medium" in str(label):
            cell_val.fill = _FILLS["medium"]
        elif "Pass" in str(label):
            cell_val.fill = _FILLS["pass"]
        elif "Unclear" in str(label):
            cell_val.fill = _FILLS["unclear"]


def _build_conditional_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    """Sheet showing only conditional check results with their triggers."""
    ws = wb.create_sheet("Conditional Checks")
    ws.freeze_panes = "A2"

    headers = [
        ("Документ", 35),
        ("Тип", 15),
        ("Триггер", 22),
        ("Проверка", 30),
        ("Результат", 12),
        ("Severity", 12),
        ("Evidence", 45),
        ("Стр.", 6),
        ("Confidence", 12),
        ("Флаги", 22),
    ]
    fields = [
        "document_name",
        "doc_type",
        "trigger_name",
        "check_name",
        "result",
        "severity",
        "evidence_snippet",
        "page",
        "confidence",
        "quality_flags",
    ]

    for col, (h, w) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = _FONT_HEADER
        cell.border = _THIN_BORDER
        ws.column_dimensions[get_column_letter(col)].width = w

    for row_idx, crow in enumerate(aggregated.conditional_rows, 2):
        for col_idx, field in enumerate(fields, 1):
            value = getattr(crow, field, "")
            if field == "confidence" and isinstance(value, float):
                value = f"{value:.0%}"
            if field == "page" and value is None:
                value = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value else "")
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP

        fill = _FILLS.get(crow.severity, _FILLS["unclear"])
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=row_idx, column=col_idx).fill = fill


def _build_extracted_values_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    """Sheet showing structured values extracted from documents."""
    ws = wb.create_sheet("Extracted Values")
    ws.freeze_panes = "A2"

    headers = [
        ("Документ", 35),
        ("Тип", 15),
        ("Проверка", 30),
        ("Поле", 20),
        ("Значение", 35),
        ("Формат", 15),
        ("Стр.", 6),
        ("Пункт", 10),
    ]
    fields = [
        "document_name",
        "doc_type",
        "check_name",
        "field_name",
        "field_value",
        "field_format",
        "page",
        "clause_uid",
    ]

    for col, (h, w) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = _FONT_HEADER
        cell.border = _THIN_BORDER
        ws.column_dimensions[get_column_letter(col)].width = w

    for row_idx, srow in enumerate(aggregated.structured_value_rows, 2):
        for col_idx, field in enumerate(fields, 1):
            value = getattr(srow, field, "")
            if field == "page" and value is None:
                value = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value else "")
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP
