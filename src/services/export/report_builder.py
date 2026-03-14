# src/services/export/report_builder.py

"""
Report Builder — DD Report as Word document.

Sections:
  Title page
  1. Executive Summary        — severity counts + assessment
  2. Critical Findings        — details per critical/high finding
  3. Analysis Quality         — quarantine, degraded, evidence validity
  4. Conditional Checks       — triggered conditional check results (NEW)
  5. Extracted Values         — structured data table (NEW)
  Appendix A: Request List    — with addressee column (NEW)
  Reproducibility footer
"""

import io
from datetime import datetime

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from core.logging import get_logger
from services.export.models import AggregatedResults

logger = get_logger(__name__)

_SEVERITY_COLORS = {
    "critical": RGBColor(0xFF, 0x44, 0x44),
    "high": RGBColor(0xFF, 0x8C, 0x00),
    "medium": RGBColor(0xFF, 0xD7, 0x00),
    "pass": RGBColor(0x00, 0x80, 0x00),
    "unclear": RGBColor(0x80, 0x80, 0x80),
}


def build_report_docx(
    aggregated: AggregatedResults,
    playbook_version: str = "1.0.0",
    playbook_profile: str = "M&A Russia DD",
    environment_hash: str = "",
) -> bytes:
    doc = Document()

    _add_title_page(doc, aggregated, playbook_version, playbook_profile)
    _add_executive_summary(doc, aggregated)
    _add_critical_findings(doc, aggregated)
    _add_quality_section(doc, aggregated)

    # NEW sections
    if aggregated.conditional_rows:
        _add_conditional_checks_section(doc, aggregated)
    if aggregated.structured_value_rows:
        _add_extracted_values_section(doc, aggregated)

    _add_request_list(doc, aggregated)
    _add_footer(doc, aggregated, playbook_version, playbook_profile, environment_hash)

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    logger.info("DD Report Word built")
    return output.read()


def _add_title_page(
    doc: Document,
    agg: AggregatedResults,
    pb_version: str,
    pb_profile: str,
) -> None:
    doc.add_paragraph("")
    doc.add_paragraph("")
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("ОТЧЁТ О ЮРИДИЧЕСКОМ DUE DILIGENCE")
    run.bold = True
    run.font.size = Pt(18)
    doc.add_paragraph("")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run(agg.deal_name).font.size = Pt(14)
    doc.add_paragraph("")
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info.add_run(f"Профиль анализа: {pb_profile}\n").font.size = Pt(11)
    info.add_run(f"Дата: {datetime.now().strftime('%d.%m.%Y')}\n").font.size = Pt(11)
    info.add_run(f"Playbook: v{pb_version}\n").font.size = Pt(11)
    info.add_run(f"Run ID: {agg.run_id[:8]}...").font.size = Pt(9)
    doc.add_page_break()


def _add_executive_summary(doc: Document, agg: AggregatedResults) -> None:
    doc.add_heading("1. Executive Summary", level=1)
    counts = agg.severity_counts
    doc.add_paragraph(
        f"В рамках анализа проверено {agg.total_documents} документов, "
        f"выполнено {agg.total_checks} проверок."
    )
    # NEW: mention conditional checks
    if agg.conditional_checks_triggered > 0:
        doc.add_paragraph(
            f"Выявлены и проверены {agg.conditional_checks_total} условных "
            f"проверок (triggered checks), из которых "
            f"{agg.conditional_checks_triggered} завершились с результатом FAIL."
        )

    table = doc.add_table(rows=6, cols=2)
    table.style = "Light Grid Accent 1"
    cells = [
        ("🔴 Critical", str(counts.critical)),
        ("🟠 High", str(counts.high)),
        ("🟡 Medium", str(counts.medium)),
        ("🟢 Pass", str(counts.pass_count)),
        ("⚪ Unclear", str(counts.unclear)),
        ("Итого", str(counts.total)),
    ]
    for i, (label, value) in enumerate(cells):
        table.cell(i, 0).text = label
        table.cell(i, 1).text = value

    doc.add_paragraph("")
    if counts.critical > 0:
        assessment = (
            f"⚠️ ВЫЯВЛЕНЫ КРИТИЧЕСКИЕ РИСКИ ({counts.critical}). "
            "Рекомендуется немедленная проработка с юридической командой."
        )
    elif counts.high > 0:
        assessment = (
            f"Выявлены существенные риски ({counts.high} high). "
            "Рекомендуется детальный анализ до закрытия сделки."
        )
    else:
        assessment = "Критических и существенных рисков не выявлено."

    p = doc.add_paragraph(assessment)
    if counts.critical > 0:
        p.runs[0].bold = True


