# src/services/export/grid_builder.py

"""
DD Grid Builder — формирует Excel-книгу с результатами DD-анализа.

Листы:
  1. "DD Grid"            — полный плоский список результатов (документ × чек)
  2. "DD Matrix"          — матричное представление (строки=документы, столбцы=чеки)
  3. "Summary"            — KPI-сводка по рану
  4. "By Doc Type"        — сводка по типам документов
  5. "Conditional Checks" — только сработавшие условные проверки (если включено)
  6. "Extracted Values"   — структурированные значения (суммы, даты и т.п.)
"""

import io
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from core.config import settings
from core.logging import get_logger
from services.export.models import AggregatedResults

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Стили
# ---------------------------------------------------------------------------

_FILLS = {
    "critical": PatternFill(start_color="FF4444", end_color="FF4444", fill_type="solid"),
    "high":     PatternFill(start_color="FF8C00", end_color="FF8C00", fill_type="solid"),
    "medium":   PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid"),
    "pass":     PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid"),
    "unclear":  PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid"),
    "na":       PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid"),
}
_FONT_WHITE  = Font(color="FFFFFF", bold=True)
_FONT_BLACK  = Font(color="000000")
_FONT_HEADER = Font(bold=True, size=11)
_FONT_TITLE  = Font(bold=True, size=14)
_FONT_SMALL  = Font(size=9, color="555555")
_THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
_WRAP   = Alignment(wrap_text=True, vertical="top")
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


# ---------------------------------------------------------------------------
# Колонки плоского листа DD Grid
# ---------------------------------------------------------------------------

_BASE_COLUMNS = [
    ("Документ",            35, "document_name"),
    ("Папка",               25, "folder_path"),
    ("Тип документа",       18, "doc_type"),
    ("Проверка",            30, "check_name"),
    ("Результат",           12, "result"),
    ("Severity",            12, "severity"),
    ("Evidence / Значение", 50, "evidence_snippet"),
    ("Стр.",                 6, "page"),
    ("Пункт",               10, "clause_uid"),
    ("Confidence",          12, "confidence"),
    ("Детектор",            10, "detector_used"),
    ("Флаги",               22, "quality_flags"),
    ("QC",                  12, "qc_status"),
]

_STRUCTURED_COLUMN  = ("Извлечённые данные", 30, "structured_data_preview")
_CLASSIFIER_COLUMNS = [
    ("Уровень классиф.", 15, "classification_level"),
    ("Conf. классиф.",   14, "classification_confidence"),
]
_CONDITIONAL_COLUMN = ("Триггер", 18, "trigger_name")
_ORIGIN_COLUMN      = ("Источник чека", 18, "origin")


# ---------------------------------------------------------------------------
# Публичная точка входа
# ---------------------------------------------------------------------------

def build_grid_excel(
    aggregated: AggregatedResults,
    checks_mode: str = "",
    pipeline_strategy: str = "",
) -> bytes:
    """
    Построить Excel-книгу со всеми листами DD-анализа.

    Важно:
    - checks_mode / pipeline_strategy используются только для шапки
      (Summary / DD Grid), сами данные не меняют.
    """
    wb = Workbook()

    _build_grid_sheet(wb, aggregated, checks_mode=checks_mode, pipeline_strategy=pipeline_strategy)
    _build_matrix_sheet(wb, aggregated)
    _build_summary_sheet(
        wb,
        aggregated,
        checks_mode=checks_mode,
        pipeline_strategy=pipeline_strategy,
    )

    if aggregated.doc_type_summaries:
        _build_doc_type_sheet(wb, aggregated)

    if settings.EXPORT_CONDITIONAL_CHECKS_SHEET and aggregated.conditional_rows:
        _build_conditional_sheet(wb, aggregated)

    if settings.EXPORT_STRUCTURED_DATA_ENABLED and aggregated.structured_value_rows:
        _build_extracted_values_sheet(wb, aggregated)

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    logger.info(
        "DD Grid Excel built",
        deal_id=aggregated.deal_id,
        rows=len(aggregated.rows),
        sheets=len(wb.sheetnames),
    )
    return output.read()



# ---------------------------------------------------------------------------
# Лист 1: DD Grid — плоский список результатов
# ---------------------------------------------------------------------------

