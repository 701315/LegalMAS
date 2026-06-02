# src/services/structure/_segmenter/assembly.py

"""
Сборка сегментов из boundary-кандидатов.

Содержит:
- построение ``SegmentDocument`` из validated boundaries;
- назначение primary-сегмента;
- формирование scope_name;
- propagation segment metadata в элементы.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from services.structure.heading_patterns import normalize_spaces
from services.structure.models import (
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_TYPE_ACT,
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_INVOICE,
    SEGMENT_TYPE_PROTOCOL,
    SEGMENT_TYPE_UNKNOWN,
    SegmentDocument,
    make_segment_id,
)

from .confidence import confidence_label
from .element_utils import (
    is_list_item_element,
    is_non_boundary_element_type,
    safe_page,
)
from .heuristics import (
    is_heading_like,
    looks_like_non_boundary_block,
)
from .patterns import (
    APPENDIX_RE,
    extract_appendix_number,
    infer_segment_type_from_text,
)
from .element_utils import is_heading_candidate_element
from .types import BoundaryCandidate


def build_segments_from_candidates(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
    candidates: list[BoundaryCandidate],
) -> list[SegmentDocument]:
    """Строит список ``SegmentDocument`` из принятых boundary-кандидатов."""
    boundaries = [0] + [c.element_index for c in candidates]
    boundaries = sorted(set(boundaries))

    segments: list[SegmentDocument] = []

    for order, start_idx in enumerate(boundaries):
        end_idx = boundaries[order + 1] if order + 1 < len(boundaries) else len(elements)
        if start_idx >= end_idx:
            continue

        segment_slice = elements[start_idx:end_idx]
        page_start = safe_page(segment_slice[0]) if segment_slice else 1
        page_end = safe_page(segment_slice[-1]) if segment_slice else page_start

        if order == 0:
            boundary_candidate = None
            segment_type = _infer_first_segment_type(elements, candidates)
            segment_title = _infer_first_segment_title(elements)
            conf_score = 1.0 if segment_type == SEGMENT_TYPE_CONTRACT else 0.75
        else:
            boundary_candidate = next(
                (c for c in candidates if c.element_index == start_idx),
                None,
            )
            segment_type = boundary_candidate.segment_type if boundary_candidate else SEGMENT_TYPE_UNKNOWN
            segment_title = boundary_candidate.title if boundary_candidate else None
            conf_score = boundary_candidate.confidence_score if boundary_candidate else 0.60

        segment = SegmentDocument(
            segment_id=make_segment_id(document_id=document_id, segment_order=order),
            document_id=document_id,
            document_version_id=None,
            segment_order=order,
            segment_type=segment_type,
            segment_title=segment_title,
            page_start=page_start,
            page_end=page_end,
            element_start=start_idx,
            element_end=end_idx,
            confidence=confidence_label(conf_score),
            is_primary=False,
        )

        segment.segmentation_confidence_score = round(conf_score, 3)
        segment.segmentation_reasons = (
            list(boundary_candidate.reasons) if boundary_candidate else ["file_start"]
        )

        segments.append(segment)

    return segments


def assign_primary_segment(segments: list[SegmentDocument]) -> None:
    """Назначает один сегмент как primary."""
    if not segments:
        return

    for s in segments:
        s.is_primary = False

    contracts_high = [
        s
        for s in segments
        if s.segment_type == SEGMENT_TYPE_CONTRACT and s.confidence == SEGMENT_CONFIDENCE_HIGH
    ]
    if contracts_high:
        contracts_high[0].is_primary = True
        return

    contracts_any = [s for s in segments if s.segment_type == SEGMENT_TYPE_CONTRACT]
    if contracts_any:
        contracts_any[0].is_primary = True
        return

    segments[0].is_primary = True


def attach_scope_names(segments: list[SegmentDocument]) -> None:
    """Формирует ``scope_name`` для каждого сегмента по типу и порядку."""
    type_counters: dict[str, int] = defaultdict(int)

    for seg in segments:
        seg_type = seg.segment_type or SEGMENT_TYPE_UNKNOWN

        if seg_type == SEGMENT_TYPE_CONTRACT and seg.segment_order == 0:
            seg.scope_name = "main_contract"
            continue

        type_counters[seg_type] += 1

        appendix_number = extract_appendix_number(seg.segment_title or "")
        if seg_type == SEGMENT_TYPE_APPENDIX and appendix_number:
            normalized_num = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "_", appendix_number).strip("_")
            seg.scope_name = f"appendix_{normalized_num.lower()}"
            continue

        seg.scope_name = _generate_scope_name(
            segment_type=seg_type,
            index_within_type=type_counters[seg_type],
        )


def propagate_segment_metadata(
    *,
    elements: list[dict[str, Any]],
    segments: list[SegmentDocument],
) -> None:
    """Проставляет segment metadata в каждый элемент."""
    for seg in segments:
        for idx in range(seg.element_start, seg.element_end):
            if idx >= len(elements):
                continue

            el = elements[idx]
            el["segment_id"] = seg.segment_id
            el["segment_type"] = seg.segment_type
            el["segment_order"] = seg.segment_order
            el["scope"] = getattr(seg, "scope_name", None) or "unknown_scope"


def make_single_segment(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> SegmentDocument:
    """Создаёт единственный сегмент, покрывающий весь документ."""
    if elements:
        page_start = safe_page(elements[0])
        page_end = safe_page(elements[-1])
        inferred_type = _infer_first_segment_type(elements, [])
        if inferred_type == SEGMENT_TYPE_UNKNOWN:
            inferred_type = SEGMENT_TYPE_CONTRACT
        inferred_title = _infer_first_segment_title(elements)
    else:
        page_start = 1
        page_end = 1
        inferred_type = SEGMENT_TYPE_CONTRACT
        inferred_title = None

    segment = SegmentDocument(
        segment_id=make_segment_id(document_id=document_id, segment_order=0),
        document_id=document_id,
        document_version_id=None,
        segment_order=0,
        segment_type=inferred_type,
        segment_title=inferred_title,
        page_start=page_start,
        page_end=page_end,
        element_start=0,
        element_end=len(elements),
        confidence=SEGMENT_CONFIDENCE_HIGH,
        is_primary=True,
    )
    segment.scope_name = "main_contract"
    segment.segmentation_confidence_score = 1.0
    segment.segmentation_reasons = ["single_segment_mode"]
    return segment


# ── Внутренние helpers ────────────────────────────────────────────────────────

def _infer_first_segment_type(
    elements: list[dict[str, Any]],
    candidates: list[BoundaryCandidate],
) -> str:
    """Определяет тип первого сегмента (до первой boundary)."""
    if any(
        c.segment_type
        in {
            SEGMENT_TYPE_APPENDIX,
            SEGMENT_TYPE_AMENDMENT,
            SEGMENT_TYPE_ACT,
            SEGMENT_TYPE_INVOICE,
            SEGMENT_TYPE_PROTOCOL,
        }
        for c in candidates
    ):
        return SEGMENT_TYPE_CONTRACT

    for el in elements[:12]:
        if is_non_boundary_element_type(el):
            continue

        text = normalize_spaces(str(el.get("text", "") or "")).lower()
        if not text:
            continue

        if "contract" in text or "договор" in text or "agreement" in text:
            return SEGMENT_TYPE_CONTRACT

    return SEGMENT_TYPE_UNKNOWN


def _infer_first_segment_title(elements: list[dict[str, Any]]) -> str | None:
    """Извлекает заголовок первого сегмента из начальных элементов."""
    for idx, element in enumerate(elements[:10]):
        if is_non_boundary_element_type(element) or is_list_item_element(element):
            continue

        text = normalize_spaces(str(element.get("text", "") or ""))
        if not text:
            continue
        if len(text) > 240:
            continue
        if looks_like_non_boundary_block(text):
            continue

        if is_heading_candidate_element(element):
            return text

        if is_heading_like(text):
            return text

        if idx == 0 and len(text.split()) <= 20:
            return text

    return None


def _generate_scope_name(
    *,
    segment_type: str,
    index_within_type: int,
) -> str:
    """Генерирует scope_name вида ``{type}_{index}``."""
    segment_type = (segment_type or SEGMENT_TYPE_UNKNOWN).strip().lower()

    allowed = {
        SEGMENT_TYPE_CONTRACT,
        SEGMENT_TYPE_APPENDIX,
        SEGMENT_TYPE_ACT,
        SEGMENT_TYPE_AMENDMENT,
        SEGMENT_TYPE_INVOICE,
        SEGMENT_TYPE_PROTOCOL,
        SEGMENT_TYPE_UNKNOWN,
    }
    if segment_type not in allowed:
        segment_type = SEGMENT_TYPE_UNKNOWN

    segment_type = re.sub(r"[^a-z0-9_]+", "_", segment_type).strip("_") or "unknown"
    return f"{segment_type}_{index_within_type}"