def _add_critical_findings(doc: Document, agg: AggregatedResults) -> None:
    doc.add_heading("2. Критические находки", level=1)
    critical_high = [r for r in agg.top_risks if r.severity in ("critical", "high")]

    if not critical_high:
        doc.add_paragraph("Критических и существенных рисков не выявлено.")
        return

    for i, risk in enumerate(critical_high[:15], 1):
        doc.add_heading(
            f"2.{i}. {risk.check_name} ({risk.severity.upper()})",
            level=2,
        )
        doc.add_paragraph(f"Документ: {risk.document_name} ({risk.doc_type})")
        if risk.clause_uid:
            doc.add_paragraph(f"Пункт: {risk.clause_uid}, стр. {risk.page or '—'}")
        if risk.evidence_snippet:
            quote = doc.add_paragraph()
            run = quote.add_run(f"«{risk.evidence_snippet[:300]}»")
            run.italic = True
        # NEW: structured data
        if risk.structured_data:
            sd_text = "; ".join(f"{k}: {v}" for k, v in risk.structured_data.items())
            doc.add_paragraph(f"Извлечённые данные: {sd_text}")
        # NEW: conditional trigger note
        if risk.conditional_check_triggered and risk.trigger_name:
            doc.add_paragraph(f"ℹ️ Проверка активирована триггером: «{risk.trigger_name}»")
        doc.add_paragraph("")


def _add_quality_section(doc: Document, agg: AggregatedResults) -> None:
    doc.add_heading("3. Качество анализа", level=1)
    items = [
        f"Документов в карантине: {agg.quarantine_count}",
        f"Документов с degraded структурой: {agg.degraded_count}",
        f"Evidence validity rate: {agg.evidence_validity_rate:.0%}",
    ]
    for item in items:
        doc.add_paragraph(item, style="List Bullet")
    if agg.quarantine_count > 0:
        doc.add_paragraph(
            "⚠️ Документы в карантине не были проанализированы. "
            "Рекомендуется загрузить текстовые версии для повторного анализа."
        )


def _add_conditional_checks_section(doc: Document, agg: AggregatedResults) -> None:
    """NEW: Section for conditional (triggered) check results."""
    doc.add_heading("4. Условные проверки", level=1)
    doc.add_paragraph(
        "Следующие проверки были активированы автоматически на основании "
        "триггеров, определённых в YAML-инструкциях типов документов "
        "(conditional_checks)."
    )

    fail_cond = [r for r in agg.conditional_rows if r.result == "fail"]
    if not fail_cond:
        doc.add_paragraph("Нарушений по условным проверкам не выявлено.")
        return

    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text = "Документ"
    hdr[1].text = "Триггер"
    hdr[2].text = "Проверка"
    hdr[3].text = "Severity"
    hdr[4].text = "Evidence"

    for cr in fail_cond[:20]:
        row_cells = table.add_row().cells
        row_cells[0].text = cr.document_name
        row_cells[1].text = cr.trigger_name
        row_cells[2].text = cr.check_name
        row_cells[3].text = cr.severity.upper()
        row_cells[4].text = cr.evidence_snippet[:150]


def _add_extracted_values_section(doc: Document, agg: AggregatedResults) -> None:
    """NEW: Section for structured extracted values (amounts, dates, etc.)."""
    doc.add_heading("5. Извлечённые значения", level=1)
    doc.add_paragraph(
        "В ходе анализа из документов были извлечены следующие "
        "структурированные значения (суммы, даты, стороны и пр.)."
    )

    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text = "Документ"
    hdr[1].text = "Тип"
    hdr[2].text = "Поле"
    hdr[3].text = "Значение"
    hdr[4].text = "Пункт"

    for sv in agg.structured_value_rows[:30]:
        row_cells = table.add_row().cells
        row_cells[0].text = sv.document_name
        row_cells[1].text = sv.doc_type
        row_cells[2].text = sv.field_name
        row_cells[3].text = sv.field_value
        row_cells[4].text = sv.clause_uid or (str(sv.page) if sv.page else "")


def _add_request_list(doc: Document, agg: AggregatedResults) -> None:
    doc.add_heading("Приложение A. Список запросов", level=1)
    if not agg.dd_requests:
        doc.add_paragraph("Запросы не сформированы.")
        return

    for i, req in enumerate(agg.dd_requests, 1):
        doc.add_heading(
            f"A.{i}. [{req.priority.upper()}] {req.check_name}",
            level=2,
        )
        # NEW: addressee
        doc.add_paragraph(f"Адресат: {req.addressee}")
        doc.add_paragraph(req.text)
        doc.add_paragraph(f"Документы ({req.document_count}): " + ", ".join(req.document_names[:5]))
        # NEW: structured values referenced
        if req.structured_values:
            sv_text = "; ".join(f"{sv['field']}={sv['value']}" for sv in req.structured_values[:5])
            doc.add_paragraph(f"Связанные значения: {sv_text}")
        doc.add_paragraph("")


def _add_footer(
    doc: Document,
    agg: AggregatedResults,
    pb_version: str,
    pb_profile: str,
    env_hash: str,
) -> None:
    doc.add_paragraph("")
    doc.add_paragraph("—" * 60)
    footer_text = (
        f"Reproducibility: Profile={pb_profile} | "
        f"Playbook v{pb_version} | "
        f"Run {agg.run_id[:12]} | "
        f"Env {env_hash[:12] if env_hash else 'dev'} | "
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    p = doc.add_paragraph(footer_text)
    p.runs[0].font.size = Pt(8)
    p.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)
