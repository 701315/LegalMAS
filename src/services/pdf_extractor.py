# src/services/pdf_extractor.py

"""
PDF Extraction Service.

Отвечает за извлечение текстовой разметки и таблиц из PDF и построение
структуры textlayoutraw, которая затем используется всеми downstream‑стадиями.

Поддерживает три стратегии постраничной обработки:
  - text   : pdfplumber для нативных PDF с текстовым слоем (быстро, качественно)
  - ocr    : Tesseract для сканов (медленнее, качество зависит от OCR)
  - hybrid : сочетание text и ocr для смешанных документов (частично сканы)

Результат extract_pdf(...) — ExtractionResult с:
  - elements        : список Element (текстовые блоки, уже сгруппированные по строкам)
  - tables          : список TableData (сырые таблицы)
  - page_count      : число страниц
  - strategy        : общий режим (text | ocr | hybrid)
  - page_strategies : стратегия по каждой странице
  - ocr_confidences : средняя уверенность OCR по страницам
  - errors          : диагностические сообщения

Функция build_text_layout_raw(...) конвертирует ExtractionResult в JSON‑формат
textlayoutraw, который далее используют:
  - PII Sanitizer      (Stage 5)  — итерируется по elements для детекции/токенизации PII;
  - Structure Builder  (Stage 6)  — опирается на element.type (heading/text/listitem)
                                    для поиска границ клауз и проставления clause_uid;
  - Classifier L2/L3   (Stage 6)  — читает первые N символов из elements для
                                    keyword/semantic классификации;
  - Runner / Retrieval (Stage 8)  — строит BM25 и эмбеддинги по elements
                                    и использует element_id для ссылок на доказательства.
"""

import hashlib
import io
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pdfplumber

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ─── OCR availability ──────────────────────────────────────────────────────────
OCR_AVAILABLE = False
try:
    import pytesseract
    from pdf2image import convert_from_bytes

    pytesseract.get_tesseract_version()
    OCR_AVAILABLE = True
except Exception:
    logger.info("OCR not available — Tesseract not installed or not found")


# ─── Data classes ─────────────────────────────────────────────────────────────


class PageStrategy(str, Enum):
    TEXT = "text"
    OCR = "ocr"
    EMPTY = "empty"


@dataclass
class Element:
    """Single text block extracted from a PDF page."""

    element_id: str
    type: str  # heading | text | listitem
    text: str
    page: int
    bbox: list  # [x0, top, x1, bottom]
    confidence: float = 1.0
    strategy: str = "text"
    # NOTE: clause_uid is NOT set here — it is added by Structure Builder
    # after clause tree is built (Stage 6).


@dataclass
class TableData:
    """Table extracted from a PDF page."""

    page: int
    rows: list = field(default_factory=list)  # list[list[str]]
    bbox: list = field(default_factory=list)  # [x0, top, x1, bottom]


@dataclass
class ExtractionResult:
    """Complete result of extracting a PDF document."""

    elements: list = field(default_factory=list)  # list[Element]
    tables: list = field(default_factory=list)  # list[TableData]
    page_count: int = 0
    strategy: str = "text"  # overall: text | ocr | hybrid
    page_strategies: dict = field(default_factory=dict)  # {page_num: strategy}
    ocr_confidences: list = field(default_factory=list)  # per-page avg
    avg_ocr_confidence: float = 1.0
    errors: list = field(default_factory=list)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def make_element_id(document_id: str, page_num: int, element_index: int) -> str:
    """
    Generate a deterministic element ID.
    Same document + same processing order → same element IDs → reproducible pipelines.
    Used by Structure Builder to build clause tree and by Runner to cite evidence.
    """
    raw = f"{document_id}{page_num}{element_index}"
    return "e" + hashlib.sha256(raw.encode()).hexdigest()[:10]


def is_ocr_available() -> bool:
    return OCR_AVAILABLE and settings.EXTRACTION_OCR_ENABLED


def _is_debug_enabled_for_doc(document_id: str) -> bool:
    enabled = bool(getattr(settings, "EXTRACTION_DEBUG_LOG", False))
    if not enabled:
        return False

    debug_doc_id = getattr(settings, "EXTRACTION_DEBUG_DOC_ID", None)
    return debug_doc_id in (None, "", document_id)