def _get_columns(aggregated: AggregatedResults) -> list[tuple]:
    cols = list(_BASE_COLUMNS)
    if settings.EXPORT_STRUCTURED_DATA_ENABLED and aggregated.structured_value_rows:
        cols.append(_STRUCTURED_COLUMN)
    if settings.EXPORT_CLASSIFICATION_METADATA:
        cols.extend(_CLASSIFIER_COLUMNS)
    if aggregated.conditional_rows:
        cols.append(_CONDITIONAL_COLUMN)
    # Источник чека полезен всегда
    cols.append(_ORIGIN_COLUMN)
    return cols


def _build_grid_sheet(
    wb: Workbook,
    aggregated: AggregatedResults,
    *,
    checks_mode: str = "",
    pipeline_strategy: str = "",
) -> None:
    ws = wb.active
    ws.title = "DD Grid"
    ws.freeze_panes = "A2"

    # Можно в A1 положить человекочитаемую шапку по ран‑метаданным.
    # Но у тебя уже заголовки в строке 1 под данные, поэтому аккуратнее:
    # оставляем как есть, чтобы не ломать формат — шапку лучше делать на Summary.
    
    columns = _get_columns(aggregated)

    # Заголовки
    for col_idx, (header, width, _) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _FONT_HEADER
        cell.border = _THIN_BORDER
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    severity_order = {"critical": 0, "high": 1, "medium": 2, "unclear": 3, "pass": 4}
    sorted_rows = sorted(
        aggregated.rows,
        key=lambda r: (
            severity_order.get(r.severity, 9),
            r.document_name.lower(),
            r.check_name.lower(),
        ),
    )

    for row_idx, row in enumerate(sorted_rows, 2):
        for col_idx, (_, _, field) in enumerate(columns, 1):
            value = getattr(row, field, "")
            if field == "confidence" and isinstance(value, float):
                value = f"{value:.0%}"
            elif field == "classification_confidence" and isinstance(value, float):
                value = f"{value:.0%}" if value > 0 else ""
            elif field == "page" and value is None:
                value = ""
            elif field == "origin" and not value:
                value = "—"

            cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value else "")
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP

        fill = _FILLS.get(row.severity, _FILLS["unclear"])
        for col_idx in range(1, len(columns) + 1):
            ws.cell(row=row_idx, column=col_idx).fill = fill
            if row.severity == "critical":
                ws.cell(row=row_idx, column=col_idx).font = _FONT_WHITE

    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(sorted_rows) + 1}"


# ---------------------------------------------------------------------------
# Лист 2: DD Matrix — матричное представление
# ---------------------------------------------------------------------------

