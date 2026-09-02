# src/services/structure/element_classifier/_classify_single.py

# src/services/structure/element_classifier/_classify_single.py
"""Ядро классификации одного элемента документа.

Содержит основную логику _classify_single_element с иерархией проверок.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.logging import get_logger
from services.structure.heading_patterns import parse_raw_heading
from services.structure.heading_features import (
    looks_like_numeric_amount_continuation,
    looks_like_reference_led_clause_continuation,
)



from services.structure.legal_heading_rules import numeric_uid_depth
from ._config import TOC_SCORE_STRONG, TOC_SCORE_WEAK
from ._detectors import (
    _heading_candidate_confidence,
    _is_roman_heading,
    _is_toc_header,
    _looks_like_list_item,
    _looks_like_page_artifact,
    _looks_like_requisites_block,
    _looks_like_signature_block,
    _looks_like_table_content,
    _looks_like_toc_false_positive,
    _looks_like_unknown_layout,
    _toc_line_score,
)
from ._page_stats import _relative_page_position
from ._text_utils import _normalize_text, _safe_int
from ._toc_context import _TocContext

logger = get_logger(__name__)

if TYPE_CHECKING:
    pass


# Константы типов элементов (локальные для этого модуля)
ELEMENT_TYPE_HEADING_CANDIDATE = "heading_candidate"
ELEMENT_TYPE_BODY_TEXT = "body_text"
ELEMENT_TYPE_TABLE_CONTENT = "table_content"
ELEMENT_TYPE_REQUISITES_BLOCK = "requisites_block"
ELEMENT_TYPE_SIGNATURE_BLOCK = "signature_block"
ELEMENT_TYPE_TOC_HEADER = "toc_header"
ELEMENT_TYPE_TOC_LINE = "toc_line"
ELEMENT_TYPE_POSSIBLE_TOC = "possible_toc"
ELEMENT_TYPE_TOC_FALSE_POSITIVE = "toc_false_positive"
ELEMENT_TYPE_LIST_ITEM = "list_item"
ELEMENT_TYPE_PAGE_ARTIFACT = "page_artifact"
ELEMENT_TYPE_UNKNOWN_LAYOUT = "unknown_layout"


def _classify_single_element(
    *,
    element: dict[str, Any],
    index: int,
    elements: list[dict[str, Any]],
    page_stats: dict[int, dict[str, float]],
    toc_ctx: _TocContext,
):
    """Классифицирует один элемент.

    Args:
        element: Элемент для классификации
        index: Индекс элемента в списке
        elements: Полный список элементов (для доступа к соседям)
        page_stats: Статистика по страницам
        toc_ctx: TOC-контекст

    Returns:
        ClassificationResult с типом и уверенностью
    """
    # Импорт внутри функции для избежания циклических зависимостей
    from ._classify_reason import ClassificationReason, ClassificationResult

    original_text = str(element.get("text") or "").strip()
    text = _normalize_text(original_text)
    raw_type = str(element.get("type") or "").strip().lower() or None
    raw_label = str(element.get("label") or "").strip().lower() or None

    is_table = bool(element.get("is_table")) or raw_type == "table" or raw_label == "table"

    top_ratio, bottom_ratio = _relative_page_position(element, page_stats)
    page = _safe_int(element.get("page"), default=1)

    # 1. Пустой текст
    if not text:
        return ClassificationResult(
            element_type=ELEMENT_TYPE_UNKNOWN_LAYOUT,
            confidence=0.55,
            reasons=[ClassificationReason("empty_text", 0.55, "Empty or whitespace-only text")],
            raw_type=raw_type,
        )

    reasons: list[ClassificationReason] = []

    # 2. Page artifact
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

    # 3. TOC header
    if _is_toc_header(text):
        toc_ctx.header_seen = True
        toc_ctx.header_page = page
        reasons.append(ClassificationReason("toc_header", 0.98, "Explicit TOC header detected"))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_TOC_HEADER,
            confidence=0.98,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 4. TOC line scoring с contextual boost
    toc_score, toc_score_reasons = _toc_line_score(text)

    prev_text = _normalize_text(str(elements[index - 1].get("text") or "")) if index > 0 else ""
    next_text = (
        _normalize_text(str(elements[index + 1].get("text") or ""))
        if index + 1 < len(elements)
        else ""
    )

    contextual_boost = 0.0

    # Boost если рядом TOC header на той же или следующей странице
    if (
        toc_ctx.header_seen
        and toc_ctx.header_page is not None
        and page in {toc_ctx.header_page, toc_ctx.header_page + 1}
    ):
        contextual_boost += 0.06

    # Boost если соседи — сильные TOC lines
    if (
        _is_toc_header(prev_text)
        or _looks_like_toc_line(prev_text)
        or _looks_like_toc_line(next_text)
    ):
        contextual_boost += 0.06

    toc_score = min(1.0, toc_score + contextual_boost)

    # Сильный TOC signal
    if toc_score >= TOC_SCORE_STRONG:
        toc_ctx.recent_strong_toc_indexes.append(index)
        toc_ctx.recent_strong_toc_indexes[:] = toc_ctx.recent_strong_toc_indexes[-8:]

        for reason_code in toc_score_reasons:
            reasons.append(
                ClassificationReason(
                    f"toc_signal:{reason_code}", toc_score, "Strong TOC line signal"
                )
            )
        if contextual_boost > 0:
            reasons.append(
                ClassificationReason(
                    "toc_contextual_boost",
                    contextual_boost,
                    "Nearby TOC header or strong TOC line increased confidence",
                )
            )

        if _looks_like_toc_false_positive(text):
            reasons.append(
                ClassificationReason(
                    "toc_false_positive_local",
                    0.86,
                    "Line has substantive/body-like signals despite high TOC score",
                )
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_TOC_FALSE_POSITIVE,
                confidence=0.86,
                reasons=reasons,
                raw_type=raw_type,
                metadata={
                    "toc_semantic_role": "toc_false_positive",
                    "toc_score": round(toc_score, 3),
                },
            )

        return ClassificationResult(
            element_type=ELEMENT_TYPE_TOC_LINE,
            confidence=round(toc_score, 3),
            reasons=reasons,
            raw_type=raw_type,
            metadata={
                "toc_semantic_role": "toc_line",
                "toc_score": round(toc_score, 3),
            },
        )

    # Средний TOC signal
    if TOC_SCORE_WEAK <= toc_score < TOC_SCORE_STRONG:
        for reason_code in toc_score_reasons:
            reasons.append(
                ClassificationReason(
                    f"possible_toc_signal:{reason_code}",
                    toc_score,
                    "Weak or partial TOC signal",
                )
            )
        if contextual_boost > 0:
            reasons.append(
                ClassificationReason(
                    "possible_toc_contextual_boost",
                    contextual_boost,
                    "Nearby TOC context slightly increased confidence",
                )
            )

        if _looks_like_toc_false_positive(text):
            reasons.append(
                ClassificationReason(
                    "possible_toc_false_positive_local",
                    0.80,
                    "Weak TOC signal overridden by substantive/body-like features",
                )
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_TOC_FALSE_POSITIVE,
                confidence=0.80,
                reasons=reasons,
                raw_type=raw_type,
                metadata={
                    "toc_semantic_role": "toc_false_positive",
                    "toc_score": round(toc_score, 3),
                },
            )

        return ClassificationResult(
            element_type=ELEMENT_TYPE_POSSIBLE_TOC,
            confidence=round(toc_score, 3),
            reasons=reasons,
            raw_type=raw_type,
            metadata={
                "toc_semantic_role": "possible_toc",
                "toc_score": round(toc_score, 3),
            },
        )

    # 5. Signature block
    if _looks_like_signature_block(text):
        reasons.append(
            ClassificationReason(
                "signature_keywords", 0.94, "Contains signature/seal/representative markers"
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_SIGNATURE_BLOCK,
            confidence=0.94,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 6. Requisites block
    if _looks_like_requisites_block(text):
        reasons.append(
            ClassificationReason(
                "requisites_keywords", 0.93, "Contains requisites/banking/address identifiers"
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_REQUISITES_BLOCK,
            confidence=0.93,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 6.5 Strong numeric heading override
    #
    # Universal rule for legal docs:
    # if extractor already marked the element as heading
    # AND parse_raw_heading() extracts a plausible numeric uid of depth >= 2,
    # this element must stay in heading pipeline and must not be downgraded
    # to table_content/list_item by downstream weak heuristics.
    #
    # This protects clauses like:
    #   2.1 В соответствии ...
    #   5.1 В том случае ...
    #   6.3 В случае нарушения ...
    #   7.1.1 ...
    #   7.1.2 ...
    #   7.3.3 ...
    parsed_heading = parse_raw_heading(text)
    parsed_uid = parsed_heading[0] if parsed_heading else None
    parsed_title = parsed_heading[1] if parsed_heading else ""

    # 6.4 Hard negative demotion for numeric false positives
    #
    # Universal production rule:
    # if a parsed numeric prefix is followed by an amount-like continuation
    # or by a reference-led sentence continuation, this is body text rather
    # than a structural heading candidate.
    #
    # Important:
    # - this is NOT document-specific;
    # - we demote to body_text BEFORE heading override logic fires.
    if parsed_uid and parsed_title:
        is_amount_tail = looks_like_numeric_amount_continuation(parsed_title)
        is_reference_led = looks_like_reference_led_clause_continuation(parsed_title)

        if is_amount_tail or is_reference_led:
            reason_code = (
                "numeric_amount_continuation_after_uid"
                if is_amount_tail
                else "reference_led_clause_continuation_after_uid"
            )
            reason_text = (
                "Parsed numeric prefix is followed by amount-like continuation"
                if is_amount_tail
                else "Parsed numeric prefix is followed by reference-led body continuation"
            )
            confidence = 0.86 if raw_type == "heading" else 0.80
            reasons.append(
                ClassificationReason(
                    reason_code,
                    confidence,
                    reason_text,
                )
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_BODY_TEXT,
                confidence=confidence,
                reasons=reasons,
                raw_type=raw_type,
                metadata={
                    "parsed_uid": parsed_uid,
                    "demoted_from_numeric_heading": True,
                    "demotion_reason": reason_code,
                },
            )

    if raw_type == "heading" and parsed_uid:
        uid_depth = numeric_uid_depth(parsed_uid)
        if (
            uid_depth >= 2
            and not looks_like_reference_led_clause_continuation(parsed_title)
            and not looks_like_numeric_amount_continuation(parsed_title)
        ):
            heading_conf = _heading_candidate_confidence(text=original_text, raw_type=raw_type)
            reasons.append(
                ClassificationReason(
                    "extractor_numeric_heading_override",
                    max(heading_conf, 0.90),
                    "Extractor marked element as heading and parser found numeric clause uid",
                )
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_HEADING_CANDIDATE,
                confidence=round(max(heading_conf, 0.90), 3),
                reasons=reasons,
                raw_type=raw_type,
                metadata={
                    "parsed_uid": parsed_uid,
                    "numeric_heading_evidence": True,
                    "numeric_heading_evidence_source": "raw_heading_parser",
                },
            )

    # 7. Table content
    if is_table or _looks_like_table_content(text):
        reasons.append(
            ClassificationReason(
                "table_structure", 0.83, "Looks like row-like or delimiter-heavy table content"
            )
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_TABLE_CONTENT,
            confidence=0.83,
            reasons=reasons,
            raw_type=raw_type,
            metadata={
                "table_detection_source": "layout" if is_table else "text_shape",
            },
        )

    # 8. List item (с защитой от ложной классификации римских заголовков)
    is_list_by_raw_type = raw_type in {"listitem", "list_item"}
    is_list_by_regex = _looks_like_list_item(original_text)

    if is_list_by_raw_type or is_list_by_regex:
        # Если это универсальный заголовок, возвращаем HEADING_CANDIDATE напрямую.
        # Не проваливаемся в _heading_candidate_confidence, т.к. строгий скоринг
        # отвергнет текст с raw_type="list_item".
        if _is_roman_heading(original_text):
            logger.info(
                "Universal heading detected (uppercase/roman), overriding list_item",
                element_id=element.get("element_id"),
                text=text[:80],
                previous_label=raw_type,
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_HEADING_CANDIDATE,
                confidence=0.85,  # Высокая уверенность для ALL CAPS заголовков
                reasons=[
                    ClassificationReason(
                        "universal_heading_override", 
                        0.85, 
                        "Matches universal heading fallback (uppercase, short, no terminal punctuation)"
                    )
                ],
                raw_type=raw_type,
            )
        else:
            conf = 0.9 if is_list_by_raw_type else 0.82
            reasons.append(
                ClassificationReason(
                    "list_item_pattern", conf, "Extractor or regex indicates list item"
                )
            )
            return ClassificationResult(
                element_type=ELEMENT_TYPE_LIST_ITEM,
                confidence=conf,
                reasons=reasons,
                raw_type=raw_type,
            )
    # ── КОНЕЦ FIX ──────────────────────────────────────────────────────

    # 9. Heading candidate
    heading_conf = _heading_candidate_confidence(text=original_text, raw_type=raw_type)
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

    # 10. Unknown layout
    if _looks_like_unknown_layout(text):
        reasons.append(
            ClassificationReason("unknown_layout_noise", 0.72, "Noise-heavy or layout-broken line")
        )
        return ClassificationResult(
            element_type=ELEMENT_TYPE_UNKNOWN_LAYOUT,
            confidence=0.72,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 11. Default body text
    conf = 0.8 if raw_type == "text" else 0.7
    reasons.append(
        ClassificationReason("default_body_text", conf, "Falls back to ordinary body text")
    )
    return ClassificationResult(
        element_type=ELEMENT_TYPE_BODY_TEXT,
        confidence=conf,
        reasons=reasons,
        raw_type=raw_type,
    )


def _looks_like_toc_line(text: str) -> bool:
    """Вспомогательная функция для проверки TOC line (избегает циклических импортов)."""
    if not text:
        return False
    score, _ = _toc_line_score(text)
    return score >= TOC_SCORE_STRONG
