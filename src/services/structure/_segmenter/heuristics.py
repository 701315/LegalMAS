# src/services/structure/_segmenter/heuristics.py

"""
Текстовые и контекстные эвристики boundary-позиции.

Содержит функции, определяющие:
- выглядит ли текст как заголовок;
- находится ли элемент в позиции, пригодной для boundary;
- есть ли рядом сброс нумерации, смена форматирования, сдвиг плотности;
- является ли текст mid-paragraph reference;
- выглядит ли текст как non-boundary блок (подписи, реквизиты).
"""

from __future__ import annotations

import re
from typing import Any

from services.structure.heading_features import (
    looks_like_body_sentence_title,
    looks_like_numeric_amount_continuation,
    looks_like_reference_led_clause_continuation,
    looks_like_substantive_clause_line,
)
from services.structure.heading_patterns import normalize_spaces, parse_raw_heading
from services.structure.heading_scoring import CandidateStatus, score_heading_candidate
from services.structure.models import SEGMENT_TYPE_APPENDIX

from .config import NEW_PAGE_HEADING_WINDOW
from .element_utils import (
    is_heading_candidate_element,
    is_list_item_element,
    is_non_boundary_element_type,
    page_offset,
    safe_page,
)
from .patterns import (
    APPENDIX_RE,
    REQUISITES_LINE_RE,
    SIGNATURE_LINE_RE,
    infer_segment_type_from_text,
)


def normalize_boundary_text(value: str | None) -> str:
    """Нормализует текст для сравнения boundary: lowercase + collapse whitespace."""
    return normalize_spaces(str(value or "")).strip().lower()


def safe_parse_heading(text: str) -> tuple[str, str] | None:
    """Разбирает текст на (uid, title) если он похож на пронумерованный заголовок.

    Поддерживает:
    - ``1.2.3 Title``
    - ``IV. Title``
    - ``A) Title``
    """
    text = normalize_spaces(text)
    if not text:
        return None

    match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", text)
    if match:
        return match.group(1), match.group(2)

    roman = re.match(r"^([IVXLCM]+)\.?\s+(.+)$", text, re.IGNORECASE)
    if roman:
        return roman.group(1), roman.group(2)

    letter = re.match(r"^([A-ZА-ЯЁ])[\.\)]\s+(.+)$", text, re.IGNORECASE)
    if letter:
        return letter.group(1), letter.group(2)

    return None


def is_heading_like(text: str) -> bool:
    """Определяет, выглядит ли текст как заголовок (heading-like)."""
    text = normalize_spaces(text)
    if not text:
        return False
    if looks_like_non_boundary_block(text):
        return False

    parsed = safe_parse_heading(text)
    if parsed:
        uid, title = parsed
        try:
            result = score_heading_candidate(uid=uid, title=title, raw_text=text)
            return result.status in (CandidateStatus.ACCEPTED, CandidateStatus.AMBIGUOUS)
        except Exception:
            pass

    words = text.split()
    if 1 <= len(words) <= 14 and len(text) <= 160:
        if text.isupper():
            return True
        if text.endswith(":"):
            return True
        if words[0][:1].isdigit():
            return True
        if APPENDIX_RE.match(text):
            return True

    return False


def is_boundary_position(
    elements: list[dict[str, Any]],
    index: int,
    text: str,
) -> bool:
    """Определяет, находится ли элемент в позиции, допустимой для boundary."""
    element = elements[index]
    offset = page_offset(elements, index)

    if offset < NEW_PAGE_HEADING_WINDOW:
        return True

    if is_heading_candidate_element(element):
        return True

    if is_list_item_element(element):
        return False

    if is_heading_like(text):
        return True

    if infer_segment_type_from_text(text) == SEGMENT_TYPE_APPENDIX and len(text.split()) <= 20:
        return True

    if looks_like_segment_start_context(elements, index):
        return True

    return False


