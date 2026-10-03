"""
report_sections_v2.py — новая структура DD Report (Big4/Olswang).

Отдельный модуль, чтобы:
- v1 report_builder.py остаётся нетронутым (обратная совместимость);
- v2 — чистый рендерер из FactBundle;
- можно переключаться между v1 и v2 в core.py одной строкой.

Структура:
- Helpers (i18n, humanize, section utilities)
- Title + TOC
- Definitions / Purpose / Terms of Reference
- Executive Summary + Manual Review + Key Findings
- Detailed Report (Landscape) + Extracted Values (Landscape)
- Appendix A/B/C
- build_report_docx_v2 (главная функция)

Источники данных (только FactBundle):
- fact_bundle.meta
- fact_bundle.totals
- fact_bundle.quality
- fact_bundle.conditional
- fact_bundle.global_checks
- fact_bundle.doc_type_checks
- fact_bundle.extracted_values
- fact_bundle.requests
- fact_bundle.documents_reviewed
"""

from __future__ import annotations

import io
import logging
import re
import uuid
from typing import Any

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from engine.checks.result_semantics import get_display_clause_ref
from services.export.fact_bundle import (
    FactBundle,
    GlobalChecksFacts,
    DocTypeChecksFacts,
    DocTypeGroup,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

PLACEHOLDER_DEAL_NAME = "[Deal name not provided]"

# Severity → hex color (для таблиц и badge'ей)
SEVERITY_COLORS_HEX = {
    "critical": "C00000",   # dark red
    "high": "E36C0A",       # orange
    "medium": "FFC000",     # amber
    "low": "92D050",        # green
    "info": "808080",       # gray
    "pass": "92D050",
    "unclear": "A6A6A6",
    "not_applicable": "D9D9D9",
}


# ---------------------------------------------------------------------------
# Helpers — i18n / humanization
# ---------------------------------------------------------------------------

# Enum-значения из check_results → человекочитаемые строки
# (Spec: report.value.*)
_HUMANIZE_MAP: dict[str, dict[str, str]] = {
    "en": {
        "not_applicable": "Not applicable",
        "missing": "Not found",
        "defined": "Defined",
        "no": "No",
        "present": "Present",
        "unclear": "Unclear",
        "pass": "Pass",
        "fail": "Fail",
        "not_defined": "Not defined",
        "clause_missing": "Clause missing",
        "clause_defined": "Clause defined",
        "clause_partially_defined": "Clause partially defined",
        "no_issue_detected": "No issue detected",
        "preamble": "Preamble",
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "info": "Info",
        "missing_required_cla": "Missing required clause",
        "clause_defined": "Clause defined",
        "clause_missing": "Clause missing",
        "clause_partially_defined": "Clause partially defined",
        "no_issue_detected": "No issue detected",
    },
    "ru": {
        "not_applicable": "Не применимо",
        "missing": "Не обнаружено",
        "defined": "Определено",
        "no": "Нет",
        "present": "Присутствует",
        "unclear": "Требует уточнения",
        "pass": "Пройдено",
        "fail": "Не пройдено",
        "not_defined": "Не определено",
        "clause_missing": "Пункт отсутствует",
        "clause_defined": "Пункт определён",
        "clause_partially_defined": "Пункт определён частично",
        "no_issue_detected": "Проблем не обнаружено",
        "preamble": "Преамбула",
        "critical": "Критично",
        "high": "Высокий",
        "medium": "Средний",
        "low": "Низкий",
        "info": "Информация",
        "missing_required_cla": "Отсутствует обязательная клауза",
        "clause_defined": "Клауза определена",
        "clause_missing": "Клауза отсутствует",
        "clause_partially_defined": "Клауза определена частично",
        "no_issue_detected": "Проблем не обнаружено",
    },
}


def _humanize_value(value: str, locale: str = "en") -> str:
    """Превращает enum-значение в human-readable."""
    if not value:
        return ""
    key = str(value).strip().lower()
    mapping = _HUMANIZE_MAP.get(locale, _HUMANIZE_MAP["en"])
    return mapping.get(key, value)


def _humanize_clause(clause_uid: str, locale: str = "en") -> str:
    """Заменяет __preamble__ на 'Preamble' / 'Преамбула'."""
    if not clause_uid:
        return ""
    if "__preamble__" in clause_uid.lower():
        return _humanize_value("preamble", locale)
    return clause_uid


def _is_uuid_like(value: str) -> bool:
    """Проверяет, похожа ли строка на UUID."""
    if not value:
        return False
    return bool(UUID_RE.match(value.strip()))


def _sanitize_deal_name(name: str) -> str:
    """Fallback для deal_name: если UUID — placeholder."""
    if not name:
        return PLACEHOLDER_DEAL_NAME
    if _is_uuid_like(name):
        return PLACEHOLDER_DEAL_NAME
    return name


def _has_cyrillic(value: str) -> bool:
    """Проверяет наличие кириллицы в строке."""
    if not value:
        return False
    return bool(CYRILLIC_RE.search(str(value)))



def _set_first_section_zero_margins(doc: Document) -> None:
    """
    Обнулить поля первой секции (титульная страница).

    Печатная область = весь лист, поэтому картинка шириной
    = page_width встаёт от края до края без отрицательных отступов.

    top_margin оставлен небольшой (0.4") — чтобы STRICTLY PRIVATE
    в header'е не срезалось краем листа.
    bottom_margin минимальный (0.05") — чтобы footer с датой
    визуально лёг на нижнюю часть картинки.
    """
    sec = doc.sections[0]
    sec.left_margin = Inches(0)
    sec.right_margin = Inches(0)
    sec.top_margin = Inches(0.4)
    sec.bottom_margin = Inches(0.05)


def _start_landscape_section(doc: Document) -> None:
    """Начинает новую секцию в Landscape.

    Идемпотентна: если секция уже landscape (width > height) —
    не свапает размеры обратно.
    """
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    if section.page_width < section.page_height:
        section.page_width, section.page_height = (
            section.page_height, section.page_width,
        )
    # Уменьшаем поля для широких таблиц
    section.left_margin = Inches(0.5)
    section.right_margin = Inches(0.5)
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)


def _start_portrait_section(doc: Document) -> None:
    """Начинает новую секцию в Portrait."""
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.PORTRAIT
    if section.page_width > section.page_height:
        section.page_width, section.page_height = (
            section.page_height, section.page_width,
        )
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)


# ---------------------------------------------------------------------------
# Helpers — header / footer
# ---------------------------------------------------------------------------




def _apply_font_to_style(style, font_name: str) -> None:
    """Установить font.name на стиль со всеми rFonts (ascii/hAnsi/cs/eastAsia)."""
    style.font.name = font_name
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), font_name)
    rfonts.set(qn("w:hAnsi"), font_name)
    rfonts.set(qn("w:cs"), font_name)
    rfonts.set(qn("w:eastAsia"), font_name)


