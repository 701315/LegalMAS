# src/services/structure/element_classifier.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Public constants
# ============================================================================

ELEMENT_TYPE_HEADING_CANDIDATE = "heading_candidate"
ELEMENT_TYPE_BODY_TEXT = "body_text"
ELEMENT_TYPE_TABLE_CONTENT = "table_content"
ELEMENT_TYPE_REQUISITES_BLOCK = "requisites_block"
ELEMENT_TYPE_SIGNATURE_BLOCK = "signature_block"
ELEMENT_TYPE_TOC_CONTENT = "toc_content"
ELEMENT_TYPE_LIST_ITEM = "list_item"
ELEMENT_TYPE_PAGE_ARTIFACT = "page_artifact"
ELEMENT_TYPE_UNKNOWN_LAYOUT = "unknown_layout"

SUPPORTED_ELEMENT_TYPES = {
    ELEMENT_TYPE_HEADING_CANDIDATE,
    ELEMENT_TYPE_BODY_TEXT,
    ELEMENT_TYPE_TABLE_CONTENT,
    ELEMENT_TYPE_REQUISITES_BLOCK,
    ELEMENT_TYPE_SIGNATURE_BLOCK,
    ELEMENT_TYPE_TOC_CONTENT,
    ELEMENT_TYPE_LIST_ITEM,
    ELEMENT_TYPE_PAGE_ARTIFACT,
    ELEMENT_TYPE_UNKNOWN_LAYOUT,
}


# ============================================================================
# Language-specific configuration (RU-first, Sprint 1 scope)
# ============================================================================

BOUNDARY_KEYWORDS_RU = (
    "приложение",
    "акт",
    "дополнительное соглашение",
    "доп соглашение",
    "соглашение",
    "протокол",
)

TOC_HEADER_PATTERNS = (
    r"^содержание$",
    r"^оглавление$",
    r"^table of contents$",
    r"^contents$",
)

TOC_LINE_UID_PREFIX = (
    "1 ",
    "1.",
    "i ",
    "i.",
    "ii ",
    "ii.",
    "iii ",
    "iii.",
    "a ",
    "a.",
)

REQUISITES_KEYWORDS_RU = (
    "реквизиты",
    "реквизиты сторон",
    "юридический адрес",
    "почтовый адрес",
    "адрес местонахождения",
    "адрес для корреспонденции",
    "инн",
    "кпп",
    "огрн",
    "окпо",
    "оквэд",
    "банк",
    "бик",
    "корреспондентский счет",
    "корр. счет",
    "кор счет",
    "расчетный счет",
    "расчётный счёт",
    "р/с",
    "к/с",
    "iban",
    "swift",
    "e-mail",
    "email",
    "телефон",
    "тел.",
    "факс",
    "адрес",
)

SIGNATURE_KEYWORDS_RU = (
    "подписи сторон",
    "подписи",
    "подпись",
    "стороны подписали",
    "от заказчика",
    "от исполнителя",
    "от поставщика",
    "от покупателя",
    "от арендатора",
    "от арендодателя",
    "от подрядчика",
    "от заказчика:",
    "от исполнителя:",
    "генеральный директор",
    "директор",
    "уполномоченный представитель",
    "м.п.",
    "мп",
)

PAGE_ARTIFACT_PATTERNS = (
    r"^стр\.?\s*\d+\s*$",
    r"^страница\s+\d+\s*$",
    r"^page\s+\d+\s*$",
    r"^\d+\s*/\s*\d+\s*$",
    r"^-\s*\d+\s*-$",
    r"^\d+$",
)

DOT_LEADER_RE = re.compile(
    r"""
    (?:
        [\.\·•_]{3,}          # ..... or ___ or ···
        |
        (?:\.\s*){3,}         # . . . . .
    )
    """,
    re.VERBOSE,
)

