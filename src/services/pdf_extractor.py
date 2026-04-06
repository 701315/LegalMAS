# src/services/pdf_extractor.py

"""
PDF Extraction Service.

Supports three strategies:
  - text:   pdfplumber for native-text PDFs (fast, high quality)
  - ocr:    Tesseract for scanned PDFs (slower, confidence-dependent)
  - hybrid: mix of text and OCR for partially scanned PDFs

Produces textlayoutraw — a list of elements (text blocks) with:
  - element_id  (deterministic, SHA-256 based)
  - type        (heading | text | listitem | table_cell)
  - text        (content)
  - page        (1-based)
  - bbox        [x0, top, x1, bottom]
  - confidence  (1.0 for pdfplumber, 0–1 for OCR)
  - strategy    (text | ocr)

Downstream consumers:
  - PII Sanitizer    (Stage 5): iterates elements
  - Structure Builder (Stage 6): uses element.type for clause detection
  - Classifier L2    (Stage 6): reads first 1500 chars from elements
  - Classifier L3    (Stage 6): embeds first 1000 chars
  - Runner / Retrieval (Stage 8): BM25 + embeddings over elements
"""

import time
import hashlib
import io
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


# ─── Main entry point ─────────────────────────────────────────────────────────


def extract_pdf(pdf_bytes: bytes, document_id: str) -> ExtractionResult:
    """
    Extract text and tables from a PDF document.
    """
    result = ExtractionResult()
    element_index = 0
    start_time = time.time()
    hard_timeout = getattr(settings, "EXTRACTION_HARD_TIMEOUT_SECONDS", 120)

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            result.page_count = len(pdf.pages)

            if result.page_count == 0:
                result.errors.append("PDF has 0 pages")
                return result

            if result.page_count > settings.EXTRACTION_MAX_PAGES:
                result.errors.append(
                    f"PDF has {result.page_count} pages, "
                    f"max {settings.EXTRACTION_MAX_PAGES}"
                )
                return result

            text_pages = ocr_pages = 0

            for page_num, page in enumerate(pdf.pages, start=1):
                # жёсткий таймаут на весь документ
                if time.time() - start_time > hard_timeout:
                    msg = (
                        f"Extraction hard timeout after {hard_timeout} seconds "
                        f"on page {page_num}"
                    )
                    logger.error(msg, document_id=document_id)
                    result.errors.append(msg)
                    break

                logger.debug(
                    "Extract: starting page",
                    document_id=document_id,
                    page=page_num,
                )

                strategy = _detect_page_strategy(page)
                result.page_strategies[page_num] = strategy.value

                if strategy == PageStrategy.TEXT:
                    page_elements = _extract_text_page(
                        page, document_id, page_num, element_index
                    )
                    result.elements.extend(page_elements)
                    element_index += len(page_elements)
                    text_pages += 1

                elif strategy == PageStrategy.OCR:
                    if is_ocr_available():
                        page_elements, page_conf = _extract_ocr_page(
                            pdf_bytes, page_num, document_id, element_index
                        )
                        result.elements.extend(page_elements)
                        element_index += len(page_elements)
                        result.ocr_confidences.append(page_conf)
                        ocr_pages += 1
                    else:
                        result.errors.append(
                            f"Page {page_num}: OCR required but Tesseract not available"
                        )

                page_tables = _extract_tables(page, page_num)
                result.tables.extend(page_tables)

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

    except Exception as e:
        result.errors.append(f"PDF parsing failed: {e}")
        logger.error("PDF extraction failed", error=str(e), document_id=document_id)

    # Дополнительная мягкая диагностика: формально валидный PDF без элементов
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
            # Small amount of text — likely headers/footers on a scan
            if hasattr(page, "images") and page.images:
                return PageStrategy.OCR
            return PageStrategy.EMPTY
        else:
            return PageStrategy.OCR
    except Exception:
        return PageStrategy.OCR


# ─── Text extraction (pdfplumber) ─────────────────────────────────────────────