def _configure_document_styles(doc: Document) -> None:
    """
    Настроить Word-стили документа под Big4-вид:
    - Normal: Calibri 10.5pt, line 1.15
    - Heading 1: Calibri Light 20pt, #1F3A5F
    - Heading 2: Calibri Light 15pt, #1F3A5F
    - Heading 3: Calibri 12.5pt, #4A4A4A
    - Heading 4: Calibri 11pt, #4A4A4A italic
    - Title: Calibri Light 28pt, #1F3A5F
    """
    BLUE = RGBColor(0x1F, 0x3A, 0x5F)
    GREY = RGBColor(0x4A, 0x4A, 0x4A)

    def _safe(name):
        try:
            return doc.styles[name]
        except KeyError:
            logger.warning("Style not found: %s", name)
            return None

    # Normal
    st = _safe("Normal")
    if st is not None:
        _apply_font_to_style(st, "Calibri")
        st.font.size = Pt(10.5)
        st.paragraph_format.line_spacing = 1.15
        st.paragraph_format.space_after = Pt(6)

    # Heading 1
    st = _safe("Heading 1")
    if st is not None:
        _apply_font_to_style(st, "Calibri Light")
        st.font.size = Pt(20)
        st.font.bold = True
        st.font.color.rgb = BLUE
        st.paragraph_format.space_before = Pt(18)
        st.paragraph_format.space_after = Pt(8)
        st.paragraph_format.keep_with_next = True

    # Heading 2
    st = _safe("Heading 2")
    if st is not None:
        _apply_font_to_style(st, "Calibri Light")
        st.font.size = Pt(15)
        st.font.bold = True
        st.font.color.rgb = BLUE
        st.paragraph_format.space_before = Pt(14)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True

    # Heading 3
    st = _safe("Heading 3")
    if st is not None:
        _apply_font_to_style(st, "Calibri")
        st.font.size = Pt(12.5)
        st.font.bold = True
        st.font.color.rgb = GREY
        st.paragraph_format.space_before = Pt(12)
        st.paragraph_format.space_after = Pt(4)
        st.paragraph_format.keep_with_next = True

    # Heading 4
    st = _safe("Heading 4")
    if st is not None:
        _apply_font_to_style(st, "Calibri")
        st.font.size = Pt(11)
        st.font.bold = False
        st.font.italic = True
        st.font.color.rgb = GREY
        st.paragraph_format.space_before = Pt(10)
        st.paragraph_format.space_after = Pt(4)

    # Title
    st = _safe("Title")
    if st is not None:
        _apply_font_to_style(st, "Calibri Light")
        st.font.size = Pt(28)
        st.font.bold = True
        st.font.color.rgb = BLUE




def _apply_headers_footers(doc: Document, fb: FactBundle) -> None:
    """
    Header / Footer для всех секций.

    Секция 0 (титул):
      - header: 'STRICTLY PRIVATE AND CONFIDENTIAL' (красный, справа)
      - footer: дата (белый, жирный, справа) — ложится на нижнюю часть картинки

    Секции 1+:
      - header: '{deal_name} — Legal Due Diligence Report | {date}'
      - footer: 'Limited Exceptions Only · Strictly Private and Confidential' + 'Page X of Y'
    """
    deal_name = (fb.meta.deal_name or "Confidential").strip()
    generated_at = (fb.meta.generated_at or "")[:10]
    date_str = generated_at if generated_at else ""
    locale = fb.meta.locale or "en"
    title_date = _format_date_for_title(fb.meta.generated_at, fb.meta.locale)

    for idx, section in enumerate(doc.sections):
        try:
            usable = section.page_width - section.left_margin - section.right_margin
            usable_in = usable / 914400.0
        except Exception:
            usable_in = 10.0

        if idx == 0:
            # Титульная секция: обычные header/footer (не first_page — вся секция = титул)
            try:
                section.different_first_page_header_footer = False
            except Exception as e:
                logger.warning("different_first_page не сброшен: %s", e)

            _set_section_header_custom(
                section, "STRICTLY PRIVATE AND CONFIDENTIAL",
                color=RGBColor(0xC0, 0x00, 0x00),
                bold=True, size=11,
            )
            _set_section_footer_custom(
                section, title_date,
                color=RGBColor(0x40, 0x40, 0x40),
                bold=False, size=11,
            )
        else:
            _set_section_header(section, deal_name, date_str, locale)
            _set_section_footer(section, locale, usable_width_in=usable_in)


def _set_first_page_header(section, text: str) -> None:
    """first_page_header: произвольный текст справа (для титула)."""
    hdr = section.first_page_header
    hdr.is_linked_to_previous = False
    p = hdr.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)


def _set_first_page_footer(section, date_str: str) -> None:
    """
    first_page_footer: НЕ используется для титула, т.к. дата выводится
    в теле страницы белым поверх картинки. Оставлено для совместимости.
    """
    return




def _set_section_header_custom(
    section, text: str, color=None, bold: bool = False, size: int = 9,
) -> None:
    """Универсальный header с произвольным текстом, цветом и размером."""
    hdr = section.header
    hdr.is_linked_to_previous = False
    p = hdr.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color


def _set_section_footer_custom(
    section, text: str, color=None, bold: bool = False, size: int = 9,
) -> None:
    """Универсальный footer с произвольным текстом, цветом и размером."""
    ftr = section.footer
    ftr.is_linked_to_previous = False
    p = ftr.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color


def _set_section_header(
    section,
    deal_name: str,
    date_str: str,
    locale: str = "en",
) -> None:
    """Header секции: '{deal_name} — Legal Due Diligence Report | {date}'."""
    header = section.header
    header.is_linked_to_previous = False
    p = header.paragraphs[0]
    p.text = ""
    run = p.add_run(f"{deal_name} — Legal Due Diligence Report | {date_str}")
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    # Тонкая линия под header'ом
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "BFBFBF")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _set_section_footer(
    section,
    locale: str = "en",
    usable_width_in: float = 10.0,
) -> None:
    """
    Footer секции:
      слева: 'Limited Exceptions Only · Strictly Private and Confidential'
      справа: 'Page X of Y'
    """
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0]
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Правый tab stop на границе доступной ширины
    p.paragraph_format.tab_stops.add_tab_stop(
        Inches(usable_width_in), WD_TAB_ALIGNMENT.RIGHT,
    )

    left_text = (
        "Limited Exceptions Only · Strictly Private and Confidential"
    )
    run = p.add_run(left_text + "\t")
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

    run = p.add_run("Page ")
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
    _append_field(p, "PAGE")
    run = p.add_run(" of ")
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)
    _append_field(p, "NUMPAGES")

    # Все runs PAGE/NUMPAGES — тоже серые 8.5pt (после вставки поля)
    for r in p.runs:
        if r.font.size is None:
            r.font.size = Pt(8.5)
        if r.font.color.rgb is None:
            r.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

    # Тонкая линия над footer'ом
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    top = OxmlElement("w:top")
    top.set(qn("w:val"), "single")
    top.set(qn("w:sz"), "4")
    top.set(qn("w:space"), "4")
    top.set(qn("w:color"), "BFBFBF")
    pBdr.append(top)
    pPr.append(pBdr)


def _append_field(paragraph, field_code: str) -> None:
    """Вставляет поле Word (PAGE / NUMPAGES / TOC / ...) в параграф."""
    run = paragraph.add_run()
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = field_code
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)


# ---------------------------------------------------------------------------
# Helpers — tables
# ---------------------------------------------------------------------------




