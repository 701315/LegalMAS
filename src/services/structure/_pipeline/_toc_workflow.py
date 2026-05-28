# src/services/structure/pipeline/_toc_workflow.py

"""
TOC workflow:
- suppression индексов
- parser status
- построение TOCDiagnostics
"""

from __future__ import annotations

from services.structure.models import (
    TOCDiagnostics,
    PARSE_QUALITY_OK,
    PARSE_QUALITY_WEAK,
)
from services.structure.toc_analysis import TOCAnalysisBundle
from services.structure.toc_guard import TOC_GUARD_RELIABLE


def compute_suppressed_indexes(
    *,
    elements: list[dict],
    analysis: TOCAnalysisBundle,
) -> set[int]:
    """
    Вычисляет индексы элементов, которые можно suppressed.
    """
    if not analysis.guard.suppress_body_elements:
        return set()

    if analysis.guard.decision != TOC_GUARD_RELIABLE:
        return set()

    entry_indexes: set[int] = set()

    for entry in analysis.parsed_toc.entries:
        for idx in (entry.source_element_indexes or []):
            if isinstance(idx, int) and idx >= 0:
                if idx not in analysis.guard.false_positive_indexes:
                    entry_indexes.add(idx)

    if analysis.toc_block.start_index is not None:
        start = analysis.toc_block.start_index
        end = min(analysis.toc_block.end_index, len(elements))
        for idx in range(start, end):
            if elements[idx].get("element_type") == "toc_header":
                entry_indexes.add(idx)

    return {
        idx
        for idx in entry_indexes
        if elements[idx].get("element_type") in {"toc_header", "toc_line"}
    }


def resolve_parser_status(analysis: TOCAnalysisBundle) -> str:
    """
    Определяет parser_status.
    """
    if analysis.guard.suppress_body_elements:
        return PARSE_QUALITY_OK
    if analysis.reliability.confidence_band in {"partial", "low"}:
        return PARSE_QUALITY_WEAK
    return PARSE_QUALITY_OK


def build_toc_diagnostics(
    *,
    analysis: TOCAnalysisBundle,
    suppressed_indexes: set[int],
    body_recovered_count: int,
    guard_fp_count: int,
) -> TOCDiagnostics:
    """
    Строит TOCDiagnostics.
    """
    return TOCDiagnostics(
        detected=analysis.toc_block.detected,
        block_start_index=analysis.toc_block.start_index,
        block_end_index=analysis.toc_block.end_index,
        detection_reason=analysis.toc_block.reason,
        parsed_entries_total=analysis.alignment.entries_total,
        exact_matches=analysis.alignment.exact_matches,
        fuzzy_matches=analysis.alignment.fuzzy_matches,
        no_matches=analysis.alignment.no_matches,
        stale_entries=analysis.alignment.stale_entries,
        toc_alignment_score=analysis.alignment.toc_alignment_score,
        toc_partial_reliability=analysis.reliability.partial_reliability,
        toc_confidence_band=analysis.reliability.confidence_band,
        toc_guard_applied=True,
        toc_body_suppression_allowed=analysis.guard.suppress_body_elements,
        toc_false_positive_count=guard_fp_count,
        body_recovered_from_toc=body_recovered_count,
        toc_skipped_elements=len(suppressed_indexes),
        parser_status=resolve_parser_status(analysis),
        parser_reasons=list(analysis.reliability.reasons),
    )