def _safe_preview(text: str, limit: int = 200) -> str:
    if not text:
        return ""
    return text[:limit].replace("\n", " ").replace("\r", " ")


def _safe_page_metrics(page: Any) -> dict[str, Any]:
    width = height = None
    images_count = None
    chars_count = None
    try:
        width = float(page.width) if getattr(page, "width", None) is not None else None
    except Exception:
        width = None
    try:
        height = float(page.height) if getattr(page, "height", None) is not None else None
    except Exception:
        height = None
    try:
        images_count = (
            len(page.images) if hasattr(page, "images") and page.images is not None else 0
        )
    except Exception:
        images_count = None
    try:
        chars_count = len(page.chars) if hasattr(page, "chars") and page.chars is not None else 0
    except Exception:
        chars_count = None

    return {
        "width": width,
        "height": height,
        "images_count": images_count,
        "chars_count": chars_count,
    }


# ─── Main entry point ─────────────────────────────────────────────────────────


def extract_pdf(pdf_bytes: bytes, document_id: str) -> ExtractionResult:
    """
    Extract text and tables from a PDF document.
    """
    result = ExtractionResult()
    element_index = 0
    start_time = time.time()
    hard_timeout = getattr(settings, "EXTRACTION_HARD_TIMEOUT_SECONDS", 120)

    debug_this_doc = _is_debug_enabled_for_doc(document_id)

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            result.page_count = len(pdf.pages)

            if debug_this_doc:
                logger.debug(
                    "Extract: opened PDF",
                    document_id=document_id,
                    page_count=result.page_count,
                    pdf_size=len(pdf_bytes),
                )

            if result.page_count == 0:
                result.errors.append("PDF has 0 pages")
                return result

            if result.page_count > settings.EXTRACTION_MAX_PAGES:
                result.errors.append(
                    f"PDF has {result.page_count} pages, " f"max {settings.EXTRACTION_MAX_PAGES}"
                )
                return result

            text_pages = 0
            ocr_pages = 0
            empty_pages = 0

            for page_num, page in enumerate(pdf.pages, start=1):
                elapsed = time.time() - start_time
                if elapsed > hard_timeout:
                    msg = (
                        f"Extraction hard timeout after {hard_timeout} seconds "
                        f"on page {page_num}"
                    )
                    logger.error(msg, document_id=document_id)
                    result.errors.append(msg)
                    break

                page_metrics = _safe_page_metrics(page)

                page_text_raw = ""
                page_text_error = None
                try:
                    page_text_raw = page.extract_text() or ""
                except Exception as e:
                    page_text_error = str(e)
                    page_text_raw = ""

                page_text = page_text_raw.strip()
                page_text_len = len(page_text)

                if debug_this_doc:
                    logger.debug(
                        "Extract: page pre-scan",
                        document_id=document_id,
                        page=page_num,
                        elapsed_seconds=round(elapsed, 3),
                        text_len=page_text_len,
                        text_preview=_safe_preview(page_text, 300),
                        extract_text_error=page_text_error,
                        **page_metrics,
                    )

                logger.debug(
                    "Extract: starting page",
                    document_id=document_id,
                    page=page_num,
                )

                strategy = _detect_page_strategy_with_text(page, page_text, page_text_len)
                result.page_strategies[page_num] = strategy.value

                if debug_this_doc:
                    logger.debug(
                        "Extract: page strategy decided",
                        document_id=document_id,
                        page=page_num,
                        strategy=strategy.value,
                        text_len=page_text_len,
                        min_text_threshold=getattr(
                            settings, "EXTRACTION_MIN_TEXT_LENGTH_PER_PAGE", None
                        ),
                        images_count=page_metrics.get("images_count"),
                        chars_count=page_metrics.get("chars_count"),
                    )

                page_element_count = 0
                page_table_count = 0

                if strategy == PageStrategy.TEXT:
                    page_elements = _extract_text_page(
                        page=page,
                        document_id=document_id,
                        page_num=page_num,
                        start_index=element_index,
                        debug_this_doc=debug_this_doc,
                        page_text_len=page_text_len,
                        page_text_preview=_safe_preview(page_text, 300),
                    )
                    result.elements.extend(page_elements)
                    page_element_count = len(page_elements)
                    element_index += page_element_count
                    text_pages += 1

                elif strategy == PageStrategy.OCR:
                    if is_ocr_available():
                        page_elements, page_conf = _extract_ocr_page(
                            pdf_bytes=pdf_bytes,
                            page_num=page_num,
                            document_id=document_id,
                            start_index=element_index,
                            debug_this_doc=debug_this_doc,
                        )
                        result.elements.extend(page_elements)
                        page_element_count = len(page_elements)
                        element_index += page_element_count
                        result.ocr_confidences.append(page_conf)
                        ocr_pages += 1

                        if debug_this_doc:
                            logger.debug(
                                "Extract: OCR page processed",
                                document_id=document_id,
                                page=page_num,
                                elements=page_element_count,
                                avg_conf=round(page_conf, 4),
                                first_element_preview=_safe_preview(page_elements[0].text, 200)
                                if page_elements
                                else "",
                                last_element_preview=_safe_preview(page_elements[-1].text, 200)
                                if page_elements
                                else "",
                            )
                    else:
                        msg = f"Page {page_num}: OCR required but Tesseract not available"
                        result.errors.append(msg)
                        logger.warning(
                            "Extract: OCR required but Tesseract unavailable",
                            document_id=document_id,
                            page=page_num,
                        )

                else:
                    empty_pages += 1
                    if debug_this_doc:
                        logger.debug(
                            "Extract: page classified as EMPTY",
                            document_id=document_id,
                            page=page_num,
                            text_len=page_text_len,
                            text_preview=_safe_preview(page_text, 200),
                        )

                page_tables = _extract_tables(
                    page, page_num, debug_this_doc=debug_this_doc, document_id=document_id
                )
                page_table_count = len(page_tables)
                result.tables.extend(page_tables)

                if debug_this_doc:
                    logger.debug(
                        "Extract: page completed",
                        document_id=document_id,
                        page=page_num,
                        strategy=strategy.value,
                        page_elements=page_element_count,
                        page_tables=page_table_count,
                        cumulative_elements=len(result.elements),
                        cumulative_tables=len(result.tables),
                    )

            if ocr_pages > 0 and text_pages > 0:
                result.strategy = "hybrid"
            elif ocr_pages > 0:
                result.strategy = "ocr"
            else:
                result.strategy = "text"

            result.avg_ocr_confidence = (
                sum(result.ocr_confidences) / len(result.ocr_confidences)
                if result.ocr_confidences
                else 1.0
            )

            if debug_this_doc:
                logger.info(
                    "Extract: document summary",
                    document_id=document_id,
                    page_count=result.page_count,
                    total_elements=len(result.elements),
                    total_tables=len(result.tables),
                    strategy=result.strategy,
                    text_pages=text_pages,
                    ocr_pages=ocr_pages,
                    empty_pages=empty_pages,
                    avg_ocr_confidence=round(result.avg_ocr_confidence, 4)
                    if result.avg_ocr_confidence is not None
                    else None,
                    errors=result.errors,
                )

    except Exception as e:
        result.errors.append(f"PDF parsing failed: {e}")
        logger.error("PDF extraction failed", error=str(e), document_id=document_id)

    if result.page_count > 0 and not result.elements:
        msg = "PDF extraction produced zero text elements"
        result.errors.append(msg)
        logger.warning(msg, document_id=document_id, pages=result.page_count)

    return result


