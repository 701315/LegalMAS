# src/services/primary_pdf_builder.py

"""
Primary PDF builder.

Назначение:
- собрать новый PDF из уже подготовленного одноязычного layout;
- использовать этот PDF как primary_source_ref для extract_worker;
- не пытаться идеально воспроизвести оригинальную вёрстку, а сделать
  стабильный и извлекаемый downstream PDF.

Дизайн-принципы:
- production-safe: если layout плохой, лучше поднять явную ошибку;
- предсказуемость: один и тот же layout -> одинаковая структура PDF;
- простота: текст рисуется по bbox, страницы создаются по фактическому числу страниц;
- downstream-friendly: PDF должен хорошо читаться повторным extract_pdf().

Ограничения текущей версии:
- рисуем только text elements;
- tables отдельно не реконструируем как настоящие таблицы;
- используем один Unicode-шрифт для всех языков;
- не сохраняем оригинальные fontname/fontsize из PDF, если их нет в layout;
- не вставляем изображения и графику из исходного документа.

Это первый production-шаг варианта A: сначала получаем одноязычный PDF-конвейер,
затем при необходимости улучшаем fidelity.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from core.exceptions import PermanentError
from core.logging import get_logger

logger = get_logger(__name__)

REPORTLAB_IMPORT_ERROR: Exception | None = None

try:
    from reportlab.lib.colors import black
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    REPORTLAB_AVAILABLE = True
    DEFAULT_PAGE_SIZE = A4
except Exception as exc:
    REPORTLAB_AVAILABLE = False
    REPORTLAB_IMPORT_ERROR = exc
    DEFAULT_PAGE_SIZE = (595.2756, 841.8898)  # A4 fallback in points


DEFAULT_PAGE_WIDTH = float(DEFAULT_PAGE_SIZE[0])
DEFAULT_PAGE_HEIGHT = float(DEFAULT_PAGE_SIZE[1])

# Ожидаем, что эти шрифты доступны в контейнере.
UNICODE_FONT_NAME = "DejaVuSans"
UNICODE_FONT_BOLD_NAME = "DejaVuSans-Bold"

DEFAULT_FONT_NAME = UNICODE_FONT_NAME
DEFAULT_FONT_NAME_BOLD = UNICODE_FONT_BOLD_NAME
DEFAULT_FONT_SIZE_TEXT = 10.0
DEFAULT_FONT_SIZE_HEADING = 12.0

MIN_FONT_SIZE = 6.0
MAX_FONT_SIZE = 18.0
MIN_LINE_HEIGHT_FACTOR = 1.15
MAX_LINE_HEIGHT_FACTOR = 1.35

PAGE_MARGIN_LEFT = 24.0
PAGE_MARGIN_RIGHT = 24.0
PAGE_MARGIN_TOP = 24.0
PAGE_MARGIN_BOTTOM = 24.0

# Минимальный допустимый процент реально отрисованных элементов.
# Если ниже — считаем layout деградированным и явно падаем.
MIN_DRAWN_RATIO = 0.5

# Опциональный debug-режим — рисовать рамки bbox
DEBUG_DRAW_BBOX = False


@dataclass
class PrimaryPdfBuildStats:
    page_count: int
    element_count_in: int
    element_count_drawn: int
    skipped_elements: int


def _register_unicode_fonts() -> None:
    """
    Зарегистрировать Unicode-шрифты для всех скриптов (латиница, кириллица и т.п.).

    Ожидается, что соответствующие TTF-файлы есть в Docker-образе.
    Например, для DejaVuSans это обычно:
    /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
    /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
    """
    if not REPORTLAB_AVAILABLE:
        return

    try:
        pdfmetrics.registerFont(
            TTFont(UNICODE_FONT_NAME, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        )
        pdfmetrics.registerFont(
            TTFont(
                UNICODE_FONT_BOLD_NAME,
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "primary_pdf_builder: failed to register unicode fonts",
            error=str(exc),
        )
        raise PermanentError("primary_pdf_builder cannot register unicode fonts")


def build_pdf_from_layout(layout: dict[str, Any]) -> bytes:
    """
    Построить PDF из одноязычного layout.

    Ожидаемый вход:
    {
        "document_id": str,
        "document_version_id": str,
        "elements": [...],
        "metadata": {...}
    }

    Возвращает:
    - bytes готового PDF.

    Ошибка:
    - PermanentError, если layout пустой или ReportLab недоступен.
    """
    if not REPORTLAB_AVAILABLE:
        raise PermanentError("primary_pdf_builder requires reportlab, but it is not installed")

    _register_unicode_fonts()

    elements = layout.get("elements") or []
    if not elements:
        raise PermanentError("Cannot build primary PDF from empty layout")

    page_count = _resolve_page_count(layout, elements)
    pages = _group_elements_by_page(elements, page_count=page_count)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=DEFAULT_PAGE_SIZE)
    pdf.setTitle(_safe_pdf_title(layout))
    pdf.setAuthor("LegalMAS")
    pdf.setSubject("Primary language source")
    pdf.setCreator("LegalMAS primary_pdf_builder")
    pdf.setFillColor(black)

    drawn_count = 0
    skipped_count = 0

    for page_num in range(1, page_count + 1):
        page_elements = pages.get(page_num, [])
        page_elements = sorted(
            page_elements,
            key=_bbox_sort_key,
        )

        for el in page_elements:
            drawn = _draw_element(pdf, el)
            if drawn:
                drawn_count += 1
            else:
                skipped_count += 1

        if page_num < page_count:
            pdf.showPage()

    pdf.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()

    stats = PrimaryPdfBuildStats(
        page_count=page_count,
        element_count_in=len(elements),
        element_count_drawn=drawn_count,
        skipped_elements=skipped_count,
    )

    logger.info(
        "Primary PDF build complete",
        document_id=layout.get("document_id"),
        document_version_id=layout.get("document_version_id"),
        page_count=stats.page_count,
        element_count_in=stats.element_count_in,
        element_count_drawn=stats.element_count_drawn,
        skipped_elements=stats.skipped_elements,
        pdf_size=len(pdf_bytes),
    )

    if not pdf_bytes:
        raise PermanentError("Primary PDF builder produced empty PDF bytes")

    if stats.element_count_in and (
        stats.element_count_drawn / stats.element_count_in < MIN_DRAWN_RATIO
    ):
        raise PermanentError(
            "Primary PDF builder drew only "
            f"{stats.element_count_drawn}/{stats.element_count_in} elements"
        )

    return pdf_bytes


def _resolve_page_count(layout: dict[str, Any], elements: list[dict[str, Any]]) -> int:
    """
    Определить число страниц.

    Приоритет:
    1. metadata.pages
    2. максимум page в elements
    3. 1
    """
    metadata = layout.get("metadata") or {}
    meta_pages = metadata.get("pages")
    if isinstance(meta_pages, int) and meta_pages > 0:
        return meta_pages

    max_page = 1
    for el in elements:
        page = el.get("page", 1)
        try:
            page_int = int(page)
            if page_int > max_page:
                max_page = page_int
        except Exception:
            continue

    return max_page


def _group_elements_by_page(
    elements: list[dict[str, Any]],
    page_count: int,
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {
        page_num: [] for page_num in range(1, page_count + 1)
    }

    for el in elements:
        page = el.get("page", 1)
        try:
            page_num = int(page)
        except Exception:
            page_num = 1

        if page_num < 1:
            page_num = 1
        if page_num > page_count:
            page_num = page_count

        grouped.setdefault(page_num, []).append(el)

    return grouped


def _bbox_sort_key(element: dict[str, Any]) -> tuple[int, float, float]:
    bbox = _safe_bbox(element)
    page = _safe_int_page(element.get("page", 1))
    return page, bbox[1], bbox[0]


def _draw_element(pdf: canvas.Canvas, element: dict[str, Any]) -> bool:
    """
    Нарисовать один text element в PDF.

    Возвращает:
    - True, если элемент реально отрисован;
    - False, если элемент пришлось пропустить.
    """
    text = (element.get("text") or "").strip()
    if not text:
        return False

    bbox = _safe_bbox(element)
    x0, top, x1, bottom = bbox

    box_width = max(0.0, x1 - x0)
    box_height = max(0.0, bottom - top)

    if box_width <= 1 or box_height <= 1:
        return False

    x = _clamp(x0, PAGE_MARGIN_LEFT, DEFAULT_PAGE_WIDTH - PAGE_MARGIN_RIGHT)
    y_top = _clamp(top, PAGE_MARGIN_TOP, DEFAULT_PAGE_HEIGHT - PAGE_MARGIN_BOTTOM)
    y_bottom = _clamp(bottom, PAGE_MARGIN_TOP, DEFAULT_PAGE_HEIGHT - PAGE_MARGIN_BOTTOM)

    usable_width = max(
        1.0,
        min(box_width, DEFAULT_PAGE_WIDTH - PAGE_MARGIN_LEFT - PAGE_MARGIN_RIGHT),
    )
    usable_height = max(
        1.0,
        abs(y_bottom - y_top),
    )

    element_type = (element.get("type") or "text").lower()
    font_name = DEFAULT_FONT_NAME_BOLD if element_type == "heading" else DEFAULT_FONT_NAME
    estimated_font_size = _estimate_font_size(
        text=text,
        box_width=usable_width,
        box_height=usable_height,
        is_heading=(element_type == "heading"),
    )

    pdf.setFont(font_name, estimated_font_size)

    # ReportLab рисует от нижней точки, а bbox у нас — top/bottom.
    # Переводим в координаты canvas: (0,0) внизу страницы.
    canvas_top = DEFAULT_PAGE_HEIGHT - y_top
    canvas_bottom = DEFAULT_PAGE_HEIGHT - y_bottom

    line_height = estimated_font_size * _line_height_factor(estimated_font_size)
    start_y = max(canvas_bottom + 1, canvas_top - estimated_font_size)

    wrapped_lines = _wrap_text_to_width(
        text=text,
        font_name=font_name,
        font_size=estimated_font_size,
        max_width=usable_width,
    )

    if not wrapped_lines:
        return False

    if DEBUG_DRAW_BBOX:
        pdf.setStrokeColorRGB(1, 0, 0)
        pdf.rect(
            x,
            canvas_bottom,
            usable_width,
            canvas_top - canvas_bottom,
            stroke=1,
            fill=0,
        )
        pdf.setStrokeColorRGB(0, 0, 0)

    text_obj = pdf.beginText()
    text_obj.setTextOrigin(x, start_y)
    text_obj.setFont(font_name, estimated_font_size)
    text_obj.setLeading(line_height)

    current_y = start_y
    min_allowed_y = canvas_bottom - line_height

    for line in wrapped_lines:
        if current_y < min_allowed_y:
            break
        text_obj.textLine(line)
        current_y -= line_height

    pdf.drawText(text_obj)
    return True


def _estimate_font_size(
    text: str,
    box_width: float,
    box_height: float,
    is_heading: bool,
) -> float:
    """
    Грубая, но стабильная эвристика выбора font size по bbox.

    Идея:
    - heading немного крупнее;
    - размер ограничен bbox по высоте;
    - размер ограничен шириной по средней длине текста.
    """
    base_size = DEFAULT_FONT_SIZE_HEADING if is_heading else DEFAULT_FONT_SIZE_TEXT

    if not text:
        return base_size

    height_limited = max(
        MIN_FONT_SIZE,
        min(MAX_FONT_SIZE, box_height * 0.75),
    )

    avg_char_width_factor = 0.58 if is_heading else 0.52
    width_limited = box_width / max(len(text) * avg_char_width_factor, 1.0)

    estimated = min(base_size, height_limited, width_limited)

    if is_heading:
        estimated = max(estimated, DEFAULT_FONT_SIZE_TEXT)

    return round(_clamp(estimated, MIN_FONT_SIZE, MAX_FONT_SIZE), 2)


def _wrap_text_to_width(
    text: str,
    font_name: str,
    font_size: float,
    max_width: float,
) -> list[str]:
    """
    Перенести текст по словам так, чтобы он влезал по ширине.

    Если слово очень длинное, режем его грубо по символам.
    """
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = word
        else:
            hard_chunks = _split_long_word(
                word=word,
                font_name=font_name,
                font_size=font_size,
                max_width=max_width,
            )
            lines.extend(hard_chunks[:-1])
            current = hard_chunks[-1] if hard_chunks else ""

    if current:
        lines.append(current)

    return lines


def _split_long_word(
    word: str,
    font_name: str,
    font_size: float,
    max_width: float,
) -> list[str]:
    """
    Грубый fallback для длинного слова без пробелов.
    """
    if not word:
        return []

    chunks: list[str] = []
    current = ""

    for ch in word:
        candidate = current + ch
        if stringWidth(candidate, font_name, font_size) <= max_width or not current:
            current = candidate
        else:
            chunks.append(current)
            current = ch

    if current:
        chunks.append(current)

    return chunks


def _line_height_factor(font_size: float) -> float:
    """
    Немного увеличиваем interline для мелкого текста.
    """
    if font_size <= 8:
        return MAX_LINE_HEIGHT_FACTOR
    if font_size <= 10:
        return 1.25
    if font_size <= 12:
        return 1.2
    return MIN_LINE_HEIGHT_FACTOR


def _safe_bbox(element: dict[str, Any]) -> list[float]:
    """
    Безопасно привести bbox к [x0, top, x1, bottom].
    """
    raw_bbox = element.get("bbox") or [0, 0, 0, 0]
    if not isinstance(raw_bbox, list | tuple) or len(raw_bbox) < 4:
        return [0.0, 0.0, 0.0, 0.0]

    result: list[float] = []
    for value in raw_bbox[:4]:
        try:
            result.append(float(value))
        except Exception:
            result.append(0.0)

    x0, top, x1, bottom = result
    if x1 < x0:
        x0, x1 = x1, x0
    if bottom < top:
        top, bottom = bottom, top

    return [x0, top, x1, bottom]


def _safe_int_page(value: Any, default: int = 1) -> int:
    try:
        page = int(float(str(value).strip()))
        return page if page > 0 else default
    except Exception:
        return default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _safe_pdf_title(layout: dict[str, Any]) -> str:
    """
    Небольшой title для metadata PDF.
    """
    document_id = layout.get("document_id") or "unknown-document"
    return f"Primary source for {document_id}"