def _build_matrix_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    ws = wb.create_sheet("DD Matrix")

    if not aggregated.rows:
        ws.cell(row=1, column=1, value="Нет данных для матрицы").font = _FONT_TITLE
        return

    # 1. Реестр чеков с разделением на группы
    global_checks: list[str] = []
    typed_checks: list[str] = []
    meta_by_check: dict[str, dict] = {}

    for row in aggregated.rows:
        cid = row.check_id
        if cid in meta_by_check:
            continue
        origin = (row.origin or "").upper()
        meta = {
            "check_name": row.check_name,
            "origin": origin,
            "severity": row.severity,
        }
        meta_by_check[cid] = meta
        if origin == "GLOBAL_PLAYBOOK":
            global_checks.append(cid)
        else:
            typed_checks.append(cid)

    # итоговый порядок столбцов: глобальные → разделитель → doc-type/conditional
    check_ids = global_checks + typed_checks
    if not check_ids:
        ws.cell(row=1, column=1, value="Нет чеков для матрицы").font = _FONT_TITLE
        return

    # 2. Индекс результатов: (doc_id, check_id) → ExportRow
    result_index: dict[tuple[str, str], object] = {}
    for row in aggregated.rows:
        result_index[(row.document_id, row.check_id)] = row

    # 3. Аггрегированные данные по документам
    doc_stats: dict[str, dict] = defaultdict(lambda: {"critical": 0, "fail": 0})
    doc_meta: dict[str, dict] = {}
    for row in aggregated.rows:
        doc_id = row.document_id
        if doc_id not in doc_meta:
            doc_meta[doc_id] = {
                "document_name": row.document_name,
                "doc_type": row.doc_type,
                "classification_level": row.classification_level,
                "classification_confidence": row.classification_confidence,
            }
        if row.result == "fail":
            doc_stats[doc_id]["fail"] += 1
            if row.severity == "critical":
                doc_stats[doc_id]["critical"] += 1

    doc_order: list[str] = []
    seen_doc_ids: set[str] = set()
    for row in aggregated.rows:
        if row.document_id not in seen_doc_ids:
            seen_doc_ids.add(row.document_id)
            doc_order.append(row.document_id)

    doc_order.sort(
        key=lambda doc_id: (
            -doc_stats[doc_id]["critical"],
            -doc_stats[doc_id]["fail"],
            doc_meta.get(doc_id, {}).get("document_name", "").lower(),
        )
    )

    # 4. Заголовки
    FIXED_COLS = 4  # A–D

    ws.cell(row=1, column=1, value="Документ").font = _FONT_HEADER
    ws.cell(row=1, column=2, value="Тип").font = _FONT_HEADER
    ws.cell(row=1, column=3, value="Conf. классиф.").font = _FONT_HEADER
    ws.cell(row=1, column=4, value="Уровень").font = _FONT_HEADER

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 10

    for col_idx in range(1, FIXED_COLS + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER

    current_col = FIXED_COLS + 1

    # Заголовки глобальных чеков
    for cid in global_checks:
        meta = meta_by_check[cid]
        origin = meta["origin"]
        severity = meta["severity"]
        check_name = meta["check_name"]
        origin_icon = "🌐" if origin == "GLOBAL_PLAYBOOK" else "📄"
        cell = ws.cell(row=1, column=current_col, value=f"{origin_icon} {check_name}")
        cell.font = _FONT_HEADER
        cell.border = _THIN_BORDER
        cell.alignment = _CENTER
        cell.fill = _FILLS.get(severity, _FILLS["unclear"])
        if severity == "critical":
            cell.font = Font(bold=True, size=11, color="FFFFFF")
        ws.column_dimensions[get_column_letter(current_col)].width = 24
        current_col += 1

    # Визуальный разделитель (пустая колонка)
    separator_col = current_col
    ws.column_dimensions[get_column_letter(separator_col)].width = 3
    ws.cell(row=1, column=separator_col, value="").border = _THIN_BORDER
    current_col += 1

    # Заголовки doc-type/conditional чеков
    for cid in typed_checks:
        meta = meta_by_check[cid]
        origin = meta["origin"]
        severity = meta["severity"]
        check_name = meta["check_name"]
        origin_icon = "⚡" if origin == "CONDITIONAL" else "📄"
        cell = ws.cell(row=1, column=current_col, value=f"{origin_icon} {check_name}")
        cell.font = _FONT_HEADER
        cell.border = _THIN_BORDER
        cell.alignment = _CENTER
        cell.fill = _FILLS.get(severity, _FILLS["unclear"])
        if severity == "critical":
            cell.font = Font(bold=True, size=11, color="FFFFFF")
        ws.column_dimensions[get_column_letter(current_col)].width = 24
        current_col += 1

    ws.freeze_panes = ws.cell(row=2, column=FIXED_COLS + 1)

    # 5. Строки документов
    for row_idx, doc_id in enumerate(doc_order, 2):
        meta = doc_meta.get(doc_id, {})
        name = meta.get("document_name", "")
        doc_type = meta.get("doc_type", "")
        level = meta.get("classification_level", "")
        conf = meta.get("classification_confidence", 0.0)
        conf_str = f"{conf:.0%}" if conf and conf > 0 else "—"

        ws.cell(row=row_idx, column=1, value=name)
        ws.cell(row=row_idx, column=2, value=doc_type)
        ws.cell(row=row_idx, column=3, value=conf_str)
        ws.cell(row=row_idx, column=4, value=level)

        for col in range(1, FIXED_COLS + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP

        # Глобальные чеки
        col = FIXED_COLS + 1
        for cid in global_checks:
            cell = ws.cell(row=row_idx, column=col)
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP
            export_row = result_index.get((doc_id, cid))
            if export_row is None:
                cell.value = "n/a"
                cell.fill = _FILLS["na"]
                cell.font = _FONT_SMALL
            else:
                snippet = (export_row.evidence_snippet or "")[:80]
                page_str = f" [стр. {export_row.page}]" if export_row.page else ""
                result_label = {
                    "fail": "✗ FAIL",
                    "pass": "✓ PASS",
                    "unclear": "? UNCLEAR",
                }.get(export_row.result, export_row.result.upper())
                cell.value = f"{result_label}{page_str}\n{snippet}" if snippet else result_label
                cell.fill = _FILLS.get(export_row.severity, _FILLS["unclear"])
                cell.font = _FONT_WHITE if export_row.severity == "critical" else _FONT_BLACK
            col += 1

        # Пустой разделитель
        ws.cell(row=row_idx, column=separator_col).border = _THIN_BORDER

        # Doc-type / conditional чеки
        col = separator_col + 1
        for cid in typed_checks:
            cell = ws.cell(row=row_idx, column=col)
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP
            export_row = result_index.get((doc_id, cid))
            if export_row is None:
                cell.value = "n/a"
                cell.fill = _FILLS["na"]
                cell.font = _FONT_SMALL
            else:
                snippet = (export_row.evidence_snippet or "")[:80]
                page_str = f" [стр. {export_row.page}]" if export_row.page else ""
                result_label = {
                    "fail": "✗ FAIL",
                    "pass": "✓ PASS",
                    "unclear": "? UNCLEAR",
                }.get(export_row.result, export_row.result.upper())
                cell.value = f"{result_label}{page_str}\n{snippet}" if snippet else result_label
                cell.fill = _FILLS.get(export_row.severity, _FILLS["unclear"])
                cell.font = _FONT_WHITE if export_row.severity == "critical" else _FONT_BLACK
            col += 1

        ws.row_dimensions[row_idx].height = 42

# ---------------------------------------------------------------------------
# Лист 3: Summary — KPI
# ---------------------------------------------------------------------------

def _build_summary_sheet(
    wb: Workbook,
    aggregated: AggregatedResults,
    *,
    checks_mode: str = "",
    pipeline_strategy: str = "",
) -> None:
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 30

    # Строка 1 — название сделки
    ws.cell(row=1, column=1, value=f"DD Summary: {aggregated.deal_name}").font = _FONT_TITLE
    ws.merge_cells("A1:B1")

    # Строка 2 — контекст последнего Run
    meta_parts: list[str] = []
    if checks_mode:
        meta_parts.append(f"Режим проверок: {checks_mode}")
    if pipeline_strategy:
        meta_parts.append(f"Стратегия пайплайна: {pipeline_strategy}")
    if meta_parts:
        meta_text = " | ".join(meta_parts)
        cell = ws.cell(row=2, column=1, value=meta_text)
        cell.font = _FONT_SMALL
        cell.alignment = _WRAP
        ws.merge_cells("A2:B2")

    kpi_data = [
        ("Всего документов",           aggregated.total_documents),
        ("Всего проверок",            aggregated.total_checks),
        ("",                          ""),
        ("🔴 Critical",               aggregated.severity_counts.critical),
        ("🟠 High",                   aggregated.severity_counts.high),
        ("🟡 Medium",                 aggregated.severity_counts.medium),
        ("🟢 Pass",                   aggregated.severity_counts.pass_count),
        ("⚪ Unclear",                aggregated.severity_counts.unclear),
        ("",                          ""),
        ("Документов в карантине",    aggregated.quarantine_count),
        ("Документов с degraded OCR", aggregated.degraded_count),
        ("Evidence validity rate",    f"{aggregated.evidence_validity_rate:.0%}"),
        ("",                          ""),
        ("DD Requests (дедупл.)",     len(aggregated.dd_requests)),
        ("Условных проверок (всего)", aggregated.conditional_checks_total),
        ("Условных проверок (FAIL)",  aggregated.conditional_checks_triggered),
        ("Извлечённых значений",      len(aggregated.structured_value_rows)),
    ]

    start_row = 4  # 1 — title, 2 — meta, 3 — пустая строка под отступ
    for row, (label, value) in enumerate(kpi_data, start_row):
        label_cell = ws.cell(row=row, column=1, value=label)
        label_cell.font = Font(bold=bool(label))
        val_cell = ws.cell(row=row, column=2, value=value)
        val_cell.alignment = Alignment(horizontal="right")

        if "Critical" in str(label):
            val_cell.fill = _FILLS["critical"]
            val_cell.font = _FONT_WHITE
        elif "High" in str(label):
            val_cell.fill = _FILLS["high"]
        elif "Medium" in str(label):
            val_cell.fill = _FILLS["medium"]
        elif "Pass" in str(label):
            val_cell.fill = _FILLS["pass"]
        elif "Unclear" in str(label):
            val_cell.fill = _FILLS["unclear"]



# ---------------------------------------------------------------------------
# Лист 4: By Doc Type — сводка по типам документа
# ---------------------------------------------------------------------------

def _build_doc_type_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    ws = wb.create_sheet("By Doc Type")
    ws.freeze_panes = "A2"

    headers = [
        ("Тип документа",         28),
        ("Документов",            12),
        ("Проверок",              12),
        ("🔴 Critical",           12),
        ("🟠 High",               12),
        ("🟡 Medium",             12),
        ("🟢 Pass",               12),
        ("⚪ Unclear",            12),
        ("Conf. классиф. (avg)",  20),
        ("Низкая conf. (<0.6)",   20),
        ("Условных FAIL",         16),
    ]

    for col_idx, (header, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _FONT_HEADER
        cell.border = _THIN_BORDER
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    sorted_summaries = sorted(
        aggregated.doc_type_summaries,
        key=lambda s: -(s.critical + s.high),
    )

    for row_idx, s in enumerate(sorted_summaries, 2):
        values = [
            s.doc_type,
            s.document_count,
            s.check_count,
            s.critical,
            s.high,
            s.medium,
            s.pass_count,
            s.unclear,
            f"{s.avg_classification_confidence:.0%}" if s.avg_classification_confidence > 0 else "—",
            s.low_confidence_count,
            s.conditional_checks_triggered,
        ]

        for col_idx, value in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP

        # Подсветка по рискам
        if s.critical > 0:
            ws.cell(row=row_idx, column=4).fill = _FILLS["critical"]
            ws.cell(row=row_idx, column=4).font = _FONT_WHITE
        if s.high > 0:
            ws.cell(row=row_idx, column=5).fill = _FILLS["high"]
        if s.medium > 0:
            ws.cell(row=row_idx, column=6).fill = _FILLS["medium"]
        if s.pass_count > 0:
            ws.cell(row=row_idx, column=7).fill = _FILLS["pass"]


# ---------------------------------------------------------------------------
# Лист 5: Conditional Checks
# ---------------------------------------------------------------------------

def _build_conditional_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    ws = wb.create_sheet("Conditional Checks")
    ws.freeze_panes = "A2"

    headers = [
        ("Документ",   35),
        ("Тип",        15),
        ("Триггер",    22),
        ("Проверка",   30),
        ("Результат",  12),
        ("Severity",   12),
        ("Evidence",   45),
        ("Стр.",        6),
        ("Confidence", 12),
        ("Флаги",      22),
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
        cell.alignment = _CENTER
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
            if crow.severity == "critical":
                ws.cell(row=row_idx, column=col_idx).font = _FONT_WHITE


# ---------------------------------------------------------------------------
# Лист 6: Extracted Values — структурированные значения
# ---------------------------------------------------------------------------

def _build_extracted_values_sheet(wb: Workbook, aggregated: AggregatedResults) -> None:
    ws = wb.create_sheet("Extracted Values")
    ws.freeze_panes = "A2"

    headers = [
        ("Документ",  35),
        ("Тип",       15),
        ("Проверка",  30),
        ("Поле",      20),
        ("Значение",  35),
        ("Формат",    15),
        ("Стр.",       6),
        ("Пункт",     10),
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
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(col)].width = w

    for row_idx, srow in enumerate(aggregated.structured_value_rows, 2):
        for col_idx, field in enumerate(fields, 1):
            value = getattr(srow, field, "")
            if field == "page" and value is None:
                value = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=str(value) if value else "")
            cell.border = _THIN_BORDER
            cell.alignment = _WRAP