# ─── Strategy detection ───────────────────────────────────────────────────────


def _detect_page_strategy(page: Any) -> PageStrategy:
    """
    Determine extraction strategy for a single page.
    If pdfplumber yields ≥ MIN_TEXT_LENGTH chars → text.
    If page has images but no text → ocr.
    Otherwise → empty.
    """
    try:
        text = (page.extract_text() or "").strip()
        if len(text) >= settings.EXTRACTION_MIN_TEXT_LENGTH_PER_PAGE:
            return PageStrategy.TEXT
        elif len(text) > 0:
            if hasattr(page, "images") and page.images:
                return PageStrategy.OCR
            return PageStrategy.EMPTY
        else:
            return PageStrategy.OCR
    except Exception:
        return PageStrategy.OCR


def _detect_page_strategy_with_text(page: Any, text: str, text_len: int) -> PageStrategy:
    """
    Version of strategy detection that reuses already extracted page text.
    """
    try:
        if text_len >= settings.EXTRACTION_MIN_TEXT_LENGTH_PER_PAGE:
            return PageStrategy.TEXT
        elif text_len > 0:
            if hasattr(page, "images") and page.images:
                return PageStrategy.OCR
            return PageStrategy.EMPTY
        else:
            return PageStrategy.OCR
    except Exception:
        return PageStrategy.OCR