def _set_table_header_repeat(table) -> None:
    """
    Пометить первую строку таблицы как повторяющуюся шапку.

    Word будет повторять её на каждой новой странице, куда попадает
    таблица. Критично для длинных таблиц (4.1, 4.2, 5.x, Appendix A).

    См. w:tblHeader в OOXML.
    """
    if not table.rows:
        return
    first_row = table.rows[0]
    tr = first_row._tr
    trPr = tr.get_or_add_trPr()
    # Убираем старый, если есть (идемпотентно)
    for old_el in trPr.findall(qn("w:tblHeader")):
        trPr.remove(old_el)
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def _style_table_header(table) -> None:
    """Полужирный шрифт в первой строке таблицы."""
    for cell in table.rows[0].cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.bold = True



def _set_table_widths(table, widths_in: list) -> None:
    """
    Явно задать ширины колонок таблицы.

    python-docx сам по себе table.columns[i].width часто игнорирует —
    нужно устанавливать width на уровне каждой ячейки. Этот helper
    инкапсулирует правильный паттерн.

    Args:
        table: docx Table.
        widths_in: список docx.shared.Inches, длина = число колонок.
    """
    if not widths_in:
        return
    table.autofit = False
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths_in):
                cell.width = widths_in[i]

def _safe_text(value: Any, max_len: int = 500) -> str:
    """Обрезает слишком длинный текст для ячейки таблицы."""
    if value is None:
        return ""
    s = str(value).strip()
    if len(s) > max_len:
        return s[:max_len] + "…"
    return s


# ---------------------------------------------------------------------------
# SECTION: Title page
# ---------------------------------------------------------------------------




# Путь к центральной картинке титульной страницы.
# Указывается относительно рабочей директории процесса (/srv/steloom-dev).
_TITLE_IMAGE_PATH = "frontend/public/ia-1-2.png"
_TITLE_IMAGE_WIDTH_IN = 8.5  # full page width


def _add_title_image(doc: Document) -> None:
    """
    Картинка титула — во всю ширину печатной области.

    Так как первая секция имеет margin=0, ширина печатной области
    равна ширине листа. Картинка ложится от края до края листа.
    """
    from pathlib import Path as _P
    img = _P(_TITLE_IMAGE_PATH)
    if not img.exists():
        logger.warning("Title image not found: %s", _TITLE_IMAGE_PATH)
        return
    try:
        sec = doc.sections[0]
        available_emu = sec.page_width - sec.left_margin - sec.right_margin

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(24)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0  # 1.0 = одинарный интервал (множитель, не пункты!)

        run = p.add_run()
        run.add_picture(_TITLE_IMAGE_PATH, width=available_emu)
    except Exception as exc:
        logger.warning("Title image failed: %s", exc)


def _add_title_page_v2(doc: Document, fb: FactBundle) -> None:
    """
    Титульная страница — только заголовок.

    - LIMITED EXCEPTIONS ONLY / LEGAL DUE DILIGENCE REPORT
    - Слева
    - По вертикали — в центре высоты печатной области

    Confidential и дата размещаются в header / footer секции 0
    через _apply_headers_footers().
    """
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    # Центр высоты: 4.5" от top_margin (usable 9") минус половина
    # высоты заголовка (~0.4") = ~4.1" = ~295pt
    title.paragraph_format.space_before = Pt(290)
    title.paragraph_format.space_after = Pt(0)
    title.paragraph_format.line_spacing = 1.15

    run = title.add_run("LIMITED EXCEPTIONS ONLY\nLEGAL DUE DILIGENCE REPORT")
    run.bold = True
    run.font.size = Pt(26)
    run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)


def _format_date(iso_date: str) -> str:
    """ISO → '01 October 2026'."""
    if not iso_date:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%d %B %Y")
    except Exception:
        return iso_date[:10]


def _format_date_for_title(iso_date: str, locale: str) -> str:
    """
    Форматирует дату для титульной страницы в Big4-стиле.

    RU: "2 октября 2026 г."
    EN: "2 October 2026"
    """
    if not iso_date:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except Exception:
        return iso_date[:10]

    if locale and locale.startswith("ru"):
        months_ru = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        ]
        return f"{dt.day} {months_ru[dt.month - 1]} {dt.year} г."

    return f"{dt.day} {dt.strftime('%B')} {dt.year}"

_FIELD_NAME_OVERRIDES = {
    "dopog_documents_mentioned": {"ru": "ДОПОГ документы упомянуты", "en": "ADN/ADR documents mentioned"},
    "special_permit_mentioned": {"ru": "Спецразрешение упомянуто", "en": "Special permit mentioned"},
    "personal_data_regulation_level": {"ru": "Уровень регулирования ПДн", "en": "Personal data regulation level"},
    "personal_data_display": {"ru": "ПДн (описание)", "en": "Personal data (display)"},
    "personal_data_status": {"ru": "Статус ПДн", "en": "Personal data status"},
    "confidentiality_term_regime": {"ru": "Режим срока конфиденциальности", "en": "Confidentiality term regime"},
    "confidentiality_term_value": {"ru": "Срок конфиденциальности", "en": "Confidentiality term value"},
    "confidentiality_term_display": {"ru": "Срок конфиденциальности (описание)", "en": "Confidentiality term (display)"},
    "confidentiality_status": {"ru": "Статус конфиденциальности", "en": "Confidentiality status"},
    "confidentiality_display": {"ru": "Конфиденциальность (описание)", "en": "Confidentiality (display)"},
}


def _humanize_field_name(name: str, locale: str) -> str:
    """snake_case → человекочитаемое название поля ('who_prepares' → 'Who prepares')."""
    if not name:
        return ""
    key = name.strip()
    override = _FIELD_NAME_OVERRIDES.get(key)
    if override:
        return override.get("ru" if locale and locale.startswith("ru") else "en", key)
    parts = key.replace("_", " ").strip()
    if not parts:
        return key
    return parts[0].upper() + parts[1:]


_EXTRACTED_VALUE_MAP = {
    "missing": ("Не указано", "Not specified"),
    "not_specified": ("Не указано", "Not specified"),
    "not_defined": ("Не определено", "Not defined"),
    "not_found": ("Не найдено", "Not found"),
    "yes": ("Да", "Yes"),
    "no": ("Нет", "No"),
    "true": ("Да", "Yes"),
    "false": ("Нет", "No"),
    "statutory": ("В силу закона", "Statutory"),
    "consignment_note": ("Товарно-транспортная накладная", "Consignment note"),
    "shipper": ("Грузоотправитель", "Shipper"),
    "carrier": ("Перевозчик", "Carrier"),
    "not_applicable": ("Не применимо", "Not applicable"),
}


def _humanize_extracted_value(value: str, locale: str) -> str:
    """Код значения → человекочитаемое ('missing' → 'Не указано')."""
    if not value:
        return ""
    key = value.strip().lower()
    pair = _EXTRACTED_VALUE_MAP.get(key)
    if pair:
        return pair[0] if locale and locale.startswith("ru") else pair[1]
    return value


def _humanize_source(source: str, locale: str) -> str:
    """Source: llm / rule / none / manual."""
    if not source:
        return ""
    s = source.strip().lower()
    ru_map = {"llm": "LLM", "rule": "Правило", "none": "—", "manual": "Вручную", "qc": "QC"}
    en_map = {"llm": "LLM", "rule": "Rule", "none": "—", "manual": "Manual", "qc": "QC"}
    return (ru_map if locale and locale.startswith("ru") else en_map).get(s, source)


