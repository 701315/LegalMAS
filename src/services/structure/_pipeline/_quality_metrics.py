# src/services/structure/pipeline/_quality_metrics.py

"""
Метрики качества структуры и вспомогательные summary-функции.

Содержит:
- расчёт coverage узлов
- вычисление structural confidence
- сводки по headings
- сводки по element_type
- component-based confidence report
- quality gate mode selection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.config import settings
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.models import (
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
    FrozenHierarchyNode,
)

from ._utils import is_numeric_uid, stable_element_id

QUALITY_GATE_ALLOW_SECTION_CHUNKING = "ALLOW_SECTION_CHUNKING"
QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS = "ALLOW_SECTION_CHUNKING_WITH_WARNINGS"
QUALITY_GATE_ALLOW_HYBRID_CHUNKING = "ALLOW_HYBRID_CHUNKING"
QUALITY_GATE_BLOCK_AND_FALLBACK = "BLOCK_AND_FALLBACK"


@dataclass(slots=True)
class StructureConfidenceReport:
    confidence: str
    degraded: bool
    overall_score: float
    heading_confidence: float
    tree_consistency_confidence: float
    appendix_confidence: float
    crossref_anchor_confidence: float
    layout_quality_confidence: float
    reasons: list[str] = field(default_factory=list)
    gate_mode: str = QUALITY_GATE_BLOCK_AND_FALLBACK

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "degraded": self.degraded,
            "overall_score": round(self.overall_score, 4),
            "heading_confidence": round(self.heading_confidence, 4),
            "tree_consistency_confidence": round(self.tree_consistency_confidence, 4),
            "appendix_confidence": round(self.appendix_confidence, 4),
            "crossref_anchor_confidence": round(self.crossref_anchor_confidence, 4),
            "layout_quality_confidence": round(self.layout_quality_confidence, 4),
            "reasons": list(self.reasons),
            "gate_mode": self.gate_mode,
        }


def _clamp01(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def calculate_node_coverage(
    *,
    nodes: dict[str, FrozenHierarchyNode],
    elements: list[dict],
) -> float:
    """
    Доля элементов body, покрытых own_element_ids.
    """
    if not elements:
        return 0.0

    all_ids: set[str] = set()
    covered_ids: set[str] = set()

    for idx, el in enumerate(elements):
        all_ids.add(stable_element_id(el, idx))

    for node in nodes.values():
        covered_ids.update(node.own_element_ids or ())

    if not all_ids:
        return 0.0

    return len(all_ids & covered_ids) / len(all_ids)


def summarize_headings(headings: list[HeadingCandidate]) -> dict[str, Any]:
    """
    Лёгкая quality summary по принятым headings.
    """
    total = len(headings)
    if not total:
        return {
            "total": 0,
            "numeric_count": 0,
            "numeric_ratio": 0.0,
            "empty_title_count": 0,
            "scope_distribution": {},
        }

    numeric_count = 0
    empty_title_count = 0
    scope_distribution: dict[str, int] = {}

    for h in headings:
        raw_uid = str(getattr(h, "raw_uid", None) or h.uid or "").strip()
        title = str(h.title or "").strip()
        scope = str(getattr(h, "scope", None) or "unknown").strip() or "unknown"

        scope_distribution[scope] = scope_distribution.get(scope, 0) + 1

        if is_numeric_uid(raw_uid):
            numeric_count += 1
        if not title:
            empty_title_count += 1

    return {
        "total": total,
        "numeric_count": numeric_count,
        "numeric_ratio": numeric_count / total,
        "empty_title_count": empty_title_count,
        "scope_distribution": scope_distribution,
    }


def summarize_element_types(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Сводка по element_type.
    """
    counts: dict[str, int] = {}

    for el in elements:
        element_type = str(el.get("element_type") or "unknown").strip() or "unknown"
        counts[element_type] = counts.get(element_type, 0) + 1

    total = len(elements)
    toc_total = (
        counts.get("toc_header", 0)
        + counts.get("toc_line", 0)
        + counts.get("possible_toc", 0)
        + counts.get("toc_false_positive", 0)
    )

    return {
        "total": total,
        "counts": counts,
        "heading_candidates": counts.get("heading_candidate", 0),
        "body_text": counts.get("body_text", 0),
        "list_items": counts.get("list_item", 0),
        "toc_header": counts.get("toc_header", 0),
        "toc_line": counts.get("toc_line", 0),
        "possible_toc": counts.get("possible_toc", 0),
        "toc_false_positive": counts.get("toc_false_positive", 0),
        "toc_total": toc_total,
        "signature_blocks": counts.get("signature_block", 0),
        "requisites_blocks": counts.get("requisites_block", 0),
        "page_artifacts": counts.get("page_artifact", 0),
        "unknown_layout": counts.get("unknown_layout", 0),
    }


