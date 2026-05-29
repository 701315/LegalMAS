# src/services/structure/pipeline/_core_builder.py

"""
Core builder: один сегмент → ClauseTree.
"""

from __future__ import annotations

import time
from typing import Any

from core.logging import get_logger
from services.structure.crossrefs import build_cross_reference_graph
from services.structure.element_classifier import annotate_elements_with_guard
from services.structure.heading_builder import (
    build_heading_candidates,
    build_structure_evidence_bundle,
)
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
    QUALITY_GATE_ALLOW_HYBRID_CHUNKING,
    QUALITY_GATE_ALLOW_SECTION_CHUNKING,
    QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS,
    QUALITY_GATE_BLOCK_AND_FALLBACK,
    build_structure_confidence_report,
    calculate_node_coverage,
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
        diagnostics: dict[str, Any] = {
            "quality_gates": {
                "headings_pre_count": 0,
                "early_fallback_reason": "no_headings_in_pass_1",
                "section_chunking_allowed": False,
                "technical_fallback_only": True,
                "quality_gate_mode": QUALITY_GATE_BLOCK_AND_FALLBACK,
            }
        }
        return degraded_tree(
            document_id=document_id,
            elements=elements,
            structure_confidence=STRUCTURE_CONFIDENCE_LOW,
            diagnostics=diagnostics,
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

    evidence_bundle = build_structure_evidence_bundle(
        body_elements,
        document_id=document_id,
        toc_match_index=analysis.toc_match_index,
    )

    try:
        evidence_bundle.global_signals.toc_detected = bool(analysis.detected)
        evidence_bundle.global_signals.toc_confidence = float(
            analysis.reliability.partial_reliability or 0.0
        )
        evidence_bundle.global_signals.crossref_anchor_count = max(
            int(getattr(evidence_bundle.global_signals, "crossref_anchor_count", 0) or 0),
            len(getattr(evidence_bundle, "crossref_anchors", []) or []),
        )
        evidence_bundle.global_signals.document_quality_signals.update(
            {
                "toc_guard_decision": analysis.guard.decision,
                "toc_reliable": bool(analysis.reliability.is_reliable),
                "toc_confidence_band": str(analysis.reliability.confidence_band or "none"),
                "toc_partial_reliability": float(analysis.reliability.partial_reliability or 0.0),
                "suppressed_indexes_count": len(suppressed_indexes),
                "recoverable_indexes_count": len(analysis.guard.recoverable_indexes),
                "false_positive_indexes_count": len(analysis.guard.false_positive_indexes),
                "body_recovered_count": int(body_recovered_count),
                "guard_false_positive_count": int(guard_fp_count),
                "body_elements_count": len(body_elements),
                "original_elements_count": len(elements),
            }
        )
    except Exception:
        logger.exception(
            "STRUCTURE evidence_bundle_toc_enrichment_failed",
            extra={"document_id": document_id},
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
        structure_evidence=evidence_bundle,
    )

    cross_reference_graph = build_cross_reference_graph(
        elements=body_elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes,
        document_id=document_id,
        stable_element_id_resolver=stable_element_id,
    )

    coverage = calculate_node_coverage(nodes=nodes, elements=body_elements)
    heading_summary = summarize_headings(headings)

    diagnostics: dict[str, Any] = {}
    diagnostics = embed_toc_diagnostics(diagnostics, toc_diag_obj)
    diagnostics = embed_parse_quality_diagnostics(diagnostics, parse_quality_obj)

    toc_detected = bool(analysis.detected)
    toc_reliable = bool(analysis.reliability.is_reliable)
    toc_confidence_band = str(analysis.reliability.confidence_band or "none")
    toc_partial_reliability = float(analysis.reliability.partial_reliability or 0.0)

    main_chain_len = 0
    appendix_chain_len = 0
    crossref_anchor_candidates = 0
    evidence_heading_candidates_count = 0
    appendix_marker_count = 0
    toc_guard_decision = str(analysis.guard.decision or "reject_toc")

    try:
        main_chain_len = int(
            getattr(evidence_bundle.global_signals, "main_section_chain_length", 0) or 0
        )
        appendix_chain_len = int(
            getattr(evidence_bundle.global_signals, "appendix_chain_length", 0) or 0
        )
        crossref_anchor_candidates = int(
            getattr(evidence_bundle.global_signals, "crossref_anchor_count", 0) or 0
        )
        evidence_heading_candidates_count = int(
            getattr(evidence_bundle.global_signals, "heading_candidates_count", 0) or 0
        )
        appendix_marker_count = len(getattr(evidence_bundle, "appendix_markers", []) or [])
    except Exception:
        logger.exception(
            "STRUCTURE evidence_bundle_signal_read_failed",
            extra={"document_id": document_id},
        )

    root_sections_count = sum(
        1
        for node in root_nodes
        if str(getattr(node, "raw_uid", "") or "").strip().isdigit()
    )
    appendix_root_count = sum(
        1
        for node in root_nodes
        if str(getattr(node, "raw_uid", "") or "").strip().lower().startswith(
            ("appendix-", "приложение-")
        )
    )

    diagnostics["structure_evidence"] = {
        "toc_detected": toc_detected,
        "toc_guard_decision": toc_guard_decision,
        "toc_reliable": toc_reliable,
        "toc_confidence_band": toc_confidence_band,
        "toc_partial_reliability": round(toc_partial_reliability, 4),
        "main_section_chain_length": main_chain_len,
        "appendix_chain_length": appendix_chain_len,
        "crossref_anchor_candidates": crossref_anchor_candidates,
        "heading_candidates_count": evidence_heading_candidates_count,
        "appendix_marker_count": appendix_marker_count,
        "suppressed_indexes_count": len(suppressed_indexes),
        "body_recovered_count": int(body_recovered_count),
        "guard_false_positive_count": int(guard_fp_count),
    }

    quality_gates = diagnostics.setdefault("quality_gates", {})
    quality_gates.update(
        {
            "coverage": round(coverage, 4),
            "headings_count": heading_summary["total"],
            "numeric_ratio": round(heading_summary["numeric_ratio"], 4),
            "empty_title_count": heading_summary["empty_title_count"],
            "structure_degraded_from_builder": bool(structure_degraded),
            "toc_detected": toc_detected,
            "toc_reliable": toc_reliable,
            "toc_confidence_band": toc_confidence_band,
            "toc_partial_reliability": round(toc_partial_reliability, 4),
            "toc_guard_decision": toc_guard_decision,
            "root_sections_count": root_sections_count,
            "appendix_root_count": appendix_root_count,
            "main_section_chain_length": main_chain_len,
            "appendix_chain_length": appendix_chain_len,
            "crossref_anchor_candidates": crossref_anchor_candidates,
            "appendix_marker_count": appendix_marker_count,
            "cross_references_count": cross_reference_graph.stats.references_count,
        }
    )

    confidence_report = build_structure_confidence_report(
        coverage=coverage,
        headings_count=heading_summary["total"],
        numeric_ratio=heading_summary["numeric_ratio"],
        empty_title_count=heading_summary["empty_title_count"],
        structure_degraded=structure_degraded,
        structure_evidence=evidence_bundle,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
        cross_references_count=cross_reference_graph.stats.references_count,
    )

    confidence = confidence_report.confidence
    degraded = confidence_report.degraded
    gate_mode = confidence_report.gate_mode

    diagnostics["structure_confidence"] = confidence_report.to_dict()

    allow_semantic_tree_with_warnings = bool(root_nodes) and (
        gate_mode in {
            QUALITY_GATE_ALLOW_SECTION_CHUNKING,
            QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS,
            QUALITY_GATE_ALLOW_HYBRID_CHUNKING,
        }
    )

    quality_gates["allow_semantic_tree_with_warnings"] = allow_semantic_tree_with_warnings
    quality_gates["quality_gate_mode"] = gate_mode
    quality_gates["confidence_reasons"] = list(confidence_report.reasons)

    if gate_mode == QUALITY_GATE_BLOCK_AND_FALLBACK:
        quality_gates.update(
            {
                "section_chunking_allowed": False,
                "technical_fallback_only": True,
                "fallback_reason": "quality_gate_block_and_fallback",
                "semantic_tree_preserved_despite_low_confidence": False,
            }
        )
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

    if confidence in {STRUCTURE_CONFIDENCE_LOW, STRUCTURE_CONFIDENCE_FAILED} and allow_semantic_tree_with_warnings:
        quality_gates.update(
            {
                "section_chunking_allowed": True,
                "technical_fallback_only": False,
                "fallback_reason": None,
                "semantic_tree_preserved_despite_low_confidence": True,
            }
        )
    else:
        quality_gates.setdefault("semantic_tree_preserved_despite_low_confidence", False)
        quality_gates.setdefault(
            "section_chunking_allowed",
            gate_mode
            in {
                QUALITY_GATE_ALLOW_SECTION_CHUNKING,
                QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS,
                QUALITY_GATE_ALLOW_HYBRID_CHUNKING,
            },
        )
        quality_gates.setdefault("technical_fallback_only", False)
        quality_gates.setdefault("fallback_reason", None)

    quality_gates["final_mode"] = (
        "semantic_preserved_with_warnings"
        if quality_gates.get("semantic_tree_preserved_despite_low_confidence")
        else (
            "hybrid_chunking"
            if gate_mode == QUALITY_GATE_ALLOW_HYBRID_CHUNKING
            else "semantic_tree"
        )
    )

    result = ClauseTree(
        document_id=document_id,
        root=root_nodes,
        cross_reference_graph=cross_reference_graph,
        structure_confidence=confidence,
        degraded=bool(
            degraded
            and not quality_gates.get("semantic_tree_preserved_despite_low_confidence")
        ),
        nodes_index=nodes,
        structure_diagnostics=diagnostics,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        segment_page_range=segment_page_range,
        segment_order=segment_order,
        scope_name=normalized_scope_name,
        is_primary_segment=is_primary_segment,
        schema_version="4.0",
    )

    log_timing(f"{log_prefix} build_total", build_started)
    return result