UID_HEADING_RE = re.compile(
    r"""
    ^
    (?:
        \d{1,3}(?:\.\d{1,3})*\.?      # 1 / 1.2 / 1.2.3.
        |
        [IVXLCM]{1,8}\.?              # I. / II / IV
        |
        [A-ZА-ЯЁ]\)                   # A) / А)
        |
        [A-ZА-ЯЁ]\.                   # A. / А.
    )
    \s+
    .+
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

ROOT_HEADING_NO_DOT_RE = re.compile(
    r"""
    ^
    \d{1,3}
    \s+
    .{2,}
    $
    """,
    re.VERBOSE,
)

LIST_ITEM_RE = re.compile(
    r"""
    ^
    (?:
        [–\-•◦▪●]\s+                  # bullet
        |
        \d{1,3}[)\u00B0]\s+           # 1) / 1°
        |
        [A-ZА-ЯЁa-zа-яё][)\.]\s+      # a) / а) / A.
    )
    .+
    $
    """,
    re.VERBOSE,
)

ROMAN_LIST_ITEM_RE = re.compile(
    r"""
    ^
    [IVXLCM]{1,8}[)\.]
    \s+
    .+
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

NORMALIZE_NUM_SIGN_RE = re.compile(r"\b(?:№|N|No\.?)\s*")
WHITESPACE_RE = re.compile(r"\s+")
PUNCT_SPACES_RE = re.compile(r"\s*([:;,.])\s*")


# ============================================================================
# Data models
# ============================================================================

@dataclass(slots=True)
class ClassificationReason:
    code: str
    weight: float
    note: str


@dataclass(slots=True)
class ClassificationResult:
    element_type: str
    confidence: float
    reasons: list[ClassificationReason]
    raw_type: str | None = None


# ============================================================================
# Public API
# ============================================================================