# ─── Text extraction (pdfplumber) ─────────────────────────────────────────────


def _extract_text_page(
    page: Any,
    document_id: str,
    page_num: int,
    start_index: int,
    debug_this_doc: bool = False,
    page_text_len: int | None = None,
    page_text_preview: str | None = None,
) -> list:
    """
    Extract text elements from a page using pdfplumber word grouping.
    Returns list[Element].
    """
    elements = []
    words = []
    extract_words_error = None

    try:
        words = page.extract_words(
            keep_blank_chars=False,
            extra_attrs=["fontname", "size"],
        )
    except Exception as e:
        extract_words_error = str(e)
        words = []

    if debug_this_doc:
        first_word = words[0] if words else None
        last_word = words[-1] if words else None
        logger.debug(
            "Extract: text page words snapshot",
            document_id=document_id,
            page=page_num,
            page_text_len=page_text_len,
            page_text_preview=page_text_preview,
            words_count=len(words),
            extract_words_error=extract_words_error,
            first_word_text=(first_word.get("text") if first_word else None),
            first_word_bbox=(
                [
                    first_word.get("x0"),
                    first_word.get("top"),
                    first_word.get("x1"),
                    first_word.get("bottom"),
                ]
                if first_word
                else None
            ),
            last_word_text=(last_word.get("text") if last_word else None),
            last_word_bbox=(
                [
                    last_word.get("x0"),
                    last_word.get("top"),
                    last_word.get("x1"),
                    last_word.get("bottom"),
                ]
                if last_word
                else None
            ),
        )

    if not words:
        if debug_this_doc:
            logger.warning(
                "Extract: text page returned no words",
                document_id=document_id,
                page=page_num,
                page_text_len=page_text_len,
                page_text_preview=page_text_preview,
            )
        return elements

    lines = _group_words_into_lines(words)

    if debug_this_doc:
        first_line_text = lines[0][0] if lines else ""
        last_line_text = lines[-1][0] if lines else ""
        first_line_bbox = lines[0][1] if lines else None
        last_line_bbox = lines[-1][1] if lines else None

        logger.debug(
            "Extract: grouped lines snapshot",
            document_id=document_id,
            page=page_num,
            lines_count=len(lines),
            first_line_preview=_safe_preview(first_line_text, 200),
            first_line_bbox=first_line_bbox,
            last_line_preview=_safe_preview(last_line_text, 200),
            last_line_bbox=last_line_bbox,
        )

    for i, (line_text, line_bbox, font_info) in enumerate(lines):
        stripped = line_text.strip()
        if not stripped:
            continue

        elem_id = make_element_id(document_id, page_num, start_index + i)
        elem_type = _classify_element_type(stripped, font_info)
        elements.append(
            Element(
                element_id=elem_id,
                type=elem_type,
                text=stripped,
                page=page_num,
                bbox=line_bbox,
                confidence=1.0,
                strategy="text",
            )
        )

    if debug_this_doc:
        heading_count = sum(1 for e in elements if e.type == "heading")
        listitem_count = sum(1 for e in elements if e.type == "listitem")
        text_count = sum(1 for e in elements if e.type == "text")

        logger.debug(
            "Extract: text page elements built",
            document_id=document_id,
            page=page_num,
            elements_count=len(elements),
            heading_count=heading_count,
            listitem_count=listitem_count,
            text_count=text_count,
            first_element_preview=_safe_preview(elements[0].text, 200) if elements else "",
            last_element_preview=_safe_preview(elements[-1].text, 200) if elements else "",
        )

    return elements


# ─── OCR extraction (Tesseract) ───────────────────────────────────────────────