def looks_like_mid_paragraph_reference(
    elements: list[dict[str, Any]],
    candidate_index: int,
    candidate_text: str,
    candidate_segment_type: str,
) -> bool:
    """Определяет, является ли кандидат inline-ссылкой внутри абзаца."""
    idx = candidate_index
    text = candidate_text.lower()

    if len(text.split()) > 24:
        return True

    parsed = parse_raw_heading(candidate_text)
    parsed_uid = parsed[0] if parsed else None
    parsed_title = parsed[1] if parsed else candidate_text
    bodyish_text = normalize_spaces(parsed_title or candidate_text)

    if looks_like_numeric_amount_continuation(bodyish_text):
        return True

    if looks_like_reference_led_clause_continuation(bodyish_text):
        return True

    if parsed_uid and looks_like_body_sentence_title(parsed_uid, bodyish_text):
        return True

    if looks_like_substantive_clause_line(bodyish_text) and page_offset(elements, idx) > 0:
        return True

    prev_text = ""
    if idx > 0:
        prev_text = normalize_spaces(str(elements[idx - 1].get("text", "") or "")).lower()

    next_text = ""
    if idx + 1 < len(elements):
        next_text = normalize_spaces(str(elements[idx + 1].get("text", "") or "")).lower()

    is_appendix_marker = candidate_segment_type == SEGMENT_TYPE_APPENDIX
    looks_compact_heading = len(candidate_text.split()) <= 16

    if prev_text and not prev_text.endswith((".", ":", ";")) and page_offset(elements, idx) > 0:
        if (
            ("appendix" in text or "приложение" in text or "акт" in text or "протокол" in text)
            and not looks_compact_heading
        ):
            return True

    if text.startswith(("see appendix", "see annex", "см. приложение", "согласно приложению")):
        return True

    if next_text and len(candidate_text.split()) > 10 and len(next_text.split()) > 10 and not is_appendix_marker:
        return True

    return False


def detect_local_numbering_reset(
    elements: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    """Обнаруживает сброс нумерации заголовков вокруг элемента."""
    prev_uids: list[str] = []
    next_uids: list[str] = []

    for i in range(max(0, index - 12), index):
        if is_non_boundary_element_type(elements[i]) or is_list_item_element(elements[i]):
            continue
        parsed = safe_parse_heading(normalize_spaces(str(elements[i].get("text", "") or "")))
        if parsed:
            prev_uids.append(parsed[0])

    for i in range(index, min(len(elements), index + 8)):
        if is_non_boundary_element_type(elements[i]) or is_list_item_element(elements[i]):
            continue
        parsed = safe_parse_heading(normalize_spaces(str(elements[i].get("text", "") or "")))
        if parsed:
            next_uids.append(parsed[0])

    if not prev_uids or not next_uids:
        return None

    prev_has_progression = any(uid not in {"1", "1.1", "I", "A"} for uid in prev_uids)
    next_has_reset = any(uid in {"1", "1.1", "I", "A"} for uid in next_uids)

    if prev_has_progression and next_has_reset:
        return {
            "prev_uids_sample": prev_uids[-5:],
            "next_uids_sample": next_uids[:5],
        }

    return None


def detect_formatting_shift(
    elements: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    """Обнаруживает визуальный сдвиг форматирования (caps, centered, font)."""
    current = elements[index]
    fmt = current.get("formatting") or {}
    if not isinstance(fmt, dict):
        return None

    is_all_caps = bool(fmt.get("is_all_caps"))
    is_centered = bool(fmt.get("is_centered"))
    font_size = fmt.get("font_size")

    strong_visual = (
        is_all_caps or is_centered or (isinstance(font_size, (int, float)) and font_size >= 13)
    )

    if strong_visual:
        return {
            "is_all_caps": is_all_caps,
            "is_centered": is_centered,
            "font_size": font_size,
        }

    return None


def detect_heading_density_shift(
    elements: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    """Обнаруживает резкий рост плотности заголовков после элемента."""
    before = 0
    after = 0

    for i in range(max(0, index - 8), index):
        if is_non_boundary_element_type(elements[i]) or is_list_item_element(elements[i]):
            continue
        if is_heading_candidate_element(elements[i]):
            before += 1
            continue
        text = normalize_spaces(str(elements[i].get("text", "") or ""))
        if text and is_heading_like(text):
            before += 1

    for i in range(index, min(len(elements), index + 8)):
        if is_non_boundary_element_type(elements[i]) or is_list_item_element(elements[i]):
            continue
        if is_heading_candidate_element(elements[i]):
            after += 1
            continue
        text = normalize_spaces(str(elements[i].get("text", "") or ""))
        if text and is_heading_like(text):
            after += 1

    if after >= before + 2 and after >= 2:
        return {"before": before, "after": after}

    return None


def looks_like_segment_start_context(
    elements: list[dict[str, Any]],
    index: int,
) -> bool:
    """Элемент находится в начале страницы (мало элементов до него на странице)."""
    current_page = safe_page(elements[index])

    before_same_page = 0
    for i in range(index - 1, -1, -1):
        if safe_page(elements[i]) != current_page:
            break
        before_same_page += 1

    return before_same_page <= 2


def looks_like_non_boundary_block(text: str) -> bool:
    """Текст является подписным / реквизитным блоком и не может быть boundary."""
    text = normalize_spaces(text)
    if not text:
        return True
    if SIGNATURE_LINE_RE.match(text):
        return True
    if REQUISITES_LINE_RE.match(text):
        return True
    return False