def classify_elements(
    elements: list[dict[str, Any]] | None,
    *,
    document_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Rule-based secondary classification for STRUCTURE stage.

    Input:
        list[dict] with extractor fields such as:
        - element_id
        - type        (heading | text | listitem)
        - text
        - page
        - bbox
        - confidence

    Output:
        same list shape, but each element additionally gets:
        - element_type
        - raw_element_type
        - element_classification_confidence
        - element_classification_reasons

    Design principles:
    - deterministic;
    - conservative when uncertain;
    - never upgrades unknown/noisy text into heading_candidate aggressively;
    - signature/requisites/toc/page artifacts suppress downstream structure logic.
    """
    if not elements:
        return []

    prepared = [dict(el) for el in elements if isinstance(el, dict)]
    if not prepared:
        return []

    page_stats = _build_page_stats(prepared)

    classified: list[dict[str, Any]] = []
    toc_state = _TocState()

    for idx, element in enumerate(prepared):
        result = _classify_single_element(
            element=element,
            index=idx,
            elements=prepared,
            page_stats=page_stats,
            toc_state=toc_state,
        )

        normalized = dict(element)
        normalized["raw_element_type"] = str(element.get("type") or "").strip() or None
        normalized["element_type"] = result.element_type
        normalized["element_classification_confidence"] = round(result.confidence, 3)
        normalized["element_classification_reasons"] = [
            {
                "code": r.code,
                "weight": r.weight,
                "note": r.note,
            }
            for r in result.reasons
        ]

        classified.append(normalized)

    _log_classification_summary(document_id=document_id, classified=classified)
    return classified


# ============================================================================
# Internal helpers: page statistics
# ============================================================================

def _build_page_stats(elements: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    """
    Build lightweight page-level stats used for relative top/bottom detection.

    Since extractor currently does not provide page height/width in each element,
    we estimate page vertical span using observed bbox values on that page.
    """
    page_to_tops: dict[int, list[float]] = {}
    page_to_bottoms: dict[int, list[float]] = {}

    for el in elements:
        page = _safe_int(el.get("page"), default=1)
        bbox = _safe_bbox(el.get("bbox"))
        top = bbox[1]
        bottom = bbox[3]

        page_to_tops.setdefault(page, []).append(top)
        page_to_bottoms.setdefault(page, []).append(bottom)

    stats: dict[int, dict[str, float]] = {}
    for page in set(page_to_tops) | set(page_to_bottoms):
        tops = page_to_tops.get(page, [0.0])
        bottoms = page_to_bottoms.get(page, [0.0])
        min_top = min(tops) if tops else 0.0
        max_bottom = max(bottoms) if bottoms else 0.0
        span = max(max_bottom - min_top, 1.0)

        stats[page] = {
            "min_top": float(min_top),
            "max_bottom": float(max_bottom),
            "span": float(span),
        }

    return stats


def _relative_page_position(
    element: dict[str, Any],
    page_stats: dict[int, dict[str, float]],
) -> tuple[float, float]:
    """
    Returns (top_ratio, bottom_ratio), both in [0, 1]-ish range.
    Lower top_ratio means closer to page top.
    Lower bottom_ratio means closer to page bottom.
    """
    page = _safe_int(element.get("page"), default=1)
    bbox = _safe_bbox(element.get("bbox"))
    top = bbox[1]
    bottom = bbox[3]

    stats = page_stats.get(page) or {"min_top": 0.0, "max_bottom": max(bottom, 1.0), "span": 1.0}
    min_top = stats["min_top"]
    max_bottom = stats["max_bottom"]
    span = max(stats["span"], 1.0)

    top_ratio = (top - min_top) / span
    bottom_ratio = (max_bottom - bottom) / span
    return top_ratio, bottom_ratio


# ============================================================================
# Internal helpers: classifier
# ============================================================================

@dataclass(slots=True)
class _TocState:
    active: bool = False
    start_page: int | None = None
    last_toc_index: int | None = None
    consecutive_toc_lines: int = 0


def _classify_single_element(
    *,
    element: dict[str, Any],
    index: int,
    elements: list[dict[str, Any]],
    page_stats: dict[int, dict[str, float]],
    toc_state: _TocState,
) -> ClassificationResult:
    text = _normalize_text(str(element.get("text") or ""))
    raw_type = str(element.get("type") or "").strip().lower() or None
    bbox = _safe_bbox(element.get("bbox"))
    top_ratio, bottom_ratio = _relative_page_position(element, page_stats)
    page = _safe_int(element.get("page"), default=1)

    if not text:
        return ClassificationResult(
            element_type=ELEMENT_TYPE_UNKNOWN_LAYOUT,
            confidence=0.55,
            reasons=[ClassificationReason("empty_text", 0.55, "Empty or whitespace-only text")],
            raw_type=raw_type,
        )

    reasons: list[ClassificationReason] = []

    # 1. Hard suppressors first: page artifacts
    if _looks_like_page_artifact(text=text, top_ratio=top_ratio, bottom_ratio=bottom_ratio):
        reasons.append(
            ClassificationReason(
                "page_artifact_pattern",
                0.97,
                "Looks like page number/header/footer artifact near page edge",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_PAGE_ARTIFACT,
            confidence=0.97,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 2. TOC detection / TOC continuation
    if _is_toc_header(text):
        toc_state.active = True
        toc_state.start_page = page
        toc_state.last_toc_index = index
        toc_state.consecutive_toc_lines = 1
        reasons.append(
            ClassificationReason(
                "toc_header",
                0.98,
                "Explicit TOC header detected",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_TOC_CONTENT,
            confidence=0.98,
            reasons=reasons,
            raw_type=raw_type,
        )

    if _is_toc_line(text):
        if toc_state.active:
            toc_state.last_toc_index = index
            toc_state.consecutive_toc_lines += 1
            reasons.append(
                ClassificationReason(
                    "toc_line_after_toc_header",
                    0.95,
                    "TOC-like line while TOC mode is active",
                )
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_TOC_CONTENT,
                confidence=0.95,
                reasons=reasons,
                raw_type=raw_type,
            )

        prev_text = _normalize_text(str(elements[index - 1].get("text") or "")) if index > 0 else ""
        next_text = _normalize_text(str(elements[index + 1].get("text") or "")) if index + 1 < len(elements) else ""
        if _is_toc_header(prev_text) or _is_toc_line(prev_text) or _is_toc_line(next_text):
            toc_state.active = True
            toc_state.start_page = page
            toc_state.last_toc_index = index
            toc_state.consecutive_toc_lines = 1
            reasons.append(
                ClassificationReason(
                    "toc_line_cluster",
                    0.9,
                    "TOC-like line clustered with neighboring TOC content",
                )
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_TOC_CONTENT,
                confidence=0.9,
                reasons=reasons,
                raw_type=raw_type,
            )

    # Turn off TOC mode conservatively if current line is clearly not TOC-like
    if toc_state.active and not _is_toc_line(text):
        if not _looks_like_short_heading(text) and not _is_toc_header(text):
            toc_state.active = False

    # 3. Signature blocks
    if _looks_like_signature_block(text):
        reasons.append(
            ClassificationReason(
                "signature_keywords",
                0.94,
                "Contains signature/seal/representative markers",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_SIGNATURE_BLOCK,
            confidence=0.94,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 4. Requisites blocks
    if _looks_like_requisites_block(text):
        reasons.append(
            ClassificationReason(
                "requisites_keywords",
                0.93,
                "Contains requisites/banking/address identifiers",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_REQUISITES_BLOCK,
            confidence=0.93,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 5. Table-ish content (conservative, only obvious cases)
    if _looks_like_table_content(text):
        reasons.append(
            ClassificationReason(
                "table_structure",
                0.83,
                "Looks like row-like or delimiter-heavy table content",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_TABLE_CONTENT,
            confidence=0.83,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 6. List items
    if raw_type == "listitem" or _looks_like_list_item(text):
        reasons.append(
            ClassificationReason(
                "list_item_pattern",
                0.9 if raw_type == "listitem" else 0.82,
                "Extractor or regex indicates list item",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_LIST_ITEM,
            confidence=0.9 if raw_type == "listitem" else 0.82,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 7. Heading candidates
    heading_conf = _heading_candidate_confidence(text=text, raw_type=raw_type)
    if heading_conf >= 0.75:
        reasons.append(
            ClassificationReason(
                "heading_candidate",
                heading_conf,
                "Heading-like numbering, uppercase, or upstream heading label",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_HEADING_CANDIDATE,
            confidence=heading_conf,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 8. Unknown layout safeguards
    if _looks_like_unknown_layout(text):
        reasons.append(
            ClassificationReason(
                "unknown_layout_noise",
                0.72,
                "Noise-heavy or layout-broken line",
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_UNKNOWN_LAYOUT,
            confidence=0.72,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 9. Default body text
    reasons.append(
        ClassificationReason(
            "default_body_text",
            0.8 if raw_type == "text" else 0.7,
            "Falls back to ordinary body text",
        )
    )
    return ClassificationResult(
        element_type=ELEMENT_TYPE_BODY_TEXT,
        confidence=0.8 if raw_type == "text" else 0.7,
        reasons=reasons,
        raw_type=raw_type,
    )


# ============================================================================
# Pattern logic
# ============================================================================

def _normalize_text(text: str) -> str:
    text = text.replace("\u00A0", " ")
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = NORMALIZE_NUM_SIGN_RE.sub("№ ", text)
    text = PUNCT_SPACES_RE.sub(r"\1 ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _normalize_for_match(text: str) -> str:
    text = _normalize_text(text).lower()
    return text


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bbox(bbox: Any) -> list[float]:
    if not isinstance(bbox, (list, tuple)):
        return [0.0, 0.0, 0.0, 0.0]

    values = list(bbox[:4])
    while len(values) < 4:
        values.append(0.0)

    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except Exception:
            out.append(0.0)
    return out


def _is_toc_header(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(re.fullmatch(pattern, normalized) for pattern in TOC_HEADER_PATTERNS)


def _is_toc_line(text: str) -> bool:
    normalized = _normalize_text(text)
    normalized_lc = normalized.lower()

    if DOT_LEADER_RE.search(normalized):
        if re.search(r"\b\d{1,4}\s*$", normalized):
            return True

    if UID_HEADING_RE.match(normalized):
        # TOC line often ends with page number
        if re.search(r"\b\d{1,4}\s*$", normalized):
            return True

    # "1 Предмет договора 5" without dot leaders
    if ROOT_HEADING_NO_DOT_RE.match(normalized) and re.search(r"\b\d{1,4}\s*$", normalized):
        return True

    # Roman/letter prefixed TOC-like lines
    if any(normalized_lc.startswith(prefix) for prefix in TOC_LINE_UID_PREFIX):
        if re.search(r"\b\d{1,4}\s*$", normalized_lc):
            return True

    return False


def _looks_like_signature_block(text: str) -> bool:
    normalized = _normalize_for_match(text)

    if any(keyword in normalized for keyword in SIGNATURE_KEYWORDS_RU):
        return True

    # Typical sign line markers
    if "________________" in text or "________" in text:
        return True

    if re.search(r"/\s*подпись\s*/", normalized):
        return True

    if re.search(r"\bм\.?\s*п\.?\b", normalized):
        return True

    return False


def _looks_like_requisites_block(text: str) -> bool:
    normalized = _normalize_for_match(text)

    keyword_hits = sum(1 for kw in REQUISITES_KEYWORDS_RU if kw in normalized)
    if keyword_hits >= 2:
        return True

    # Dense colon-heavy fields are common in requisites blocks
    colon_count = text.count(":")
    if colon_count >= 2 and keyword_hits >= 1:
        return True

    # Banking/account identifiers
    if re.search(r"\b(инн|кпп|огрн|бик|iban|swift)\b", normalized):
        return True

    return False


def _looks_like_page_artifact(text: str, top_ratio: float, bottom_ratio: float) -> bool:
    normalized = _normalize_for_match(text)

    if any(re.fullmatch(pattern, normalized) for pattern in PAGE_ARTIFACT_PATTERNS):
        return top_ratio <= 0.08 or bottom_ratio <= 0.08

    # Very short repeated-like header/footer candidates near edges
    if len(normalized) <= 25 and (top_ratio <= 0.04 or bottom_ratio <= 0.04):
        if re.search(r"\b(договор|приложение|акт|страница|page)\b", normalized):
            return True

    return False


def _looks_like_table_content(text: str) -> bool:
    normalized = _normalize_text(text)

    if "|" in normalized and normalized.count("|") >= 2:
        return True

    if "\t" in text:
        return True

    # Semi-colon / delimiter dense row
    if normalized.count(";") >= 3:
        return True

    # Multi-cell numeric row shape
    tokens = normalized.split()
    numeric_tokens = sum(1 for t in tokens if re.fullmatch(r"[\d\.,/%()-]+", t))
    if len(tokens) >= 5 and numeric_tokens >= 3:
        return True

    return False


def _looks_like_list_item(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(LIST_ITEM_RE.match(normalized) or ROMAN_LIST_ITEM_RE.match(normalized))


def _looks_like_short_heading(text: str) -> bool:
    normalized = _normalize_text(text)
    if len(normalized) > 120:
        return False
    if UID_HEADING_RE.match(normalized):
        return True
    if ROOT_HEADING_NO_DOT_RE.match(normalized):
        return True
    if len(normalized) <= 80 and normalized.isupper():
        return True
    return False


def _heading_candidate_confidence(*, text: str, raw_type: str | None) -> float:
    normalized = _normalize_text(text)

    score = 0.0

    if raw_type == "heading":
        score += 0.45

    if UID_HEADING_RE.match(normalized):
        score += 0.35

    if ROOT_HEADING_NO_DOT_RE.match(normalized) and not _looks_like_list_item(normalized):
        score += 0.28

    if len(normalized) <= 80 and normalized.isupper() and len(normalized) >= 3:
        score += 0.18

    if any(keyword in _normalize_for_match(normalized) for keyword in BOUNDARY_KEYWORDS_RU):
        score += 0.08

    if _looks_like_signature_block(normalized) or _looks_like_requisites_block(normalized):
        score -= 0.35

    if _looks_like_list_item(normalized):
        score -= 0.30

    if _is_toc_line(normalized):
        score -= 0.40

    return max(0.0, min(score, 0.99))


def _looks_like_unknown_layout(text: str) -> bool:
    normalized = _normalize_text(text)

    if not normalized:
        return True

    # Noise-heavy OCR/layout garbage
    weird_ratio = sum(1 for ch in normalized if not (ch.isalnum() or ch.isspace() or ch in ".,:;!?()/-№\"'")) / max(len(normalized), 1)
    if weird_ratio >= 0.25:
        return True

    # Too many separators, too little lexical content
    if len(normalized) >= 12:
        alnum = sum(1 for ch in normalized if ch.isalnum())
        if alnum / len(normalized) < 0.35:
            return True

    return False


# ============================================================================
# Logging
# ============================================================================

def _log_classification_summary(
    *,
    document_id: str | None,
    classified: list[dict[str, Any]],
) -> None:
    counts: dict[str, int] = {}
    for el in classified:
        element_type = str(el.get("element_type") or ELEMENT_TYPE_UNKNOWN_LAYOUT)
        counts[element_type] = counts.get(element_type, 0) + 1

    logger.info(
        "STRUCTURE element classification completed",
        extra={
            "document_id": document_id,
            "elements_count": len(classified),
            "counts": counts,
        },
    )



    