def _extract_evidence_metrics(structure_evidence: Any | None) -> dict[str, Any]:
    if structure_evidence is None:
        return {
            "present": False,
            "toc_detected": False,
            "main_chain_len": 0,
            "appendix_chain_len": 0,
            "crossref_anchor_count": 0,
            "appendix_marker_count": 0,
            "document_quality_signals": {},
        }

    try:
        global_signals = getattr(structure_evidence, "global_signals", None)
        return {
            "present": True,
            "toc_detected": bool(getattr(global_signals, "toc_detected", False)),
            "main_chain_len": int(getattr(global_signals, "main_section_chain_length", 0) or 0),
            "appendix_chain_len": int(getattr(global_signals, "appendix_chain_length", 0) or 0),
            "crossref_anchor_count": int(getattr(global_signals, "crossref_anchor_count", 0) or 0),
            "appendix_marker_count": len(getattr(structure_evidence, "appendix_markers", []) or []),
            "document_quality_signals": dict(
                getattr(global_signals, "document_quality_signals", {}) or {}
            ),
        }
    except Exception:
        return {
            "present": True,
            "toc_detected": False,
            "main_chain_len": 0,
            "appendix_chain_len": 0,
            "crossref_anchor_count": 0,
            "appendix_marker_count": 0,
            "document_quality_signals": {},
        }