def _humanize_language(lang: str, locale: str) -> str:
    """
    Код языка → человекочитаемое название.

    RU: 'ru' → 'Русский', 'en' → 'Английский'
    EN: 'ru' → 'Russian', 'en' → 'English'
    """
    if not lang:
        return ""
    code = lang.strip().lower()[:2]
    ru_map = {"ru": "Русский", "en": "Английский", "de": "Немецкий", "fr": "Французский"}
    en_map = {"ru": "Russian", "en": "English", "de": "German", "fr": "French"}
    if locale and locale.startswith("ru"):
        return ru_map.get(code, lang)
    return en_map.get(code, lang)

# ---------------------------------------------------------------------------
# SECTION: TOC
# ---------------------------------------------------------------------------




def _enable_update_fields_on_open(doc: Document) -> None:
    """
    Включить обновление полей (включая TOC) при открытии документа Word.

    Добавляет <w:updateFields w:val="true"/> в word/settings.xml.
    Word при открытии покажет диалог «Обновить поля?» — после «Да»
    TOC и другие поля (page numbers) обновятся автоматически.

    Это стандартный OOXML-механизм, работает во всех версиях Word.
    """
    settings = doc.settings.element
    # Убираем старый, если есть (идемпотентно)
    for el in settings.findall(qn("w:updateFields")):
        settings.remove(el)
    update_fields = OxmlElement("w:updateFields")
    update_fields.set(qn("w:val"), "true")
    settings.append(update_fields)


def _add_toc(doc: Document) -> None:
    """Добавляет автообновляемое поле TOC."""
    doc.add_heading("Table of Contents", level=1)
    p = doc.add_paragraph()
    run = p.add_run()

    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = 'TOC \\o "1-1" \\h \\z \\u'
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = (
        "Right-click and choose 'Update Field' to build the table of contents."
    )
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")

    for el in (fldChar1, instrText, fldChar2, placeholder, fldChar3):
        run._r.append(el)


# ---------------------------------------------------------------------------
# SECTION: Definitions
# ---------------------------------------------------------------------------


def _add_definitions(doc: Document, fb: FactBundle) -> None:
    """Definitions (заглушка для M&A Russia DD)."""
    doc.add_heading("6. Definitions", level=1)

    meta = fb.meta
    deal_name = _sanitize_deal_name(meta.deal_name)
    buyer = meta.buyer_name or "the Buyer"
    target = meta.target_name or deal_name
    seller = meta.seller_name or "the Seller"

    definitions = [
        ("Acquisition", "the proposed acquisition of the Company by the Buyer."),
        ("Buyer", buyer),
        ("Company", target),
        ("Completion", "completion of the Acquisition pursuant to the terms of the SPA."),
        ("Data Room", "the electronic data site created for the purposes of the Acquisition."),
        ("Group", "the Company and each of its Subsidiaries."),
        ("Report", "this 'exceptions only' legal due diligence report."),
        ("Seller", seller),
        ("SPA", "the share purchase agreement to be entered into between the Seller and the Buyer."),
    ]

    for term, definition in definitions:
        p = doc.add_paragraph()
        run = p.add_run(f'"{term}" ')
        run.bold = True
        p.add_run(f"means {definition}")


# ---------------------------------------------------------------------------
# SECTION: Purpose of Report
# ---------------------------------------------------------------------------


def _add_purpose(doc: Document, fb: FactBundle, narratives: dict | None) -> None:
    """Purpose of Report — LLM narrative или fallback."""
    doc.add_heading("1. Purpose of Report", level=1)

    # Если есть LLM narrative — используем его
    if narratives and narratives.get("purpose_of_report"):
        doc.add_paragraph(narratives["purpose_of_report"])
        return

    # Fallback: шаблонный текст
    totals = fb.totals
    doc_count = totals.get("documents", 0)
    checks = totals.get("checks_planned", 0)
    global_count = len(fb.global_checks.by_check)
    doc_type_count = sum(
        len(g.by_check) for g in fb.doc_type_checks.by_doc_type.values()
    )
    doc_type_groups = len(fb.doc_type_checks.by_doc_type)

    text = (
        f"This Report summarises the results of our legal due diligence exercise "
        f"on an \u201cexceptions only\u201d basis. We reviewed {doc_count} document(s) "
        f"and performed {checks} check(s) ({global_count} global + {doc_type_count} "
        f"document-type across {doc_type_groups} type(s)). The Report highlights "
        f"only material issues which we believe should be drawn to the Buyer's "
        f"attention, either because we recommend a provision in the SPA or because "
        f"we recommend certain action by the parties prior to, on, or after Completion."
    )
    doc.add_paragraph(text)


# ---------------------------------------------------------------------------
# SECTION: Terms of Reference
# ---------------------------------------------------------------------------


def _add_terms_of_reference(doc: Document, fb: FactBundle, narratives: dict | None) -> None:
    """Terms of Reference: Scope / Exclusions / Limitations / Assumptions."""
    doc.add_heading("2. Terms of Reference", level=1)

    meta = fb.meta
    quality = fb.quality

    # 3.1. Scope
    doc.add_heading("2.1. Scope", level=2)
    scope_text = (
        f"Our review was limited to matters covered by the "
        f"\u201c{meta.playbook_profile}\u201d playbook, as applied to the documents "
        f"provided in the Data Room. The review was performed in "
        f"\u201c{meta.checks_mode or 'standard'}\u201d mode."
    )
    doc.add_paragraph(scope_text)

    # 3.2. Exclusions
    doc.add_heading("2.2. Exclusions", level=2)
    if meta.excluded_areas:
        exclusions_text = (
            "We did not review the following matters: "
            + ", ".join(meta.excluded_areas)
            + "."
        )
    else:
        exclusions_text = "No specific exclusions were documented for this review."
    doc.add_paragraph(exclusions_text)

    # 3.3. Limitations
    doc.add_heading("2.3. Limitations", level=2)
    limitations = list(meta.limitations)
    if quality.get("low_confidence_count", 0) > 0:
        limitations.append(
            f"{quality['low_confidence_count']} finding(s) were extracted with low confidence "
            f"(< 0.6) and require manual verification."
        )
    if quality.get("needs_manual_review_count", 0) > 0:
        limitations.append(
            f"{quality['needs_manual_review_count']} finding(s) are flagged for manual review."
        )
    for lim in limitations:
        doc.add_paragraph(lim, style="List Bullet")

    # 3.4. Assumptions
    doc.add_heading("2.4. Assumptions", level=2)
    for a in meta.assumptions:
        doc.add_paragraph(a, style="List Bullet")


# ---------------------------------------------------------------------------
# SECTION: Executive Summary (Overall)
# ---------------------------------------------------------------------------