def _extract_ocr_page(
    pdf_bytes: bytes,
    page_num: int,
    document_id: str,
    start_index: int,
    debug_this_doc: bool = False,
) -> tuple:
    """
    Extract text from a scanned page via Tesseract.
    Returns (list[Element], avg_confidence).
    """
    elements = []
    confidences = []

    try:
        images = convert_from_bytes(
            pdf_bytes,
            dpi=settings.EXTRACTION_OCR_DPI,
            first_page=page_num,
            last_page=page_num,
        )
        if not images:
            if debug_this_doc:
                logger.warning(
                    "OCR: no images produced for page",
                    document_id=document_id,
                    page=page_num,
                    dpi=settings.EXTRACTION_OCR_DPI,
                )
            return elements, 0.0

        image = images[0]
        ocr_data = pytesseract.image_to_data(
            image,
            lang="rus+eng",
            output_type=pytesseract.Output.DICT,
        )

        if debug_this_doc:
            total_ocr_items = len(ocr_data.get("text", []))
            non_empty_ocr_words = sum(1 for t in (ocr_data.get("text", []) or []) if str(t).strip())
            logger.debug(
                "OCR: image_to_data snapshot",
                document_id=document_id,
                page=page_num,
                dpi=settings.EXTRACTION_OCR_DPI,
                total_items=total_ocr_items,
                non_empty_words=non_empty_ocr_words,
            )

        current_line_words = []
        current_line_num = -1
        current_block_num = -1

        for idx in range(len(ocr_data["text"])):
            word_text = ocr_data["text"][idx].strip()
            word_conf = int(ocr_data["conf"][idx])
            block_num = ocr_data["block_num"][idx]
            line_num = ocr_data["line_num"][idx]

            if not word_text or word_conf < 0:
                continue

            if line_num != current_line_num or block_num != current_block_num:
                if current_line_words:
                    elem, conf = _build_ocr_element(
                        current_line_words,
                        document_id,
                        page_num,
                        start_index + len(elements),
                    )
                    if elem:
                        elements.append(elem)
                        confidences.append(conf)
                current_line_words = []
                current_line_num = line_num
                current_block_num = block_num

            current_line_words.append(
                {
                    "text": word_text,
                    "conf": word_conf,
                    "left": ocr_data["left"][idx],
                    "top": ocr_data["top"][idx],
                    "width": ocr_data["width"][idx],
                    "height": ocr_data["height"][idx],
                }
            )

        if current_line_words:
            elem, conf = _build_ocr_element(
                current_line_words,
                document_id,
                page_num,
                start_index + len(elements),
            )
            if elem:
                elements.append(elem)
                confidences.append(conf)

    except Exception as e:
        logger.warning("OCR extraction failed for page", page=page_num, error=str(e))

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    if debug_this_doc:
        logger.debug(
            "OCR: page elements built",
            document_id=document_id,
            page=page_num,
            elements_count=len(elements),
            avg_conf=round(avg_conf, 4),
            first_element_preview=_safe_preview(elements[0].text, 200) if elements else "",
            last_element_preview=_safe_preview(elements[-1].text, 200) if elements else "",
        )

    return elements, avg_conf


def _build_ocr_element(words: list, document_id: str, page_num: int, element_index: int) -> tuple:
    """Build an Element from a list of OCR words on the same line."""
    if not words:
        return None, 0.0

    text = " ".join(w["text"] for w in words).strip()
    if not text:
        return None, 0.0

    avg_conf = sum(w["conf"] for w in words) / len(words)
    bbox = [
        min(w["left"] for w in words),
        min(w["top"] for w in words),
        max(w["left"] + w["width"] for w in words),
        max(w["top"] + w["height"] for w in words),
    ]
    elem_id = make_element_id(document_id, page_num, element_index)
    elem_type = _classify_element_type(text)

    return Element(
        element_id=elem_id,
        type=elem_type,
        text=text,
        page=page_num,
        bbox=[round(v, 2) for v in bbox],
        confidence=round(avg_conf / 100.0, 3),
        strategy="ocr",
    ), avg_conf / 100.0


# ─── Table extraction ─────────────────────────────────────────────────────────


def _extract_tables(
    page: Any,
    page_num: int,
    debug_this_doc: bool = False,
    document_id: str | None = None,
) -> list:
    """Extract tables from a page using pdfplumber."""
    tables = []
    try:
        page_tables = page.extract_tables()
        for idx, table in enumerate(page_tables):
            if table and any(any(cell for cell in row) for row in table):
                clean_rows = [
                    [cell.strip() if isinstance(cell, str) else cell for cell in row]
                    for row in table
                ]
                tables.append(TableData(page=page_num, rows=clean_rows))

                if debug_this_doc:
                    row_count = len(clean_rows)
                    col_count = max((len(r) for r in clean_rows), default=0)
                    logger.debug(
                        "Extract: table extracted",
                        document_id=document_id,
                        page=page_num,
                        table_index=idx,
                        rows=row_count,
                        cols=col_count,
                    )
    except Exception as e:
        logger.debug("Table extraction failed", page=page_num, error=str(e))
    return tables