def build_structure_confidence_report(
    *,
    coverage: float,
    headings_count: int = 0,
    numeric_ratio: float = 1.0,
    empty_title_count: int = 0,
    structure_degraded: bool = False,
    layout_degraded: bool = False,
    structure_evidence: Any | None = None,
    root_sections_count: int = 0,
    appendix_root_count: int = 0,
    cross_references_count: int = 0,
) -> StructureConfidenceReport:
    """
    Explainable component-based confidence report.

    Важно:
    - tree incomplete != document unstructured;
    - сильный TOC / numbering backbone / appendix chain должен поднимать confidence;
    - quality gate должен быть мягче, чем старый binary fallback.
    """
    reasons: list[str] = []
    coverage = _clamp01(coverage)

    evidence = _extract_evidence_metrics(structure_evidence)
    toc_detected = bool(evidence["toc_detected"])
    main_chain_len = int(evidence["main_chain_len"])
    appendix_chain_len = int(evidence["appendix_chain_len"])
    crossref_anchor_count = int(evidence["crossref_anchor_count"])
    appendix_marker_count = int(evidence["appendix_marker_count"])
    quality_signals = dict(evidence["document_quality_signals"] or {})

    heading_confidence = 0.0
    if headings_count <= 0:
        heading_confidence = 0.0
        reasons.append("no_headings_materialized")
    else:
        heading_confidence = 0.35
        if headings_count >= 3:
            heading_confidence += 0.15
        if headings_count >= 8:
            heading_confidence += 0.15
        if numeric_ratio >= 0.30:
            heading_confidence += 0.15
        if numeric_ratio >= 0.60:
            heading_confidence += 0.10
        if empty_title_count == 0:
            heading_confidence += 0.10
        elif empty_title_count >= max(2, headings_count // 2):
            reasons.append("too_many_empty_heading_titles")
            heading_confidence -= 0.20
    heading_confidence = _clamp01(heading_confidence)

    tree_consistency_confidence = coverage
    if root_sections_count >= 3:
        tree_consistency_confidence += 0.10
    if root_sections_count >= 8:
        tree_consistency_confidence += 0.10
    if structure_degraded:
        tree_consistency_confidence -= 0.30
        reasons.append("hierarchy_builder_marked_structure_degraded")
    if coverage < float(getattr(settings, "STRUCTURE_MIN_CLAUSE_COVERAGE", 0.55)):
        reasons.append("low_node_coverage")
    tree_consistency_confidence = _clamp01(tree_consistency_confidence)

    appendix_confidence = 0.0
    if appendix_root_count > 0 or appendix_chain_len > 0 or appendix_marker_count > 0:
        appendix_confidence = 0.40
        if appendix_chain_len >= 3:
            appendix_confidence += 0.25
        if appendix_root_count >= 1:
            appendix_confidence += 0.15
        if appendix_marker_count >= appendix_root_count and appendix_marker_count > 0:
            appendix_confidence += 0.10
    appendix_confidence = _clamp01(appendix_confidence)

    crossref_anchor_confidence = 0.0
    if crossref_anchor_count > 0:
        crossref_anchor_confidence = 0.45
        if crossref_anchor_count >= 3:
            crossref_anchor_confidence += 0.15
        if cross_references_count > 0:
            crossref_anchor_confidence += 0.20
        else:
            reasons.append("crossref_anchors_detected_but_not_resolved")
    elif cross_references_count > 0:
        crossref_anchor_confidence = 0.50
    crossref_anchor_confidence = _clamp01(crossref_anchor_confidence)

    layout_quality_confidence = 0.85
    if layout_degraded:
        layout_quality_confidence = 0.35
        reasons.append("layout_degraded")
    else:
        extraction_quality = quality_signals.get("extraction_quality_score")
        if extraction_quality is not None:
            try:
                layout_quality_confidence = _clamp01(float(extraction_quality))
            except Exception:
                layout_quality_confidence = 0.85

    if toc_detected and main_chain_len >= 5:
        reasons.append("strong_toc_and_main_chain_detected")
    elif toc_detected:
        reasons.append("toc_detected")
    if appendix_chain_len >= 3:
        reasons.append("appendix_chain_detected")
    if root_sections_count == 0 and main_chain_len >= 5:
        reasons.append("main_chain_detected_but_root_sections_not_materialized")
    if headings_count > 0 and structure_degraded:
        reasons.append("tree_incomplete_but_document_has_structure_signals")

    overall_score = (
        heading_confidence * 0.25
        + tree_consistency_confidence * 0.35
        + appendix_confidence * 0.10
        + crossref_anchor_confidence * 0.10
        + layout_quality_confidence * 0.20
    )
    overall_score = _clamp01(overall_score)

    if headings_count == 0:
        confidence = STRUCTURE_CONFIDENCE_FAILED
        degraded = True
        gate_mode = QUALITY_GATE_BLOCK_AND_FALLBACK
    elif overall_score >= 0.80 and not structure_degraded:
        confidence = STRUCTURE_CONFIDENCE_HIGH
        degraded = False
        gate_mode = QUALITY_GATE_ALLOW_SECTION_CHUNKING
    elif overall_score >= 0.58:
        confidence = STRUCTURE_CONFIDENCE_MEDIUM
        degraded = False
        gate_mode = (
            QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS
            if (toc_detected or main_chain_len >= 5 or root_sections_count >= 3)
            else QUALITY_GATE_ALLOW_HYBRID_CHUNKING
        )
    else:
        confidence = STRUCTURE_CONFIDENCE_LOW
        degraded = bool(structure_degraded)
        if toc_detected or main_chain_len >= 5 or appendix_chain_len >= 3:
            gate_mode = QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS
        elif headings_count >= 3:
            gate_mode = QUALITY_GATE_ALLOW_HYBRID_CHUNKING
        else:
            gate_mode = QUALITY_GATE_BLOCK_AND_FALLBACK

    if confidence in {STRUCTURE_CONFIDENCE_LOW, STRUCTURE_CONFIDENCE_FAILED} and not reasons:
        reasons.append("low_confidence_without_specific_explanation")

    return StructureConfidenceReport(
        confidence=confidence,
        degraded=degraded,
        overall_score=overall_score,
        heading_confidence=heading_confidence,
        tree_consistency_confidence=tree_consistency_confidence,
        appendix_confidence=appendix_confidence,
        crossref_anchor_confidence=crossref_anchor_confidence,
        layout_quality_confidence=layout_quality_confidence,
        reasons=list(dict.fromkeys(reasons)),
        gate_mode=gate_mode,
    )


def confidence_and_mode(
    coverage: float,
    *,
    layout_degraded: bool = False,
    headings_count: int = 0,
    numeric_ratio: float = 1.0,
    empty_title_count: int = 0,
    structure_degraded: bool = False,
    structure_evidence: Any | None = None,
    root_sections_count: int = 0,
    appendix_root_count: int = 0,
    cross_references_count: int = 0,
) -> tuple[str, bool]:
    """
    Backward-compatible wrapper.

    Возвращает (structural_confidence, degraded_flag), но считает их
    через новый component-based report.
    """
    report = build_structure_confidence_report(
        coverage=coverage,
        headings_count=headings_count,
        numeric_ratio=numeric_ratio,
        empty_title_count=empty_title_count,
        structure_degraded=structure_degraded,
        layout_degraded=layout_degraded,
        structure_evidence=structure_evidence,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
        cross_references_count=cross_references_count,
    )
    return report.confidence, report.degraded


