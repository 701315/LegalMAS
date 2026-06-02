# src/services/structure/_segmenter/candidates.py

"""
Сбор и валидация boundary-кандидатов.

Основной слой, который:
- сканирует элементы на предмет boundary markers;
- начисляет сигналы уверенности;
- валидирует кандидатов по proximity / conflict / mid-paragraph rules;
- поддерживает suppression context от P5 (TOC / appendix catalog pages).
"""

from __future__ import annotations

from typing import Any

from services.structure.heading_patterns import normalize_spaces
from services.structure.models import (
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_UNKNOWN,
)

from .config import (
    DEFAULT_SEGMENT_CONFIDENCE_THRESHOLD,
    MIN_ELEMENTS_BETWEEN_BOUNDARIES,
    WEAK_BOUNDARY_THRESHOLD,
)
from .confidence import confidence_label
from .element_utils import (
    is_heading_candidate_element,
    is_list_item_element,
    is_non_boundary_element_type,
    page_offset,
    safe_page,
)
from .heuristics import (
    detect_formatting_shift,
    detect_heading_density_shift,
    detect_local_numbering_reset,
    is_boundary_position,
    is_heading_like,
    looks_like_mid_paragraph_reference,
    looks_like_non_boundary_block,
    looks_like_segment_start_context,
    normalize_boundary_text,
)
from .patterns import (
    HORIZONTAL_RULE_RE,
    extract_appendix_number,
    infer_segment_title,
    infer_segment_type_from_text,
    match_boundary_marker,
)
from .toc_suppression import BoundarySuppressionContext
from .types import BoundaryCandidate, BoundarySignal


def collect_boundary_candidates(
    elements: list[dict[str, Any]],
    artifacts: set[int] | None = None,
    suppression_context: BoundarySuppressionContext | None = None,
) -> list[BoundaryCandidate]:
    """Сканирует элементы и возвращает список boundary-кандидатов.

    Параметры:
        elements:             список layout-элементов документа.
        artifacts:            индексы running-header элементов для исключения.
        suppression_context:  P5 suppression (TOC / catalog page detection).
    """
    artifacts = artifacts or set()
    candidates: list[BoundaryCandidate] = []

    appendix_series_seen = False

    for idx, element in enumerate(elements):
        if idx == 0:
            continue
        if idx in artifacts:
            continue

        raw_text = element.get("text", "")
        text = normalize_spaces(str(raw_text or ""))
        if not text:
            continue
        if HORIZONTAL_RULE_RE.match(text):
            continue
        if is_non_boundary_element_type(element):
            continue
        if looks_like_non_boundary_block(text):
            continue

        marker = match_boundary_marker(text)
        if not marker:
            continue

        page = safe_page(element)
        seg_type = infer_segment_type_from_text(text)

        # P5: подавление appendix-boundaries на TOC / catalog pages.
        if (
            suppression_context is not None
            and seg_type == SEGMENT_TYPE_APPENDIX
            and suppression_context.suppresses_appendix_page(page)
        ):
            continue

        if not is_boundary_position(elements, idx, text):
            continue

        signals: list[BoundarySignal] = []
        reasons: list[str] = []

        title = infer_segment_title(text)
        p_offset = page_offset(elements, idx)

        signals.append(
            BoundarySignal(
                name="boundary_keyword",
                weight=0.45,
                details={"marker": marker},
            )
        )
        reasons.append("boundary_keyword")

        if p_offset == 0:
            signals.append(
                BoundarySignal(
                    name="page_break",
                    weight=0.20,
                    details={"page_offset": p_offset},
                )
            )
            reasons.append("page_break")

        numbering_reset = detect_local_numbering_reset(elements, idx)
        if numbering_reset:
            signals.append(
                BoundarySignal(
                    name="numbering_reset",
                    weight=0.20,
                    details=numbering_reset,
                )
            )
            reasons.append("numbering_reset")

        formatting_shift = detect_formatting_shift(elements, idx)
        if formatting_shift:
            signals.append(
                BoundarySignal(
                    name="formatting_shift",
                    weight=0.10,
                    details=formatting_shift,
                )
            )
            reasons.append("formatting_shift")

        heading_density_shift = detect_heading_density_shift(elements, idx)
        if heading_density_shift:
            signals.append(
                BoundarySignal(
                    name="heading_density_shift",
                    weight=0.10,
                    details=heading_density_shift,
                )
            )
            reasons.append("heading_density_shift")

        if is_heading_like(text):
            signals.append(
                BoundarySignal(
                    name="heading_like_marker",
                    weight=0.05,
                    details={},
                )
            )
            reasons.append("heading_like_marker")

        if is_heading_candidate_element(element):
            signals.append(
                BoundarySignal(
                    name="element_type_heading_candidate",
                    weight=0.10,
                    details={"element_type": element.get("element_type")},
                )
            )
            reasons.append("element_type_heading_candidate")

        if is_list_item_element(element):
            signals.append(
                BoundarySignal(
                    name="element_type_list_item_penalty",
                    weight=-0.20,
                    details={"element_type": element.get("element_type")},
                )
            )
            reasons.append("element_type_list_item_penalty")

        if looks_like_segment_start_context(elements, idx):
            signals.append(
                BoundarySignal(
                    name="segment_start_context",
                    weight=0.10,
                    details={},
                )
            )
            reasons.append("segment_start_context")

        if seg_type == SEGMENT_TYPE_APPENDIX:
            appendix_number = extract_appendix_number(text)
            signals.append(
                BoundarySignal(
                    name="appendix_boundary",
                    weight=0.12,
                    details={"appendix_number": appendix_number},
                )
            )
            reasons.append("appendix_boundary")

            if not appendix_series_seen:
                signals.append(
                    BoundarySignal(
                        name="appendix_series_start",
                        weight=0.08,
                        details={},
                    )
                )
                reasons.append("appendix_series_start")
                appendix_series_seen = True

        score = max(0.0, min(sum(s.weight for s in signals), 1.0))

        candidates.append(
            BoundaryCandidate(
                element_index=idx,
                page=page,
                text=text,
                segment_type=seg_type,
                title=title,
                confidence_score=score,
                confidence_label=confidence_label(score),
                signals=tuple(signals),
                reasons=tuple(reasons),
                is_mid_page=(p_offset > 0),
            )
        )

    return candidates