# ─── Word grouping ────────────────────────────────────────────────────────────


def _group_words_into_lines(words: list) -> list:
    """
    Group pdfplumber words into lines by vertical proximity (±3px tolerance).
    Returns list of (text, bbox, font_info).
    """
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    lines = []
    current_line = [sorted_words[0]]
    current_top = round(sorted_words[0]["top"], 1)

    for word in sorted_words[1:]:
        word_top = round(word["top"], 1)
        if abs(word_top - current_top) <= 3:
            current_line.append(word)
        else:
            lines.append(_finalize_line(current_line))
            current_line = [word]
            current_top = word_top

    if current_line:
        lines.append(_finalize_line(current_line))

    return lines


def _finalize_line(words: list) -> tuple:
    """Build (text, bbox, font_info) from a list of words on the same line."""
    words_sorted = sorted(words, key=lambda w: w["x0"])
    text = " ".join(w["text"] for w in words_sorted)
    bbox = [
        round(min(w["x0"] for w in words_sorted), 2),
        round(min(w["top"] for w in words_sorted), 2),
        round(max(w["x1"] for w in words_sorted), 2),
        round(max(w["bottom"] for w in words_sorted), 2),
    ]
    font_info = {}
    if words_sorted and "fontname" in words_sorted[0]:
        font_info["fontname"] = words_sorted[0]["fontname"]
    if words_sorted and "size" in words_sorted[0]:
        font_info["size"] = words_sorted[0]["size"]
    return text, bbox, font_info


# ─── Element type classification ──────────────────────────────────────────────


def _classify_element_type(text: str, font_info: dict = None) -> str:
    """
    Classify a text element as heading, listitem, or text.

    Rules (priority order):
      1. Numeric heading  : "1.", "1.1", "1.1.1."
      2. All-caps short   : SHORT ALL-CAPS → heading
      3. List item        : starts with "–", "-", "•", "◦"
      4. Large font (≥14) : heading
      5. Bold font        : heading (if short)
      6. Default          : text
    """
    import re

    font_info = font_info or {}
    stripped = text.strip()

    if re.match(r"^\d{1,2}(\.\d{1,2})*\.?\s+.{1,}", stripped):
        return "heading"

    if len(stripped) <= 80 and stripped.isupper() and len(stripped) >= 3:
        return "heading"

    if re.match(r"^[–\-•◦]\s+", stripped):
        return "listitem"
    if re.match(r"^\d{1,2}[)\s]\s+", stripped):
        return "listitem"

    font_size = font_info.get("size", 0)
    if isinstance(font_size, int | float) and font_size >= 14 and len(stripped) <= 100:
        return "heading"

    font_name = font_info.get("fontname", "")
    if isinstance(font_name, str) and "bold" in font_name.lower() and len(stripped) <= 100:
        return "heading"

    return "text"


# ─── textlayoutraw builder ────────────────────────────────────────────────────


def build_text_layout_raw(
    extraction: ExtractionResult,
    document_id: str,
    document_version_id: str,
) -> dict:
    """
    Convert ExtractionResult into the textlayoutraw JSON format.
    """
    elements_json = [
        {
            "element_id": e.element_id,
            "type": e.type,
            "text": e.text,
            "page": e.page,
            "bbox": e.bbox,
            "confidence": e.confidence,
            "clause_uid": None,
        }
        for e in extraction.elements
    ]

    tables_json = [{"page": t.page, "rows": t.rows} for t in extraction.tables]
    ocr_page_count = sum(1 for s in extraction.page_strategies.values() if s == "ocr")

    return {
        "document_version_id": document_version_id,
        "document_id": document_id,
        "elements": elements_json,
        "tables": tables_json,
        "metadata": {
            "pages": extraction.page_count,
            "strategy": extraction.strategy,
            "ocr_rate": round(ocr_page_count / max(extraction.page_count, 1), 3),
            "avg_ocr_confidence": round(extraction.avg_ocr_confidence, 3),
            "element_count": len(extraction.elements),
            "table_count": len(extraction.tables),
            "page_strategies": extraction.page_strategies,
            "errors": extraction.errors,
        },
    }