def _extract_text_page(page: Any, document_id: str, page_num: int, start_index: int) -> list:
    """
    Extract text elements from a page using pdfplumber word grouping.
    Returns list[Element].
    """
    elements = []
    try:
        words = page.extract_words(
            keep_blank_chars=False,
            extra_attrs=["fontname", "size"],
        )
    except Exception:
        words = []

    if not words:
        return elements

    lines = _group_words_into_lines(words)
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
    return elements


# ─── OCR extraction (Tesseract) ───────────────────────────────────────────────


def _extract_ocr_page(pdf_bytes: bytes, page_num: int, document_id: str, start_index: int) -> tuple:
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
            return elements, 0.0

        image = images[0]
        ocr_data = pytesseract.image_to_data(
            image,
            lang="rus+eng",
            output_type=pytesseract.Output.DICT,
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

        # Last line
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
        confidence=round(avg_conf / 100.0, 3),  # Tesseract → 0–1
        strategy="ocr",
    ), avg_conf / 100.0


# ─── Table extraction ─────────────────────────────────────────────────────────


def _extract_tables(page: Any, page_num: int) -> list:
    """Extract tables from a page using pdfplumber."""
    tables = []
    try:
        page_tables = page.extract_tables()
        for table in page_tables:
            if table and any(any(cell for cell in row) for row in table):
                clean_rows = [
                    [cell.strip() if isinstance(cell, str) else cell for cell in row]
                    for row in table
                ]
                tables.append(TableData(page=page_num, rows=clean_rows))
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

    NOTE: These types are directly consumed by:
      - Structure Builder (Stage 6): regex matches on element.type == "heading"
        to detect clause boundaries and build clause_uid hierarchy
      - Classifier L2 (Stage 6): scans first 1500 chars;
        "heading" type helps detect document title
    """
    import re

    font_info = font_info or {}
    stripped = text.strip()

    # 1. Numeric headings: "1.", "1.1.", "1.1.1.", "12."
    if re.match(r"^\d{1,2}(\.\d{1,2})*\.?\s+.{1,}", stripped):
        return "heading"

    # 2. All-caps short text (likely a section title)
    if len(stripped) <= 80 and stripped.isupper() and len(stripped) >= 3:
        return "heading"

    # 3. List items
    if re.match(r"^[–\-•◦]\s+", stripped):
        return "listitem"
    if re.match(r"^\d{1,2}[)\s]\s+", stripped):
        return "listitem"

    # 4. Large font size → heading
    font_size = font_info.get("size", 0)
    if isinstance(font_size, int | float) and font_size >= 14 and len(stripped) <= 100:
        return "heading"

    # 5. Bold font → heading (if reasonably short)
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

    Schema:
      {
        "document_version_id": str,
        "document_id": str,
        "elements": [
          {
            "element_id":  str,      # deterministic, used by Structure Builder
            "type":        str,      # heading|text|listitem — used by Classifier/Runner
            "text":        str,
            "page":        int,
            "bbox":        [x0, top, x1, bottom],
            "confidence":  float,
            "clause_uid":  null      # filled by Structure Builder (Stage 6)
          }, ...
        ],
        "tables": [...],
        "metadata": {
          "pages":           int,
          "strategy":        str,
          "ocr_rate":        float,
          "avg_ocr_confidence": float,
          "element_count":   int,
          "table_count":     int,
          "page_strategies": dict,
          "errors":          list
        }
      }

    IMPORTANT: clause_uid is intentionally null at extraction time.
    Structure Builder (Stage 6) sets it after building the clause tree.
    Classifier (Stage 6) and Runner (Stage 8) rely on populated clause_uid
    for evidence citation and conditional check routing.
    """
    elements_json = [
        {
            "element_id": e.element_id,
            "type": e.type,
            "text": e.text,
            "page": e.page,
            "bbox": e.bbox,
            "confidence": e.confidence,
            "clause_uid": None,  # set by Structure Builder (Stage 6)
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

