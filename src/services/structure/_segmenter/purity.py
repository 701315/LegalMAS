# src/services/structure/_segmenter/purity.py

"""
Post-segmentation purity recovery (Phase P1).

После первичной сегментации повторно сканирует каждый provisional-сегмент
на предмет сильных boundary-маркеров, которые были пропущены.

Механизмы безопасности:
- максимум ``PURITY_RESCAN_MAX_PASSES`` итераций;
- принимаются только кандидаты, отличные от текущего сегмента;
- переиспользуются те же правила валидации, что и в primary pass;
- конвергенция при отсутствии новых boundaries;
- respect ``suppression_context`` (P5).
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.structure.models import (
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_UNKNOWN,
    SegmentDocument,
)

from .artifacts import detect_repeated_page_artifacts
from .candidates import (
    collect_boundary_candidates,
    pick_stronger_boundary,
    validate_boundary_candidates,
)
from .assembly import build_segments_from_candidates
from .config import MIN_ELEMENTS_BETWEEN_BOUNDARIES, PURITY_RESCAN_MAX_PASSES
from .heuristics import normalize_boundary_text
from .patterns import extract_appendix_number
from .toc_suppression import BoundarySuppressionContext
from .types import BoundaryCandidate, BoundarySignal

logger = get_logger(__name__)


def _is_distinct_internal_boundary_candidate(
    *,
    segment: SegmentDocument,
    candidate: BoundaryCandidate,
    threshold: float,
) -> bool:
    """Проверяет, что internal-кандидат представляет новый логический документ,
    а не повторение заголовка текущего сегмента.
    """
    if candidate.confidence_score < threshold:
        return False

    if candidate.segment_type == SEGMENT_TYPE_UNKNOWN:
        return False

    candidate_title_norm = normalize_boundary_text(candidate.title or candidate.text)
    current_title_norm = normalize_boundary_text(segment.segment_title)

    if (
        candidate_title_norm
        and current_title_norm
        and candidate_title_norm == current_title_norm
    ):
        return False

    if (
        segment.segment_type == SEGMENT_TYPE_APPENDIX
        and candidate.segment_type == SEGMENT_TYPE_APPENDIX
    ):
        current_num = normalize_boundary_text(
            extract_appendix_number(segment.segment_title or "")
        )
        candidate_num = normalize_boundary_text(
            extract_appendix_number(candidate.title or candidate.text)
        )
        if current_num and candidate_num and current_num == candidate_num:
            return False

    relative_offset = candidate.element_index - segment.element_start
    if relative_offset < MIN_ELEMENTS_BETWEEN_BOUNDARIES:
        return False

    return True


def _merge_boundary_candidates(
    *,
    elements: list[dict[str, Any]],
    candidates: list[BoundaryCandidate],
    threshold: float,
) -> list[BoundaryCandidate]:
    """Объединяет и переваливирует кандидатов глобально."""
    if not candidates:
        return []

    by_index: dict[int, BoundaryCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda c: (c.element_index, -c.confidence_score),
    ):
        existing = by_index.get(candidate.element_index)
        if existing is None:
            by_index[candidate.element_index] = candidate
        else:
            by_index[candidate.element_index] = pick_stronger_boundary(
                existing, candidate
            )

    merged = validate_boundary_candidates(elements, list(by_index.values()))
    return [c for c in merged if c.confidence_score >= threshold]


def recover_segment_purity_candidates(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
    accepted_candidates: list[BoundaryCandidate],
    threshold: float,
    suppression_context: BoundarySuppressionContext | None = None,
) -> list[BoundaryCandidate]:
    """Post-segmentation purity recovery: ищет пропущенные boundaries внутри
    provisional-сегментов.
    """
    if not accepted_candidates:
        return accepted_candidates

    current_candidates = sorted(
        accepted_candidates,
        key=lambda c: (c.element_index, c.page),
    )

    for pass_num in range(PURITY_RESCAN_MAX_PASSES):
        provisional_segments = build_segments_from_candidates(
            document_id=document_id,
            elements=elements,
            candidates=current_candidates,
        )
        if not provisional_segments:
            return current_candidates

        existing_indices = {c.element_index for c in current_candidates}
        recovered_candidates: list[BoundaryCandidate] = []

        for segment in provisional_segments:
            seg_start = segment.element_start
            seg_end = segment.element_end
            segment_slice = elements[seg_start:seg_end]

            if len(segment_slice) <= MIN_ELEMENTS_BETWEEN_BOUNDARIES:
                continue

            local_artifacts = detect_repeated_page_artifacts(segment_slice)
            local_candidates = collect_boundary_candidates(
                segment_slice,
                artifacts=local_artifacts,
                suppression_context=suppression_context,
            )
            validated_local = validate_boundary_candidates(
                segment_slice, local_candidates
            )

            for local_candidate in validated_local:
                global_index = seg_start + local_candidate.element_index
                if global_index in existing_indices:
                    continue

                global_candidate = BoundaryCandidate(
                    element_index=global_index,
                    page=local_candidate.page,
                    text=local_candidate.text,
                    segment_type=local_candidate.segment_type,
                    title=local_candidate.title,
                    confidence_score=local_candidate.confidence_score,
                    confidence_label=local_candidate.confidence_label,
                    signals=local_candidate.signals + (
                        BoundarySignal(
                            name="segment_purity_recovery",
                            weight=0.0,
                            details={
                                "pass": pass_num + 1,
                                "provisional_segment_order": segment.segment_order,
                                "provisional_segment_type": segment.segment_type,
                            },
                        ),
                    ),
                    reasons=local_candidate.reasons + ("segment_purity_recovery",),
                    is_mid_page=local_candidate.is_mid_page,
                )

                if not _is_distinct_internal_boundary_candidate(
                    segment=segment,
                    candidate=global_candidate,
                    threshold=threshold,
                ):
                    continue

                recovered_candidates.append(global_candidate)

        if not recovered_candidates:
            return current_candidates

        merged_candidates = _merge_boundary_candidates(
            elements=elements,
            candidates=current_candidates + recovered_candidates,
            threshold=threshold,
        )

        merged_indices = {c.element_index for c in merged_candidates}
        if merged_indices == existing_indices:
            return current_candidates

        logger.info(
            "STRUCTURE segmenter_segment_purity_recovery_applied",
            extra={
                "document_id": document_id,
                "pass": pass_num + 1,
                "recovered_boundaries_count": len(merged_indices - existing_indices),
                "total_boundaries_count": len(merged_candidates),
            },
        )

        current_candidates = merged_candidates

    return current_candidates


