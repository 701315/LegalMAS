# src/services/structure/_segmenter/candidates.py

"""
Сбор и валидация boundary-кандидатов.

Основной слой, который:
- сканирует элементы на предмет boundary markers;
- начисляет сигналы уверенности;
- валидирует кандидатов по proximity / conflict / mid-paragraph rules;
- поддерживает suppression context от P5/A3 (TOC / catalog pages, все boundary families).

V2-AWARE: Detects multilingual pipeline V2 format and creates additional
boundary candidates based on metadata.anchor_uid changes, without altering
legacy text-based detection logic. V2-кандидаты объединяются с legacy-кандидатами
после основного цикла сканирования.
"""

from __future__ import annotations

from typing import Any

from services.structure.heading_patterns import normalize_spaces
from services.structure.models import (
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_HEADING,
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
    detect_body_internal_boundary_listing,
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
    infer_boundary_family_from_text,
    infer_segment_title,
    infer_segment_type_from_text,
    match_boundary_marker,
)
from .toc_suppression import (
    BoundarySuppressionContext,
    _looks_like_substantive_body_line,
)
from .types import BoundaryCandidate, BoundarySignal


# ---------------------------------------------------------------------------
# V2 multilingual pipeline: anchor_uid-based boundary detection
# ---------------------------------------------------------------------------


def _is_v2_format(elements: list[dict[str, Any]]) -> bool:
    """
    Detect if elements are from multilingual pipeline V2.

    V2 format indicators: metadata contains "anchor_uid" or "source_element_id".
    Returns True if >= 30% of sampled elements match V2 pattern.
    """
    if not elements:
        return False

    sample_size = min(50, len(elements))
    v2_count = 0

    for el in elements[:sample_size]:
        if not isinstance(el, dict):
            continue
        metadata = el.get("metadata", {}) or {}
        element_id = str(el.get("element_id", "") or "")
        is_v2_id = element_id.startswith("seg_")
        has_anchor = "anchor_uid" in metadata
        has_source = "source_element_id" in metadata
        if has_anchor or (is_v2_id and has_source):
            v2_count += 1

    return (v2_count / sample_size) >= 0.3


def _infer_segment_type_from_anchor(anchor_uid: str) -> str:
    """Infer segment type from V2 anchor_uid (fallback: SEGMENT_TYPE_HEADING)."""
    anchor_lower = anchor_uid.lower()
    if "appendix" in anchor_lower or "приложение" in anchor_lower:
        return SEGMENT_TYPE_APPENDIX
    elif "amendment" in anchor_lower or "дополнение" in anchor_lower:
        return SEGMENT_TYPE_AMENDMENT
    elif anchor_uid in ("1", "1.0"):
        return SEGMENT_TYPE_CONTRACT
    return SEGMENT_TYPE_HEADING


def _infer_title_from_anchor(anchor_uid: str, element_text: str) -> str | None:
    """Extract segment title from V2 element text (short text = likely a heading)."""
    if element_text and len(element_text) < 200:
        return element_text[:100]
    return None


def _collect_v2_anchor_boundaries(
    elements: list[dict[str, Any]],
) -> list[BoundaryCandidate]:
    """
    Собирает boundary-кандидатов на основе смены metadata.anchor_uid (V2 only).

    Не заменяет legacy text-based detection — вызывается отдельно внутри
    collect_boundary_candidates() и результат объединяется с legacy-кандидатами.
    """
    candidates: list[BoundaryCandidate] = []
    prev_anchor_uid: str | None = None

    for idx, element in enumerate(elements):
        if not isinstance(element, dict):
            continue
        metadata = element.get("metadata", {}) or {}
        anchor_uid = metadata.get("anchor_uid")
        if not anchor_uid or anchor_uid == prev_anchor_uid:
            continue

        prev_anchor_uid = anchor_uid
        text = str(element.get("text", "") or "")
        segment_type = _infer_segment_type_from_anchor(anchor_uid)
        title = _infer_title_from_anchor(anchor_uid, text)

        candidates.append(
            BoundaryCandidate(
                element_index=idx,
                page=safe_page(element),
                text=text,
                segment_type=segment_type,
                title=title,
                confidence_score=0.95,
                confidence_label=confidence_label(0.95),
                signals=(
                    BoundarySignal(
                        name="v2_anchor_uid_change",
                        weight=0.95,
                        details={"anchor_uid": anchor_uid},
                    ),
                ),
                reasons=("v2_anchor_uid_change",),
                is_mid_page=False,
            )
        )

    return candidates


# ---------------------------------------------------------------------------
# Legacy: text-based boundary detection (unchanged from pre-V2 baseline)
# ---------------------------------------------------------------------------