def _add_overall_summary(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    Executive Summary:
    - LLM narrative (если есть) или fallback template
    - Severity summary table
    - Assessment sentence
    """
    doc.add_heading("3. Key Findings / Executive Summary", level=1)
    doc.add_heading("3.1. Overall Summary", level=2)

    totals = fb.totals
    quality = fb.quality

    # LLM narrative или fallback
    if narratives and narratives.get("overall_summary"):
        doc.add_paragraph(narratives["overall_summary"])
    else:
        doc_count = totals.get("documents", 0)
        checks = totals.get("checks_planned", 0)
        critical = totals.get("critical", 0)
        high = totals.get("high", 0)
        medium = totals.get("medium", 0)
        unclear = totals.get("unclear", 0)

        global_count = len(fb.global_checks.by_check)
        doc_type_count = sum(
            len(g.by_check) for g in fb.doc_type_checks.by_doc_type.values()
        )

        text = (
            f"We reviewed {doc_count} document(s) and performed {checks} check(s) "
            f"({global_count} global + {doc_type_count} document-type). "
        )
        if critical > 0:
            text += (
                f"{critical} critical-risk issue(s) and {high} high-risk issue(s) "
                f"were identified. "
            )
        elif high > 0:
            text += f"{high} high-risk issue(s) were identified. "
        elif medium > 0:
            text += (
                f"No critical or high-risk issues were identified; {medium} "
                f"medium-risk issue(s) were noted. "
            )
        else:
            text += "No critical, high, or medium-risk issues were identified. "

        if unclear > 0:
            text += (
                f"{unclear} check(s) require manual review "
                f"(see Section 4.2). "
            )

        text += (
            "The analysis is based on the documents available in the Data Room "
            "as at the Report date."
        )
        doc.add_paragraph(text)

    # Severity summary table
    doc.add_paragraph("")
    rows = [
        ("Critical", totals.get("critical", 0), "🔴"),
        ("High", totals.get("high", 0), "🟠"),
        ("Medium", totals.get("medium", 0), "🟡"),
        ("Pass", totals.get("pass", 0), "🟢"),
        ("Unclear (manual review)", totals.get("unclear", 0), "⚪"),
        ("Not applicable", totals.get("checks_not_applicable", 0), "—"),
        ("Total", totals.get("checks_planned", 0), ""),
    ]
    table = doc.add_table(rows=len(rows) + 1, cols=3)
    table.style = "Light Grid Accent 1"

    header = table.rows[0].cells
    header[0].text = ""
    header[1].text = "Category"
    header[2].text = "Count"

    for i, (label, value, icon) in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = icon
        cells[1].text = label
        cells[2].text = str(value)

    _style_table_header(table)
    _set_table_header_repeat(table)

    # Assessment sentence
    doc.add_paragraph("")
    critical = totals.get("critical", 0)
    high = totals.get("high", 0)

    if critical > 0:
        text = (
            f"The overall risk profile is elevated: {critical} critical-risk "
            f"finding(s) were identified."
        )
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    elif high > 0:
        text = f"{high} high-risk finding(s) were identified."
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = True
        run.font.color.rgb = RGBColor(0xE3, 0x6C, 0x0A)
    else:
        doc.add_paragraph(
            "No critical or high-risk findings were identified in this review."
        )


# ---------------------------------------------------------------------------
# SECTION: Items Requiring Manual Review (unclear checks)
# ---------------------------------------------------------------------------


def _add_manual_review_section(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    4.2. Items Requiring Manual Review — все checks со статусом unclear.
    """
    # Собираем все unclear checks из global + doc-type
    unclear_rows: list[dict] = []
    for cr in fb.global_checks.rows:
        if cr.get("result") == "unclear":
            unclear_rows.append({**cr, "_scope": "global"})
    for grp in fb.doc_type_checks.by_doc_type.values():
        for cr in grp.rows:
            if cr.get("result") == "unclear":
                unclear_rows.append({**cr, "_scope": "doc_type"})

    if not unclear_rows:
        return  # не выводим раздел, если нечего показывать

    doc.add_heading("4.2. Items Requiring Manual Review", level=2)

    # LLM narrative или fallback
    if narratives and narratives.get("manual_review"):
        doc.add_paragraph(narratives["manual_review"])
    else:
        text = (
            f"The following {len(unclear_rows)} check(s) returned an "
            f"\u201cunclear\u201d result and require manual review by a qualified "
            f"lawyer. These items are not necessarily risks; they indicate that "
            f"the automated analysis could not determine a definitive outcome "
            f"from the available evidence."
        )
        doc.add_paragraph(text)

    doc.add_paragraph("")

    # Таблица
    table = doc.add_table(rows=len(unclear_rows) + 1, cols=5)
    table.style = "Light Grid Accent 1"

    header = table.rows[0].cells
    header[0].text = "Check"
    header[1].text = "Document"
    header[2].text = "Severity"
    header[3].text = "Reason"
    header[4].text = "Clause"

    for i, cr in enumerate(unclear_rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = _safe_text(cr.get("check_name", ""), 80)
        cells[1].text = _safe_text(cr.get("_document_name", ""), 80)
        cells[2].text = _humanize_value(cr.get("severity", "medium"))
        cells[3].text = _safe_text(
            cr.get("review_message") or cr.get("display_text", ""),
            150,
        )
        cells[4].text = _humanize_clause(cr.get("clause_uid", ""))

    _style_table_header(table)
    _set_table_header_repeat(table)


# ---------------------------------------------------------------------------
# SECTION: Key Findings — Global Checks
# ---------------------------------------------------------------------------


def _add_key_findings_global(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    3.2. Global Checks Summary — текстом, без таблицы.
    """
    doc.add_heading("3.2. Global Checks Summary", level=2)

    gc = fb.global_checks
    if not gc.by_check:
        doc.add_paragraph("No global checks were performed in this review.")
        return

    # LLM narrative — если есть
    if narratives and narratives.get("global_summary"):
        doc.add_paragraph(narratives["global_summary"])
        return

    # Fallback: текстовое summary
    total_checks = len(gc.by_check)
    total_issues = sum(s.issues for s in gc.by_check.values())

    checks_with_issues = sorted(
        [s for s in gc.by_check.values() if s.issues > 0],
        key=lambda x: (-x.critical, -x.high, -x.medium, x.check_name),
    )
    checks_passed = sorted(
        [s for s in gc.by_check.values() if s.issues == 0],
        key=lambda x: x.check_name,
    )

    # Вводный абзац
    intro = (
        f"{total_checks} global check(s) were applied across all documents. "
    )
    if total_issues == 0:
        intro += "No material issues were identified."
    else:
        intro += f"{total_issues} issue(s) were identified."
    doc.add_paragraph(intro)

    # Блок с issues
    if checks_with_issues:
        doc.add_paragraph("")
        p = doc.add_paragraph()
        run = p.add_run("Issues identified:")
        run.bold = True

        for s in checks_with_issues:
            # Определяем top severity
            if s.critical > 0:
                sev_label = "Critical"
            elif s.high > 0:
                sev_label = "High"
            else:
                sev_label = "Medium"

            affected = ", ".join(s.affected_documents[:3])
            if len(s.affected_documents) > 3:
                affected += f" (+{len(s.affected_documents) - 3} more)"

            line = (
                f"  \u2022 {s.check_name} \u2014 {s.issues} issue(s), "
                f"top severity: {sev_label}. "
                f"Affected documents: {affected}."
            )
            doc.add_paragraph(line)

    # Блок с passed
    if checks_passed:
        doc.add_paragraph("")
        p = doc.add_paragraph()
        run = p.add_run("Checks passed without findings:")
        run.bold = True

        names = ", ".join(s.check_name for s in checks_passed)
        doc.add_paragraph(f"  {names}.")


# ---------------------------------------------------------------------------
# SECTION: Key Findings — Document-Type Checks
# ---------------------------------------------------------------------------


def _add_key_findings_doctype(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    3.3. Document-Type Checks Summary — текстом по каждому типу, без таблицы.
    """
    dtc = fb.doc_type_checks
    if not dtc.by_doc_type:
        return

    doc.add_heading("3.3. Document-Type Checks Summary", level=2)

    # LLM narrative — если есть
    if narratives and narratives.get("doc_type_summary"):
        doc.add_paragraph(narratives["doc_type_summary"])
        return

    # Fallback: текстовое summary по каждому doc_type
    total_checks = sum(len(g.by_check) for g in dtc.by_doc_type.values())
    total_issues = sum(
        s.issues for g in dtc.by_doc_type.values() for s in g.by_check.values()
    )
    groups = len(dtc.by_doc_type)

    intro = (
        f"{total_checks} document-type check(s) were applied across "
        f"{groups} document type(s). "
    )
    if total_issues == 0:
        intro += "No material issues were identified."
    else:
        intro += f"{total_issues} issue(s) were identified."
    doc.add_paragraph(intro)

    # По каждому doc_type
    for doc_type, grp in sorted(
        dtc.by_doc_type.items(),
        key=lambda x: -(sum(
            s.critical * 100 + s.high * 10 + s.medium
            for s in x[1].by_check.values()
        )),
    ):
        doc.add_paragraph("")

        # Заголовок doc_type — с кодом, без humanized label (по решению)
        p = doc.add_paragraph()
        run = p.add_run(f"{doc_type} ({len(grp.documents)} document(s)):")
        run.bold = True

        checks_with_issues = sorted(
            [s for s in grp.by_check.values() if s.issues > 0],
            key=lambda x: (-x.critical, -x.high, -x.medium, x.check_name),
        )
        checks_passed = [
            s for s in grp.by_check.values() if s.issues == 0
        ]

        if checks_with_issues:
            for s in checks_with_issues:
                if s.critical > 0:
                    sev_label = "Critical"
                elif s.high > 0:
                    sev_label = "High"
                else:
                    sev_label = "Medium"

                line = (
                    f"  \u2022 {s.check_name} \u2014 {s.issues} issue(s), "
                    f"top severity: {sev_label}."
                )
                doc.add_paragraph(line)
        else:
            doc.add_paragraph("  No material issues identified.")

        if checks_passed:
            passed_count = len(checks_passed)
            doc.add_paragraph(
                f"  Checks passed without findings: {passed_count}."
            )

# ---------------------------------------------------------------------------
# SECTION: Detailed Report — Global Checks (Landscape)
# ---------------------------------------------------------------------------


def _add_detailed_report_global(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    4.1 Global Checks — Landscape таблица.
    Columns: Check | Document | Result | Severity | Clause | Comments
    """
    doc.add_heading("4. Detailed Report", level=1)
    doc.add_heading("4.1. Global Checks", level=2)

    gc = fb.global_checks
    if not gc.rows:
        doc.add_paragraph("No global checks were performed in this review.")
        return

    sorted_rows = sorted(
        gc.rows,
        key=lambda r: (
            0 if _is_issue_row(r) else 1,
            {"critical": 0, "high": 1, "medium": 2}.get(r.get("severity", "medium"), 9),
        ),
    )

    table = doc.add_table(rows=len(sorted_rows) + 1, cols=6)
    table.style = "Light Grid Accent 1"
    _set_table_widths(table, [
        Inches(1.6), Inches(1.7), Inches(1.0),
        Inches(0.8), Inches(1.4), Inches(3.5),
    ])

    header = table.rows[0].cells
    header[0].text = "Check"
    header[1].text = "Document"
    header[2].text = "Result"
    header[3].text = "Severity"
    header[4].text = "Clause"
    header[5].text = "Comments"

    for i, cr in enumerate(sorted_rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = _safe_text(cr.get("check_name", ""), 60)
        cells[1].text = _safe_text(cr.get("_document_name", ""), 50)
        cells[2].text = _humanize_value(cr.get("result", ""), fb.meta.locale)
        cells[3].text = _humanize_value(cr.get("severity", ""), fb.meta.locale)
        _clause = get_display_clause_ref(
            cr.get("result", ""), cr.get("clause_uid", "")
        )
        cells[4].text = _humanize_clause(_clause, fb.meta.locale)
        cells[5].text = _safe_text(
            cr.get("review_message") or cr.get("display_text", ""),
            350,
        )

    _style_table_header(table)
    _set_table_header_repeat(table)


def _is_issue_row(row: dict) -> bool:
    """Локальный helper для сортировки."""
    rv = (row.get("result") or "").lower().strip()
    if not rv:
        return False
    return rv not in ("pass", "unclear", "not_applicable",
                      "clause_defined", "no_issue_detected",
                      "present", "defined", "no")


# ---------------------------------------------------------------------------
# SECTION: Detailed Report — Document-Type Checks (Landscape)
# ---------------------------------------------------------------------------


def _add_detailed_report_doctype(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    4.2 Document-Type Checks — для каждого doc_type отдельная Landscape-таблица.
    Columns: Check | Document | Result | Severity | Clause | Comments
    """
    doc.add_heading("4.2. Document-Type Checks", level=2)

    dtc = fb.doc_type_checks
    if not dtc.by_doc_type:
        doc.add_paragraph("No document-type checks were performed in this review.")
        return

    for idx, (doc_type, grp) in enumerate(sorted(
        dtc.by_doc_type.items(),
        key=lambda x: -(sum(
            s.critical * 100 + s.high * 10 + s.medium
            for s in x[1].by_check.values()
        )),
    ), start=1):
        doc.add_paragraph("")
        # Заголовок с кодом doc_type
        doc.add_heading(f"4.2.{idx}. {doc_type}", level=3)

        if not grp.rows:
            doc.add_paragraph("No checks applied to this document type.")
            continue

        sorted_rows = sorted(
            grp.rows,
            key=lambda r: (
                0 if _is_issue_row(r) else 1,
                {"critical": 0, "high": 1, "medium": 2}.get(r.get("severity", "medium"), 9),
            ),
        )

        table = doc.add_table(rows=len(sorted_rows) + 1, cols=6)
        table.style = "Light Grid Accent 1"
        _set_table_widths(table, [
            Inches(1.6), Inches(1.7), Inches(1.0),
            Inches(0.8), Inches(1.4), Inches(3.5),
        ])

        header = table.rows[0].cells
        header[0].text = "Check"
        header[1].text = "Document"
        header[2].text = "Result"
        header[3].text = "Severity"
        header[4].text = "Clause"
        header[5].text = "Comments"

        for i, cr in enumerate(sorted_rows, start=1):
            cells = table.rows[i].cells
            cells[0].text = _safe_text(cr.get("check_name", ""), 60)
            cells[1].text = _safe_text(cr.get("_document_name", ""), 50)
            cells[2].text = _humanize_value(cr.get("result", ""), fb.meta.locale)
            cells[3].text = _humanize_value(cr.get("severity", ""), fb.meta.locale)
            _clause = get_display_clause_ref(
                cr.get("result", ""), cr.get("clause_uid", "")
            )
            cells[4].text = _humanize_clause(_clause, fb.meta.locale)
            cells[5].text = _safe_text(
                cr.get("review_message") or cr.get("display_text", ""),
                350,
            )

        _style_table_header(table)
        _set_table_header_repeat(table)

# ---------------------------------------------------------------------------
# SECTION: Extracted Values (Landscape)
# ---------------------------------------------------------------------------


def _add_extracted_values_landscape(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    5. Extracted Values — Landscape таблица.
    Разделена на три подтаблицы:
      5.1 Identified Values  — конкретные значения полей
      5.2 Negative Findings  — задокументированное отсутствие данных
      5.3 Diagnostic Notes   — reason-пояснения (presentation=diagnostic)

    Группировка по документу — симметрично с 4.2 Document-Type Checks.
    Колонка Document не дублируется: она вынесена в подзаголовок.
    """
    doc.add_heading("5. Extracted Values", level=1)

    ev = fb.extracted_values
    if not ev:
        doc.add_paragraph(
            "No structured values were extracted from the reviewed documents."
        )
        return

    locale = fb.meta.locale

    if narratives and narratives.get("extracted_values"):
        doc.add_paragraph(narratives["extracted_values"])
    else:
        doc_count = len({r["document_id"] for r in ev})
        if locale and locale.startswith("ru"):
            doc.add_paragraph(
                f"В ходе анализа извлечено {len(ev)} значений из "
                f"{doc_count} документ(ов)."
            )
        else:
            doc.add_paragraph(
                f"During the analysis, {len(ev)} structured value(s) were "
                f"extracted from {doc_count} document(s)."
            )

    identified = [
        r for r in ev
        if not r.get("is_negative") and not r.get("is_diagnostic")
    ]
    negative = [r for r in ev if r.get("is_negative")]
    diagnostic = [r for r in ev if r.get("is_diagnostic")]

    if identified:
        _render_extracted_section(
            doc, "5.1", "Identified Values", identified, locale,
        )
    if negative:
        _render_extracted_section(
            doc, "5.2", "Negative Findings", negative, locale,
        )
    if diagnostic:
        _render_extracted_section(
            doc, "5.3", "Diagnostic Notes", diagnostic, locale,
        )


def _render_extracted_section(
    doc: Document,
    section_number: str,
    title: str,
    rows: list[dict],
    locale: str,
) -> None:
    """
    Один подраздел раздела 5 с группировкой по документу.

    Симметрично с 4.2 Document-Type Checks: для каждого документа —
    heading(level=3) + landscape-таблица без колонки Document.
    """
    doc.add_heading(f"{section_number} {title}", level=2)

    # Группировка по документу, порядок — по имени (детерминированно)
    by_doc: dict[str, list[dict]] = {}
    for r in rows:
        key = r.get("document_id") or ""
        by_doc.setdefault(key, []).append(r)

    for idx, (doc_id, doc_rows) in enumerate(
        sorted(by_doc.items(), key=lambda kv: (kv[1][0].get("document_name") or "").lower()),
        start=1,
    ):
        doc_name = doc_rows[0].get("document_name") or doc_id
        doc.add_paragraph("")
        doc.add_heading(f"{section_number}.{idx}. {doc_name}", level=3)
        _render_extracted_table(doc, doc_rows, locale)


def _render_extracted_table(
    doc: Document,
    rows: list[dict],
    locale: str,
) -> None:
    """
    Таблица одной группы Extracted Values.
    Columns: Check | Field | Value | Page / Clause
    Стиль и структура — как в 4.1/4.2 (Light Grid Accent 1, без хардкода ширин).
    """
    table = doc.add_table(rows=len(rows) + 1, cols=4)
    table.style = "Light Grid Accent 1"
    _set_table_widths(table, [
        Inches(2.4), Inches(2.1), Inches(4.0), Inches(1.5),
    ])

    header = table.rows[0].cells
    header[0].text = "Check"
    header[1].text = "Field"
    header[2].text = "Value"
    header[3].text = "Page / Clause"

    prev_check = None

    for i, row in enumerate(rows, start=1):
        cells = table.rows[i].cells

        check_name = row.get("check_name", "") or ""
        if check_name != prev_check:
            cells[0].text = _safe_text(check_name, 60)
            prev_check = check_name
        else:
            cells[0].text = ""

        field_label = row.get("field_label") or _humanize_field_name(
            row.get("field_name", ""), locale
        )
        cells[1].text = _safe_text(field_label, 40)

        value_raw = str(row.get("field_value", "") or "")
        value_h = _humanize_extracted_value(value_raw, locale)
        cells[2].text = _safe_text(value_h, 400)

        page = row.get("page")
        clause = row.get("clause_ref") or row.get("clause_uid") or ""
        loc_parts = []
        if page:
            loc_parts.append(f"p. {page}")
        if clause:
            loc_parts.append(str(clause))
        cells[3].text = _safe_text(" / ".join(loc_parts), 60)

    _style_table_header(table)
    _set_table_header_repeat(table)


# ---------------------------------------------------------------------------
# SECTION: Appendix A. Request List (Landscape)
# ---------------------------------------------------------------------------


def _add_appendix_requests(
    doc: Document,
    fb: FactBundle,
    narratives: dict | None,
) -> None:
    """
    Appendix A. Request List — Landscape таблица.
    Columns: # | Priority | Check | Text | Addressee | Documents
    """
    doc.add_heading("Appendix A. Request List", level=1)

    reqs = fb.requests
    if not reqs:
        doc.add_paragraph("No due diligence requests were generated in this review.")
        return

    # Intro narrative
    if narratives and narratives.get("requests_summary"):
        doc.add_paragraph(narratives["requests_summary"])
    else:
        total = len(reqs)
        by_priority = {}
        for r in reqs:
            p = r.get("priority", "medium")
            by_priority[p] = by_priority.get(p, 0) + 1
        text = (
            f"{total} due diligence request(s) were generated, distributed by "
            f"priority: "
            + ", ".join(f"{k}={v}" for k, v in sorted(by_priority.items()))
            + "."
        )
        doc.add_paragraph(text)

    doc.add_paragraph("")

    # Table — Landscape
    table = doc.add_table(rows=len(reqs) + 1, cols=6)
    table.style = "Light Grid Accent 1"
    _set_table_widths(table, [
        Inches(0.4), Inches(0.9), Inches(1.7),
        Inches(4.3), Inches(1.2), Inches(1.5),
    ])

    header = table.rows[0].cells
    header[0].text = "#"
    header[1].text = "Priority"
    header[2].text = "Check"
    header[3].text = "Text"
    header[4].text = "Addressee"
    header[5].text = "Documents"

    for i, req in enumerate(reqs, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(i)
        cells[1].text = _humanize_value(req.get("priority", ""), fb.meta.locale).upper()
        cells[2].text = _safe_text(req.get("check_name", ""), 60)
        cells[3].text = _safe_text(req.get("text", ""), 400)
        cells[4].text = _safe_text(req.get("addressee", ""), 60)
        docs = req.get("document_names") or []
        cells[5].text = _safe_text(", ".join(docs), 200)

    _style_table_header(table)
    _set_table_header_repeat(table)


# ---------------------------------------------------------------------------
# SECTION: Appendix B. Methodology & Reproducibility
# ---------------------------------------------------------------------------


def _add_appendix_methodology(doc: Document, fb: FactBundle) -> None:
    """
    Appendix B. Methodology & Reproducibility — meta + quality metrics.
    """
    doc.add_heading("Appendix B. Methodology & Reproducibility", level=1)

    meta = fb.meta
    quality = fb.quality
    totals = fb.totals

    # Repro table
    rows = [
        ("Deal name", _sanitize_deal_name(meta.deal_name)),
        ("Run ID", meta.run_id),
        ("Playbook profile", meta.playbook_profile),
        ("Playbook version", meta.playbook_version),
        ("Checks mode", meta.checks_mode or "—"),
        ("Pipeline strategy", meta.pipeline_strategy or "—"),
        ("Environment hash", meta.environment_hash or "—"),
        ("Locale", meta.locale),
        ("Generated at", meta.generated_at or "—"),
    ]

    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Light Grid Accent 1"
    for i, (k, v) in enumerate(rows):
        cells = table.rows[i].cells
        cells[0].text = k
        cells[1].text = str(v)
    for row in table.rows:
        for paragraph in row.cells[0].paragraphs:
            for run in paragraph.runs:
                run.font.bold = True

    doc.add_paragraph("")

    # Quality metrics
    doc.add_heading("Analysis quality", level=2)

    q_rows = [
        ("Checks planned", str(totals.get("checks_planned", 0))),
        ("Checks completed", str(totals.get("checks_completed", 0))),
        ("Checks not applicable", str(totals.get("checks_not_applicable", 0))),
        ("Documents processed", str(totals.get("documents", 0))),
        ("Documents quarantined", str(quality.get("quarantine_count", 0))),
        ("Documents with degraded structure", str(quality.get("degraded_count", 0))),
        ("Average confidence", f"{quality.get('avg_confidence', 0.0):.2f}"),
        ("Low-confidence findings", str(quality.get("low_confidence_count", 0))),
        ("Evidence validity rate", f"{quality.get('evidence_validity_rate', 1.0):.2%}"),
        ("Needs manual review", str(quality.get("needs_manual_review_count", 0))),
    ]

    detector = quality.get("detector_coverage", {}) or {}
    q_rows.extend([
        ("Rules-based checks", str(detector.get("rules", 0))),
        ("Hybrid checks", str(detector.get("hybrid", 0))),
        ("LLM-based checks", str(detector.get("llm", 0))),
    ])

    q_table = doc.add_table(rows=len(q_rows), cols=2)
    q_table.style = "Light Grid Accent 1"
    for i, (k, v) in enumerate(q_rows):
        cells = q_table.rows[i].cells
        cells[0].text = k
        cells[1].text = v
    for row in q_table.rows:
        for paragraph in row.cells[0].paragraphs:
            for run in paragraph.runs:
                run.font.bold = True


# ---------------------------------------------------------------------------
# SECTION: Appendix C. Documents Reviewed
# ---------------------------------------------------------------------------


def _add_appendix_documents(doc: Document, fb: FactBundle) -> None:
    """
    Appendix C. Documents Reviewed — таблица документов.
    Columns: # | Filename | Folder | Doc Type | Language | Confidence
    """
    doc.add_heading("Appendix C. Documents Reviewed", level=1)

    docs = fb.documents_reviewed
    if not docs:
        doc.add_paragraph("No documents were reviewed in this run.")
        return

    table = doc.add_table(rows=len(docs) + 1, cols=6)
    table.style = "Light Grid Accent 1"
    # Appendix C — portrait section: 8.5" - 0.8" - 0.8" = 6.9" доступно
    _set_table_widths(table, [
        Inches(0.35), Inches(2.50), Inches(0.55),
        Inches(1.50), Inches(0.90), Inches(1.10),
    ])

    header = table.rows[0].cells
    header[0].text = "#"
    header[1].text = "Filename"
    header[2].text = "Folder"
    header[3].text = "Doc Type"
    header[4].text = "Language"
    header[5].text = "Confidence"

    for i, doc_row in enumerate(docs, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(i)
        cells[1].text = _safe_text(doc_row.get("name", ""), 80)
        cells[2].text = _safe_text(doc_row.get("folder_path", ""), 60)
        label = doc_row.get("doc_type_label") or doc_row.get("doc_type", "")
        cells[3].text = _safe_text(label, 60)
        lang_raw = doc_row.get("language", "") or ""
        cells[4].text = _humanize_language(lang_raw, fb.meta.locale)
        conf = doc_row.get("classification_confidence", 0.0)
        cells[5].text = f"{conf:.2f}" if conf else ""

    _style_table_header(table)
    _set_table_header_repeat(table)


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT — build_report_docx_v2
# ---------------------------------------------------------------------------


def build_report_docx_v2(
    fact_bundle: FactBundle,
    narratives: dict | None = None,
    style: str = "corporate_blue",
) -> bytes:
    """
    Собирает DD Report v2 из FactBundle.

    Структура (Big4/Olswang):
    - Титульная
    - TOC
    - 1. Definitions
    - 2. Purpose of Report
    - 3. Terms of Reference
    - 4. Key Findings / Executive Summary (4.1-4.4)
    - 5. Detailed Report (5.1-5.2) [LANDSCAPE]
    - 6. Extracted Values [LANDSCAPE]
    - Appendix A. Request List [LANDSCAPE]
    - Appendix B. Methodology & Reproducibility
    - Appendix C. Documents Reviewed

    Args:
        fact_bundle: FactBundle из build_fact_bundle().
        narratives:  dict с LLM-нарративами (опционально).
        style:       имя стиля (пока не используется — reserved).

    Returns:
        bytes — содержимое .docx файла.
    """
    logger.info(
        "Building DD Report v2 from FactBundle",
        extra={
            "style": style,
            "has_narratives": bool(narratives),
            "checks_planned": fact_bundle.totals.get("checks_planned", 0),
        },
    )

    doc = Document()

    # Настраиваем Word-стили под Big4
    _configure_document_styles(doc)

    # ---------- SECTION 0: титул (стандартные margins) ----------
    _add_title_page_v2(doc, fact_bundle)

    # ---------- SECTION 1: TOC + Purpose + Terms (portrait, обычные margins) ----------
    _start_portrait_section(doc)
    _add_toc(doc)
    doc.add_page_break()
    _add_purpose(doc, fact_bundle, narratives)
    _add_terms_of_reference(doc, fact_bundle, narratives)

    # ---------- PORTRAIT: key findings ----------
    doc.add_page_break()
    _add_overall_summary(doc, fact_bundle, narratives)
    _add_key_findings_global(doc, fact_bundle, narratives)
    _add_key_findings_doctype(doc, fact_bundle, narratives)

    # ---------- LANDSCAPE: detailed report ----------
    _start_landscape_section(doc)
    _add_detailed_report_global(doc, fact_bundle, narratives)
    _add_detailed_report_doctype(doc, fact_bundle, narratives)

    # ---------- LANDSCAPE: extracted values ----------
    _start_landscape_section(doc)
    _add_extracted_values_landscape(doc, fact_bundle, narratives)

    # ---------- LANDSCAPE: appendix A (requests) ----------
    _start_landscape_section(doc)
    _add_appendix_requests(doc, fact_bundle, narratives)

    # ---------- PORTRAIT: appendices B, C ----------
    _start_portrait_section(doc)
    _add_appendix_methodology(doc, fact_bundle)
    _add_appendix_documents(doc, fact_bundle)

    # ---------- Header / Footer на все секции ----------
    _apply_headers_footers(doc, fact_bundle)

    # ---------- Update fields on open (TOC, page numbers) ----------
    _enable_update_fields_on_open(doc)

    # ---------- Save ----------
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    result_bytes = output.read()

    logger.info(
        "DD Report v2 built successfully",
        extra={
            "size_bytes": len(result_bytes),
            "sections": len(doc.sections),
            "tables": len(doc.tables),
        },
    )

    return result_bytes


    