def _is_strong_boundary_candidate(candidate: BoundaryCandidate) -> bool:
    """Кандидат достаточно сильный для сохранения при proximity-конфликте."""
    if candidate.segment_type == SEGMENT_TYPE_UNKNOWN:
        return False
    if candidate.confidence_score < DEFAULT_SEGMENT_CONFIDENCE_THRESHOLD:
        return False
    if "boundary_keyword" not in candidate.reasons:
        return False
    if len((candidate.text or "").split()) > 20:
        return False
    return True


def _should_keep_adjacent_distinct_boundaries(
    left: BoundaryCandidate,
    right: BoundaryCandidate,
) -> bool:
    """Сохраняет обе близкие границы, если они явно относятся к разным документам."""
    distance = right.element_index - left.element_index
    if distance < 2:
        return False

    if not (_is_strong_boundary_candidate(left) and _is_strong_boundary_candidate(right)):
        return False

    left_title_norm = normalize_boundary_text(left.title or left.text)
    right_title_norm = normalize_boundary_text(right.title or right.text)
    if not left_title_norm or not right_title_norm:
        return False
    if left_title_norm == right_title_norm:
        return False

    if (
        left.segment_type == SEGMENT_TYPE_APPENDIX
        and right.segment_type == SEGMENT_TYPE_APPENDIX
    ):
        left_num = normalize_boundary_text(extract_appendix_number(left.title or left.text))
        right_num = normalize_boundary_text(extract_appendix_number(right.title or right.text))
        if left_num and right_num and left_num != right_num:
            return True
        return False

    if left.segment_type != right.segment_type:
        return True

    return True


def pick_stronger_boundary(
    left: BoundaryCandidate,
    right: BoundaryCandidate,
) -> BoundaryCandidate:
    """Выбирает более сильного кандидата из двух конфликтующих."""
    if right.confidence_score > left.confidence_score:
        return right
    if right.confidence_score < left.confidence_score:
        return left

    left_has_page_break = any(s.name == "page_break" for s in left.signals)
    right_has_page_break = any(s.name == "page_break" for s in right.signals)
    if right_has_page_break and not left_has_page_break:
        return right
    if left_has_page_break and not right_has_page_break:
        return left

    left_has_reset = any(s.name == "numbering_reset" for s in left.signals)
    right_has_reset = any(s.name == "numbering_reset" for s in right.signals)
    if right_has_reset and not left_has_reset:
        return right
    if left_has_reset and not right_has_reset:
        return left

    if left.segment_type == SEGMENT_TYPE_UNKNOWN and right.segment_type != SEGMENT_TYPE_UNKNOWN:
        return right
    if right.segment_type == SEGMENT_TYPE_UNKNOWN and left.segment_type != SEGMENT_TYPE_UNKNOWN:
        return left

    return left


def validate_boundary_candidates(
    elements: list[dict[str, Any]],
    candidates: list[BoundaryCandidate],
) -> list[BoundaryCandidate]:
    """Валидирует и фильтрует кандидатов: proximity, mid-paragraph, threshold."""
    if not candidates:
        return []

    validated: list[BoundaryCandidate] = []

    for candidate in sorted(candidates, key=lambda c: (c.element_index, -c.confidence_score)):
        if candidate.element_index <= 0:
            continue

        if looks_like_mid_paragraph_reference(
            elements,
            candidate.element_index,
            candidate.text,
            candidate.segment_type,
        ):
            continue

        if candidate.confidence_score < WEAK_BOUNDARY_THRESHOLD:
            continue

        if validated:
            prev = validated[-1]
            if candidate.element_index - prev.element_index < MIN_ELEMENTS_BETWEEN_BOUNDARIES:
                if _should_keep_adjacent_distinct_boundaries(prev, candidate):
                    validated.append(candidate)
                    continue

                winner = pick_stronger_boundary(prev, candidate)
                validated[-1] = winner
                continue

        validated.append(candidate)

    return validated

