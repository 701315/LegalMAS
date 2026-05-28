# src/services/structure/pipeline/_core_builder.py

"""
Core builder: один сегмент → ClauseTree.
"""

from __future__ import annotations

import time
from typing import Any

from core.logging import get_logger
from services.structure.crossrefs import extract_references
from services.structure.element_classifier import annotate_elements_with_guard
from services.structure.heading_builder import build_heading_candidates
from services.structure.hierarchy_builder import build_clause_hierarchy
from services.structure.models import (
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_LOW,
    ClauseTree,
    ParseQualityDiagnostics,
    embed_parse_quality_diagnostics,
    embed_toc_diagnostics,
)
from services.structure.toc_analysis import analyze_toc_with_guard

from ._degraded_fallback import degraded_tree
from ._element_validation import validate_element_contract
from ._quality_metrics import (
    calculate_node_coverage,
    confidence_and_mode,
    summarize_headings,
)
from ._toc_workflow import (
    build_toc_diagnostics,
    compute_suppressed_indexes,
)
from ._utils import log_timing, stable_element_id

logger = get_logger(__name__)


def build_single_segment_tree(
    document_id: str,
    elements: list[dict],
    *,
    segment_id: str | None = None,
    segment_type: str | None = None,
    segment_title: str | None = None,
    segment_page_range: tuple[int, int] | None = None,
    segment_order: int | None = None,
    scope_name: str | None = None,
    is_primary_segment: bool = False,
    log_prefix: str = "STRUCTURE",
) -> ClauseTree:
    build_started = time.perf_counter()
    normalized_scope_name = str(scope_name or "main_contract").strip() or "main_contract"

    contract_valid, contract_violations = validate_element_contract(
        document_id=document_id,
        segment_id=segment_id,
        elements=elements,
    )

    if not contract_valid:
        return degraded_tree(
            document_id=document_id,
            elements=elements,
            structure_confidence=STRUCTURE_CONFIDENCE_FAILED,
            diagnostics={"contract_violations": contract_violations},
            scope_name=normalized_scope_name,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
        )

    t_h1 = time.perf_counter()
    headings_pre = build_heading_candidates(elements, document_id=document_id, toc_match_index=None)
    log_timing(f"{log_prefix} headings_pass_1", t_h1)

    if not headings_pre:
        return degraded_tree(
            document_id=document_id,
            elements=elements,
            structure_confidence=STRUCTURE_CONFIDENCE_LOW,
            scope_name=normalized_scope_name,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
        )

    analysis = analyze_toc_with_guard(elements, headings_pre, document_id=document_id)

    annotated_elements, body_recovered_count, guard_fp_count = annotate_elements_with_guard(
        elements, analysis.guard
    )

    suppressed_indexes = compute_suppressed_indexes(
        elements=annotated_elements,
        analysis=analysis,
    )

    body_elements = [
        el for idx, el in enumerate(annotated_elements) if idx not in suppressed_indexes
    ]

    headings = build_heading_candidates(
        body_elements,
        document_id=document_id,
        toc_match_index=analysis.toc_match_index,
    )

    toc_diag_obj = build_toc_diagnostics(
        analysis=analysis,
        suppressed_indexes=suppressed_indexes,
        body_recovered_count=body_recovered_count,
        guard_fp_count=guard_fp_count,
    )

    parse_quality_obj = ParseQualityDiagnostics(
        toc_diagnostics=toc_diag_obj,
    )

    root_nodes, nodes, element_to_effective_uid, structure_degraded = build_clause_hierarchy(
        headings=headings,
        elements=body_elements,
        document_id=document_id,
        stable_element_id_resolver=stable_element_id,
    )

    references = extract_references(
        elements=body_elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes,
        document_id=document_id,
        stable_element_id_resolver=stable_element_id,
    )

    coverage = calculate_node_coverage(nodes=nodes, elements=body_elements)
    heading_summary = summarize_headings(headings)

    confidence, degraded = confidence_and_mode(
        coverage,
        headings_count=heading_summary["total"],
        numeric_ratio=heading_summary["numeric_ratio"],
        empty_title_count=heading_summary["empty_title_count"],
        structure_degraded=structure_degraded,
    )

    diagnostics: dict[str, Any] = {}
    diagnostics = embed_toc_diagnostics(diagnostics, toc_diag_obj)
    diagnostics = embed_parse_quality_diagnostics(diagnostics, parse_quality_obj)

    if degraded and confidence in {STRUCTURE_CONFIDENCE_LOW, STRUCTURE_CONFIDENCE_FAILED}:
        return degraded_tree(
            document_id=document_id,
            elements=body_elements,
            coverage=coverage,
            structure_confidence=confidence,
            diagnostics=diagnostics,
            scope_name=normalized_scope_name,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
        )

    result = ClauseTree(
        document_id=document_id,
        root=root_nodes,
        references_index=references,
        structure_confidence=confidence,
        degraded=bool(structure_degraded),
        nodes_index=nodes,
        structure_diagnostics=diagnostics,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        segment_page_range=segment_page_range,
        segment_order=segment_order,
        scope_name=normalized_scope_name,
        is_primary_segment=is_primary_segment,
        schema_version="3.0",
    )

    log_timing(f"{log_prefix} build_total", build_started)
    return result