def _is_part_of_local_swarm(
    elements: list[dict[str, Any]],
    candidate_index: int,
    boundary_family: str,
) -> bool:
    """Микро-защита от body-internal listings (Swarm Rule).

    Определяет, что кандидат является частью компактного inline-списка,
    а не настоящей segment boundary.

    Правила:
    - ищем только на той же странице, что и кандидат;
    - считаем только соседей в окне ±4 элемента;
    - между соседями не должно быть substantive body;
    - нужно минимум 2 других маркера того же семейства рядом,
      чтобы считать это стаей (избегаем false positive при 2 реальных
      appendix на соседних страницах).
    """
    candidate_page = safe_page(elements[candidate_index])
    window_left = max(0, candidate_index - 4)
    window_right = min(len(elements), candidate_index + 5)

    swarm_count = 0
    substantive_between = 0

    for i in range(window_left, window_right):
        if i == candidate_index:
            continue

        el = elements[i]

        if safe_page(el) != candidate_page:
            continue

        text = normalize_spaces(str(el.get("text", "") or ""))
        if not text:
            continue
        if looks_like_non_boundary_block(text):
            continue

        if infer_boundary_family_from_text(text) == boundary_family:
            swarm_count += 1
        elif is_non_boundary_element_type(el):
            continue
        else:
            if _looks_like_substantive_body_line(text):
                substantive_between += 1

    return swarm_count >= 2 and substantive_between == 0


def collect_boundary_candidates(
    elements: list[dict[str, Any]],
    artifacts: set[int] | None = None,
    suppression_context: BoundarySuppressionContext | None = None,
) -> list[BoundaryCandidate]:
    """Сканирует элементы и возвращает список boundary-кандидатов.

    Параметры:
        elements:             список layout-элементов документа.
        artifacts:            индексы running-header элементов для исключения.
        suppression_context:  P5/A3 suppression (TOC / catalog page detection,
                              все boundary families).

    V2-AWARE: дополнительно вызывает _collect_v2_anchor_boundaries() и объединяет
    результат с legacy text-based кандидатами. Legacy-логика ниже не изменена.
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
        boundary_family = infer_boundary_family_from_text(text)

        if (
            suppression_context is not None
            and suppression_context.suppresses_boundary_family(page, boundary_family)
        ):
            continue

        if boundary_family and _is_part_of_local_swarm(elements, idx, boundary_family):
            continue

        if not is_boundary_position(elements, idx, text):
            continue

        listing_guard = detect_body_internal_boundary_listing(
            elements=elements,
            candidate_index=idx,
            boundary_family=boundary_family,
        )
        if listing_guard is not None:
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

    # V2: добавляем anchor_uid-based кандидатов отдельно, не трогая legacy-логику выше.
    if _is_v2_format(elements):
        v2_candidates = _collect_v2_anchor_boundaries(elements)
        existing_indices = {c.element_index for c in candidates}
        candidates.extend(c for c in v2_candidates if c.element_index not in existing_indices)
        candidates.sort(key=lambda c: c.element_index)

    return candidates


def _is_strong_boundary_candidate(candidate: BoundaryCandidate) -> bool:
    """Кандидат достаточно сильный для сохранения при proximity-конфликте."""
    if candidate.segment_type == SEGMENT_TYPE_UNKNOWN:
        return False
    if candidate.confidence_score < DEFAULT_SEGMENT_CONFIDENCE_THRESHOLD:
        return False
    if "boundary_keyword" not in candidate.reasons and "v2_anchor_uid_change" not in candidate.reasons:
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

    if not (
        _is_strong_boundary_candidate(left) and _is_strong_boundary_candidate(right)
    ):
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
        left_num = normalize_boundary_text(
            extract_appendix_number(left.title or left.text)
        )
        right_num = normalize_boundary_text(
            extract_appendix_number(right.title or right.text)
        )
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

    if (
        left.segment_type == SEGMENT_TYPE_UNKNOWN
        and right.segment_type != SEGMENT_TYPE_UNKNOWN
    ):
        return right
    if (
        right.segment_type == SEGMENT_TYPE_UNKNOWN
        and left.segment_type != SEGMENT_TYPE_UNKNOWN
    ):
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

    for candidate in sorted(
        candidates, key=lambda c: (c.element_index, -c.confidence_score)
    ):
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
            if (
                candidate.element_index - prev.element_index
                < MIN_ELEMENTS_BETWEEN_BOUNDARIES
            ):
                if _should_keep_adjacent_distinct_boundaries(prev, candidate):
                    validated.append(candidate)
                    continue

                winner = pick_stronger_boundary(prev, candidate)
                validated[-1] = winner
                continue

        validated.append(candidate)

    return validated


    