# src/services/structure/pipeline/_core_builder.py

"""
Core builder: один сегмент -> ClauseTree.

Архитектурные принципы:
- deterministic structure строится до policy/gating;
- quality assessment и gate policy считаются отдельно;
- technical fallback включается только если gate реально блокирует structure;
- сильная deterministic structure не должна теряться только из-за LOW confidence;
- orchestration не должен падать из-за неидеального evidence object / diagnostics object;
- backward compatibility сохраняется до завершения refactor Phases 2–7.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.telemetry._collector import TelemetryCollector

from core.logging import get_logger
from services.structure.crossrefs import (
    build_cross_reference_graph,
    build_cross_reference_graph_with_audit,
    CrossRefExtractionResult,
)
from services.structure.element_classifier import annotate_elements_with_guard
from services.structure.heading_builder import (
    build_heading_candidates,
    build_structure_evidence_bundle,
    run_phase2,
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
from ._record_heading_recovery import attempt_record_heading_recovery
from ._element_validation import validate_element_contract
from ._quality_metrics import (
    QUALITY_GATE_BLOCK_AND_FALLBACK,
    CrossRefAssessmentInput,
    EvidenceAssessmentInput,
    HierarchyAssessmentInput,
    StructureAssessment,
    StructureGateDecision,
    build_structure_confidence_report,
    calculate_node_coverage,
    compute_structure_assessment,
    decide_structure_gate,
    summarize_headings,
    _extract_evidence_metrics,
    _extract_crossref_input,
)
from ._toc_workflow import (
    build_toc_diagnostics,
    compute_suppressed_indexes,
)
from ._utils import log_timing, stable_element_id

logger = get_logger(__name__)


def _safe_len(value: Any) -> int:
    try:
        return len(value or [])
    except Exception:
        return 0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    try:
        if value is None:
            return default
        return bool(value)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


def _safe_round(value: Any, digits: int = 4, default: float = 0.0) -> float:
    return round(_safe_float(value, default=default), digits)


def _safe_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _is_appendix_like_text(value: Any) -> bool:
    normalized = _safe_str(value).strip().lower()
    if not normalized:
        return False
    return (
        normalized.startswith("appendix")
        or normalized.startswith("приложение")
        or normalized.startswith("annex")
        or normalized.startswith("schedule")
        or normalized.startswith("exhibit")
        or normalized.startswith("attachment")
    )


def _read_crossref_stats(graph: Any | None) -> dict[str, Any]:
    stats = getattr(graph, "stats", None)
    if stats is None:
        return {
            "references_count": 0,
            "unresolved_count": 0,
            "ambiguous_count": 0,
            "appendix_scoped_resolved_count": 0,
            "appendix_scope_miss_count": 0,
            "toc_like_reference_skipped_count": 0,
        }

    to_dict = getattr(stats, "to_dict", None)
    if callable(to_dict):
        raw = _safe_to_dict(to_dict())
    else:
        raw = {}

    return {
        "references_count": _safe_int(raw.get("references_count", getattr(stats, "references_count", 0))),
        "unresolved_count": _safe_int(raw.get("unresolved_count", getattr(stats, "unresolved_count", 0))),
        "ambiguous_count": _safe_int(raw.get("ambiguous_count", getattr(stats, "ambiguous_count", 0))),
        "appendix_scoped_resolved_count": _safe_int(
            raw.get(
                "appendix_scoped_resolved_count",
                getattr(stats, "appendix_scoped_resolved_count", 0),
            )
        ),
        "appendix_scope_miss_count": _safe_int(
            raw.get(
                "appendix_scope_miss_count",
                getattr(stats, "appendix_scope_miss_count", 0),
            )
        ),
        "toc_like_reference_skipped_count": _safe_int(
            raw.get(
                "toc_like_reference_skipped_count",
                getattr(stats, "toc_like_reference_skipped_count", 0),
            )
        ),
    }


def _read_evidence_signals(
    *,
    document_id: str,
    evidence_bundle: Any | None,
    analysis: Any,
    suppressed_indexes: set[int] | list[int],
    body_recovered_count: int,
    guard_fp_count: int,
    body_elements_count: int,
    original_elements_count: int,
) -> dict[str, Any]:
    """
    Аккуратно читает и нормализует structure evidence signals.

    Здесь не должно быть падений пайплайна из-за неидеального evidence object.
    Это transitional reader до полной formalization Phase 2 evidence contract.
    """
    result: dict[str, Any] = {
        "toc_detected": _safe_bool(getattr(analysis, "detected", False)),
        "toc_guard_decision": _safe_str(
            getattr(getattr(analysis, "guard", None), "decision", None),
            default="reject_toc",
        ) or "reject_toc",
        "toc_reliable": _safe_bool(
            getattr(getattr(analysis, "reliability", None), "is_reliable", False)
        ),
        "toc_confidence_band": _safe_str(
            getattr(getattr(analysis, "reliability", None), "confidence_band", None),
            default="none",
        ) or "none",
        "toc_partial_reliability": _safe_float(
            getattr(getattr(analysis, "reliability", None), "partial_reliability", 0.0),
            default=0.0,
        ),
        "main_section_chain_length": 0,
        "appendix_chain_length": 0,
        "crossref_anchor_candidates": 0,
        "heading_candidates_count": 0,
        "appendix_marker_count": 0,
        "suppressed_indexes_count": len(suppressed_indexes),
        "body_recovered_count": _safe_int(body_recovered_count),
        "guard_false_positive_count": _safe_int(guard_fp_count),
        "body_elements_count": _safe_int(body_elements_count),
        "original_elements_count": _safe_int(original_elements_count),
    }

    if evidence_bundle is None:
        return result

    try:
        global_signals = getattr(evidence_bundle, "global_signals", None)

        result["main_section_chain_length"] = _safe_int(
            getattr(global_signals, "main_section_chain_length", 0)
        )
        result["appendix_chain_length"] = _safe_int(
            getattr(global_signals, "appendix_chain_length", 0)
        )
        result["crossref_anchor_candidates"] = _safe_int(
            getattr(global_signals, "crossref_anchor_count", 0)
        )
        result["heading_candidates_count"] = _safe_int(
            getattr(global_signals, "heading_candidates_count", 0)
        )
        result["appendix_marker_count"] = _safe_len(
            getattr(evidence_bundle, "appendix_markers", None)
        )
    except Exception:
        logger.exception(
            "STRUCTURE evidence_bundle_signal_read_failed",
            extra={"document_id": document_id},
        )

    return result


def _enrich_evidence_bundle_immutable(
    *,
    document_id: str,
    evidence_bundle: Any | None,
    analysis: Any,
    suppressed_indexes: set[int] | list[int],
    body_recovered_count: int,
    guard_fp_count: int,
    body_elements_count: int,
    original_elements_count: int,
) -> Any | None:
    """
    Immutable enrichment evidence bundle TOC-related сигналами.

    Возвращает НОВЫЙ StructureEvidenceBundle с обновлёнными global_signals.
    Входной bundle НЕ мутируется.

    Заменяет _try_enrich_evidence_bundle_with_toc, которая мутировала
    global_signals напрямую. Теперь создаём новые объекты.

    Если bundle is None или enrichment не удался — возвращает входной bundle
    без изменений (pipeline не должен падать из-за enrichment).
    """
    if evidence_bundle is None:
        return evidence_bundle

    try:
        old_signals = getattr(evidence_bundle, "global_signals", None)
        if old_signals is None:
            return evidence_bundle

        # Читаем существующие значения из старого global_signals
        old_quality = _safe_to_dict(
            getattr(old_signals, "document_quality_signals", {}) or {}
        )

        # Строим обновлённый document_quality_signals
        new_quality = {
            **old_quality,
            "toc_guard_decision": _safe_str(
                getattr(getattr(analysis, "guard", None), "decision", None),
                default="reject_toc",
            ) or "reject_toc",
            "toc_reliable": _safe_bool(
                getattr(getattr(analysis, "reliability", None), "is_reliable", False)
            ),
            "toc_confidence_band": _safe_str(
                getattr(getattr(analysis, "reliability", None), "confidence_band", None),
                default="none",
            ) or "none",
            "toc_partial_reliability": _safe_float(
                getattr(getattr(analysis, "reliability", None), "partial_reliability", 0.0)
            ),
            "suppressed_indexes_count": len(suppressed_indexes),
            "recoverable_indexes_count": _safe_len(
                getattr(getattr(analysis, "guard", None), "recoverable_indexes", None)
            ),
            "false_positive_indexes_count": _safe_len(
                getattr(getattr(analysis, "guard", None), "false_positive_indexes", None)
            ),
            "body_recovered_count": _safe_int(body_recovered_count),
            "guard_false_positive_count": _safe_int(guard_fp_count),
            "body_elements_count": _safe_int(body_elements_count),
            "original_elements_count": _safe_int(original_elements_count),
        }

        # Новый toc_detected и toc_confidence
        new_toc_detected = _safe_bool(getattr(analysis, "detected", False))
        new_toc_confidence = _safe_float(
            getattr(getattr(analysis, "reliability", None), "partial_reliability", 0.0)
        )

        # Crossref anchor count: берём максимум из старого значения и длины списка
        new_crossref_count = max(
            _safe_int(getattr(old_signals, "crossref_anchor_count", 0)),
            _safe_len(getattr(evidence_bundle, "crossref_anchors", None)),
        )

        # Создаём НОВЫЙ GlobalStructureSignals
        # Используем тот же тип что и в оригинале
        from services.structure._heading_scoring._types import GlobalStructureSignals
        new_global_signals = GlobalStructureSignals(
            toc_detected=new_toc_detected,
            toc_confidence=new_toc_confidence,
            main_section_chain_length=_safe_int(
                getattr(old_signals, "main_section_chain_length", 0)
            ),
            appendix_chain_length=_safe_int(
                getattr(old_signals, "appendix_chain_length", 0)
            ),
            crossref_anchor_count=new_crossref_count,
            heading_candidates_count=_safe_int(
                getattr(old_signals, "heading_candidates_count", 0)
            ),
            extraction_quality_score=_safe_float(
                getattr(old_signals, "extraction_quality_score", 0.0)
            ),
            document_quality_signals=new_quality,
            notes=list(getattr(old_signals, "notes", []) or []),
        )

        # Создаём НОВЫЙ StructureEvidenceBundle
        from services.structure._heading_scoring._types import StructureEvidenceBundle
        new_bundle = StructureEvidenceBundle(
            heading_candidates=list(
                getattr(evidence_bundle, "heading_candidates", []) or []
            ),
            numbering_sequences=list(
                getattr(evidence_bundle, "numbering_sequences", []) or []
            ),
            toc_blocks=list(
                getattr(evidence_bundle, "toc_blocks", []) or []
            ),
            appendix_markers=list(
                getattr(evidence_bundle, "appendix_markers", []) or []
            ),
            crossref_anchors=list(
                getattr(evidence_bundle, "crossref_anchors", []) or []
            ),
            page_signals=list(
                getattr(evidence_bundle, "page_signals", []) or []
            ),
            global_signals=new_global_signals,
        )

        return new_bundle

    except Exception:
        logger.exception(
            "STRUCTURE evidence_bundle_immutable_enrichment_failed",
            extra={"document_id": document_id},
        )
        # При ошибке возвращаем исходный bundle.
        # Pipeline не должен падать из-за enrichment.
        return evidence_bundle


def _try_enrich_evidence_bundle_with_toc(
    *,
    document_id: str,
    evidence_bundle: Any | None,
    analysis: Any,
    suppressed_indexes: set[int] | list[int],
    body_recovered_count: int,
    guard_fp_count: int,
    body_elements_count: int,
    original_elements_count: int,
) -> None:
    """
    DEPRECATED: мутирует evidence bundle напрямую.

    Заменена на _enrich_evidence_bundle_immutable(...).
    Оставлена для безопасного rollback. Не вызывается из pipeline.
    Будет удалена после стабилизации immutable enrichment.
    """
    if evidence_bundle is None:
        return

    try:
        global_signals = getattr(evidence_bundle, "global_signals", None)
        if global_signals is None:
            return

        global_signals.toc_detected = _safe_bool(getattr(analysis, "detected", False))
        global_signals.toc_confidence = _safe_float(
            getattr(getattr(analysis, "reliability", None), "partial_reliability", 0.0)
        )
        global_signals.crossref_anchor_count = max(
            _safe_int(getattr(global_signals, "crossref_anchor_count", 0)),
            _safe_len(getattr(evidence_bundle, "crossref_anchors", None)),
        )

        quality_signals = _safe_to_dict(
            getattr(global_signals, "document_quality_signals", {}) or {}
        )
        quality_signals.update(
            {
                "toc_guard_decision": _safe_str(
                    getattr(getattr(analysis, "guard", None), "decision", None),
                    default="reject_toc",
                )
                or "reject_toc",
                "toc_reliable": _safe_bool(
                    getattr(getattr(analysis, "reliability", None), "is_reliable", False)
                ),
                "toc_confidence_band": _safe_str(
                    getattr(getattr(analysis, "reliability", None), "confidence_band", None),
                    default="none",
                )
                or "none",
                "toc_partial_reliability": _safe_float(
                    getattr(getattr(analysis, "reliability", None), "partial_reliability", 0.0)
                ),
                "suppressed_indexes_count": len(suppressed_indexes),
                "recoverable_indexes_count": _safe_len(
                    getattr(getattr(analysis, "guard", None), "recoverable_indexes", None)
                ),
                "false_positive_indexes_count": _safe_len(
                    getattr(getattr(analysis, "guard", None), "false_positive_indexes", None)
                ),
                "body_recovered_count": _safe_int(body_recovered_count),
                "guard_false_positive_count": _safe_int(guard_fp_count),
                "body_elements_count": _safe_int(body_elements_count),
                "original_elements_count": _safe_int(original_elements_count),
            }
        )
        global_signals.document_quality_signals = quality_signals
    except Exception:
        logger.exception(
            "STRUCTURE evidence_bundle_toc_enrichment_failed",
            extra={"document_id": document_id},
        )


def _count_root_sections(root_nodes: list[Any]) -> int:
    """
    Считает корневые main sections по deterministic numeric raw_uid.

    Transitional heuristic до formal scope-aware canonical tree artifact.
    """
    count = 0
    for node in root_nodes:
        raw_uid = _safe_str(getattr(node, "raw_uid", "")).strip()
        scope = _safe_str(getattr(node, "scope", "")).strip()
        if raw_uid.isdigit() and not _is_appendix_like_text(scope):
            count += 1
    return count


def _count_appendix_roots(root_nodes: list[Any]) -> int:
    """
    Считает appendix-like root nodes.

    Transitional heuristic:
    приоритетно используем scope, затем effective_uid/title/raw_uid.
    """
    count = 0
    for node in root_nodes:
        scope = _safe_str(getattr(node, "scope", "")).strip()
        effective_uid = _safe_str(getattr(node, "effective_uid", "")).strip()
        title = _safe_str(getattr(node, "title", "")).strip()
        raw_uid = _safe_str(getattr(node, "raw_uid", "")).strip()

        if (
            _is_appendix_like_text(scope)
            or _is_appendix_like_text(effective_uid)
            or _is_appendix_like_text(title)
            or _is_appendix_like_text(raw_uid)
        ):
            count += 1
    return count


def _build_assessment_inputs(
    *,
    coverage: float,
    heading_summary: dict[str, Any],
    structure_degraded: bool,
    root_sections_count: int,
    appendix_root_count: int,
    evidence_signals: dict[str, Any],
    crossref_stats: dict[str, Any],
    evidence_bundle: Any | None = None,
    crossref_graph: Any | None = None,
) -> tuple[HierarchyAssessmentInput, EvidenceAssessmentInput, CrossRefAssessmentInput]:
    """
    Собирает typed inputs для quality assessment / gate decision.

    Приоритеты:
    1. Если доступен evidence_bundle — используем _extract_evidence_metrics
       который читает все поля включая toc_confidence, candidate_count и т.д.
    2. Fallback на evidence_signals dict если bundle недоступен.
    3. Если доступен crossref_graph.stats — используем _extract_crossref_input.
    4. Fallback на crossref_stats dict.
    """
    hierarchy_input = HierarchyAssessmentInput(
        coverage=_safe_float(coverage),
        headings_count=_safe_int(heading_summary.get("total", 0)),
        numeric_ratio=_safe_float(heading_summary.get("numeric_ratio", 0.0)),
        empty_title_count=_safe_int(heading_summary.get("empty_title_count", 0)),
        root_sections_count=_safe_int(root_sections_count),
        appendix_root_count=_safe_int(appendix_root_count),
        structure_degraded=_safe_bool(structure_degraded),
    )

    # Evidence input: используем полный extractor если bundle доступен.
    # Это даёт toc_confidence, candidate_count, max_depth_observed и другие поля
    # которые были потеряны при ручной сборке из evidence_signals dict.
    if evidence_bundle is not None:
        evidence_input = _extract_evidence_metrics(evidence_bundle)
        # Дополняем document_quality_signals из evidence_signals
        # (там есть TOC-guard и другие pipeline-specific поля)
        existing_quality = _safe_to_dict(
            getattr(
                getattr(evidence_bundle, "global_signals", None),
                "document_quality_signals",
                {},
            ) or {}
        )
        pipeline_quality_fields = {
            "toc_guard_decision": evidence_signals.get("toc_guard_decision"),
            "toc_reliable": _safe_bool(evidence_signals.get("toc_reliable", False)),
            "toc_confidence_band": _safe_str(
                evidence_signals.get("toc_confidence_band"), default="none"
            ) or "none",
            "toc_partial_reliability": _safe_float(
                evidence_signals.get("toc_partial_reliability", 0.0)
            ),
            "suppressed_indexes_count": _safe_int(
                evidence_signals.get("suppressed_indexes_count", 0)
            ),
            "body_recovered_count": _safe_int(
                evidence_signals.get("body_recovered_count", 0)
            ),
            "guard_false_positive_count": _safe_int(
                evidence_signals.get("guard_false_positive_count", 0)
            ),
            "body_elements_count": _safe_int(
                evidence_signals.get("body_elements_count", 0)
            ),
            "original_elements_count": _safe_int(
                evidence_signals.get("original_elements_count", 0)
            ),
        }
        # Merge: pipeline_quality_fields добавляются поверх уже существующих
        merged_quality = {**existing_quality, **pipeline_quality_fields}
        evidence_input.document_quality_signals = merged_quality
    else:
        # Fallback: строим из dict как раньше
        evidence_input = EvidenceAssessmentInput(
            present=True,
            toc_detected=_safe_bool(evidence_signals.get("toc_detected", False)),
            main_chain_len=_safe_int(evidence_signals.get("main_section_chain_length", 0)),
            appendix_chain_len=_safe_int(evidence_signals.get("appendix_chain_length", 0)),
            crossref_anchor_count=_safe_int(evidence_signals.get("crossref_anchor_candidates", 0)),
            appendix_marker_count=_safe_int(evidence_signals.get("appendix_marker_count", 0)),
            document_quality_signals={
                "toc_guard_decision": evidence_signals.get("toc_guard_decision"),
                "toc_reliable": _safe_bool(evidence_signals.get("toc_reliable", False)),
                "toc_confidence_band": _safe_str(
                    evidence_signals.get("toc_confidence_band"), default="none"
                ) or "none",
                "toc_partial_reliability": _safe_float(
                    evidence_signals.get("toc_partial_reliability", 0.0)
                ),
                "suppressed_indexes_count": _safe_int(
                    evidence_signals.get("suppressed_indexes_count", 0)
                ),
                "body_recovered_count": _safe_int(
                    evidence_signals.get("body_recovered_count", 0)
                ),
                "guard_false_positive_count": _safe_int(
                    evidence_signals.get("guard_false_positive_count", 0)
                ),
                "body_elements_count": _safe_int(
                    evidence_signals.get("body_elements_count", 0)
                ),
                "original_elements_count": _safe_int(
                    evidence_signals.get("original_elements_count", 0)
                ),
            },
        )

    # Crossref input: используем полный extractor если graph.stats доступен.
    crossref_graph_stats = getattr(crossref_graph, "stats", None) if crossref_graph else None
    if crossref_graph_stats is not None:
        crossref_input = _extract_crossref_input(crossref_graph_stats)
    else:
        # Fallback: строим из dict как раньше
        crossref_input = CrossRefAssessmentInput(
            references_count=_safe_int(crossref_stats.get("references_count", 0)),
            resolved_count=max(
                0,
                _safe_int(crossref_stats.get("references_count", 0))
                - _safe_int(crossref_stats.get("unresolved_count", 0))
                - _safe_int(crossref_stats.get("ambiguous_count", 0)),
            ),
            unresolved_count=_safe_int(crossref_stats.get("unresolved_count", 0)),
            ambiguous_count=_safe_int(crossref_stats.get("ambiguous_count", 0)),
            appendix_scoped_resolved_count=_safe_int(
                crossref_stats.get("appendix_scoped_resolved_count", 0)
            ),
            appendix_scope_miss_count=_safe_int(
                crossref_stats.get("appendix_scope_miss_count", 0)
            ),
        )

    return hierarchy_input, evidence_input, crossref_input


def _embed_structure_evidence_diagnostics(
    diagnostics: dict[str, Any],
    *,
    evidence_signals: dict[str, Any],
) -> dict[str, Any]:
    diagnostics["structure_evidence"] = {
        "toc_detected": _safe_bool(evidence_signals.get("toc_detected", False)),
        "toc_guard_decision": _safe_str(
            evidence_signals.get("toc_guard_decision"),
            default="reject_toc",
        )
        or "reject_toc",
        "toc_reliable": _safe_bool(evidence_signals.get("toc_reliable", False)),
        "toc_confidence_band": _safe_str(
            evidence_signals.get("toc_confidence_band"),
            default="none",
        )
        or "none",
        "toc_partial_reliability": _safe_round(
            evidence_signals.get("toc_partial_reliability", 0.0)
        ),
        "main_section_chain_length": _safe_int(
            evidence_signals.get("main_section_chain_length", 0)
        ),
        "appendix_chain_length": _safe_int(
            evidence_signals.get("appendix_chain_length", 0)
        ),
        "crossref_anchor_candidates": _safe_int(
            evidence_signals.get("crossref_anchor_candidates", 0)
        ),
        "heading_candidates_count": _safe_int(
            evidence_signals.get("heading_candidates_count", 0)
        ),
        "appendix_marker_count": _safe_int(
            evidence_signals.get("appendix_marker_count", 0)
        ),
        "suppressed_indexes_count": _safe_int(
            evidence_signals.get("suppressed_indexes_count", 0)
        ),
        "body_recovered_count": _safe_int(
            evidence_signals.get("body_recovered_count", 0)
        ),
        "guard_false_positive_count": _safe_int(
            evidence_signals.get("guard_false_positive_count", 0)
        ),
        "body_elements_count": _safe_int(
            evidence_signals.get("body_elements_count", 0)
        ),
        "original_elements_count": _safe_int(
            evidence_signals.get("original_elements_count", 0)
        ),
    }
    return diagnostics


def _embed_crossref_diagnostics(
    diagnostics: dict[str, Any],
    *,
    crossref_graph: Any | None,
    crossref_stats: dict[str, Any],
) -> dict[str, Any]:
    diagnostics["cross_references"] = {
        "stats": dict(crossref_stats),
        "graph_present": crossref_graph is not None,
    }
    return diagnostics


def _embed_quality_gate_diagnostics(
    diagnostics: dict[str, Any],
    *,
    coverage: float,
    heading_summary: dict[str, Any],
    structure_degraded: bool,
    evidence_signals: dict[str, Any],
    root_sections_count: int,
    appendix_root_count: int,
    crossref_stats: dict[str, Any],
    assessment: StructureAssessment,
    gate_decision: StructureGateDecision,
) -> dict[str, Any]:
    quality_gates = diagnostics.setdefault("quality_gates", {})
    quality_gates.update(
        {
            "coverage": _safe_round(coverage),
            "headings_count": _safe_int(heading_summary.get("total", 0)),
            "numeric_ratio": _safe_round(heading_summary.get("numeric_ratio", 0.0)),
            "empty_title_count": _safe_int(heading_summary.get("empty_title_count", 0)),
            "structure_degraded_from_builder": _safe_bool(structure_degraded),
            "toc_detected": _safe_bool(evidence_signals.get("toc_detected", False)),
            "toc_reliable": _safe_bool(evidence_signals.get("toc_reliable", False)),
            "toc_confidence_band": _safe_str(
                evidence_signals.get("toc_confidence_band"),
                default="none",
            )
            or "none",
            "toc_partial_reliability": _safe_round(
                evidence_signals.get("toc_partial_reliability", 0.0)
            ),
            "toc_guard_decision": _safe_str(
                evidence_signals.get("toc_guard_decision"),
                default="reject_toc",
            )
            or "reject_toc",
            "root_sections_count": _safe_int(root_sections_count),
            "appendix_root_count": _safe_int(appendix_root_count),
            "main_section_chain_length": _safe_int(
                evidence_signals.get("main_section_chain_length", 0)
            ),
            "appendix_chain_length": _safe_int(
                evidence_signals.get("appendix_chain_length", 0)
            ),
            "crossref_anchor_candidates": _safe_int(
                evidence_signals.get("crossref_anchor_candidates", 0)
            ),
            "appendix_marker_count": _safe_int(
                evidence_signals.get("appendix_marker_count", 0)
            ),
            "cross_references_count": _safe_int(crossref_stats.get("references_count", 0)),
            "cross_references_unresolved_count": _safe_int(crossref_stats.get("unresolved_count", 0)),
            "cross_references_ambiguous_count": _safe_int(crossref_stats.get("ambiguous_count", 0)),
            "appendix_scoped_resolved_count": _safe_int(
                crossref_stats.get("appendix_scoped_resolved_count", 0)
            ),
            "appendix_scope_miss_count": _safe_int(
                crossref_stats.get("appendix_scope_miss_count", 0)
            ),
            "quality_gate_mode": gate_decision.gate_mode,
            "section_chunking_allowed": gate_decision.section_chunking_allowed,
            "technical_fallback_only": gate_decision.technical_fallback_only,
            "semantic_tree_preserved_despite_low_confidence": (
                gate_decision.semantic_tree_preserved_despite_low_confidence
            ),
            "allow_semantic_tree_with_warnings": (
                gate_decision.section_chunking_allowed
                and not gate_decision.technical_fallback_only
            ),
            "fallback_reason": (
                "quality_gate_block_and_fallback"
                if gate_decision.technical_fallback_only
                else None
            ),
            "final_mode": gate_decision.final_mode,
            "assessment": {
                "confidence": assessment.confidence,
                "degraded": _safe_bool(assessment.degraded),
                "retrieval_safe": _safe_bool(assessment.retrieval_safe),
                "overall_score": _safe_round(assessment.overall_score),
                "heading_confidence": _safe_round(assessment.heading_confidence),
                "tree_consistency_confidence": _safe_round(
                    assessment.tree_consistency_confidence
                ),
                "appendix_confidence": _safe_round(assessment.appendix_confidence),
                "crossref_anchor_confidence": _safe_round(
                    assessment.crossref_anchor_confidence
                ),
                "layout_quality_confidence": _safe_round(
                    assessment.layout_quality_confidence
                ),
                "policy_version": _safe_str(getattr(assessment, "policy_version", "")),
            },
            "confidence_reasons": list(getattr(assessment, "reasons", []) or []),
            "gate_reasons": list(getattr(gate_decision, "reasons", []) or []),
        }
    )
    return diagnostics


def _build_early_fallback_quality_diagnostics(
    reason: str,
    *,
    record_heading_recovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics = {
        "quality_gates": {
            "headings_pre_count": 0,
            "early_fallback_reason": reason,
            "section_chunking_allowed": False,
            "technical_fallback_only": True,
            "quality_gate_mode": QUALITY_GATE_BLOCK_AND_FALLBACK,
            "final_mode": "technical_fallback",
        }
    }
    if record_heading_recovery is not None:
        diagnostics["record_heading_recovery"] = record_heading_recovery
    return diagnostics



def _build_initial_headings_with_record_recovery(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """
    Run initial heading detection with deterministic numbered-record recovery.

    Flow:
    1. try ordinary heading detection;
    2. if zero headings -> attempt numbered-record recovery;
    3. rerun heading detection on recovered elements;
    4. return headings + effective elements + recovery diagnostics.
    """
    headings_pre = build_heading_candidates(
        elements,
        document_id=document_id,
        toc_match_index=None,
    )
    if headings_pre:
        return headings_pre, elements, {
            "attempted": False,
            "applied": False,
            "mode": "numbered_record",
            "reason": "not_needed_headings_found_in_primary_pass",
            "headings_pre_count_before_recovery": len(headings_pre),
            "headings_pre_count_after_recovery": len(headings_pre),
        }

    recovery_result = attempt_record_heading_recovery(
        document_id=document_id,
        elements=elements,
    )
    recovery_diag = dict(recovery_result.diagnostics or {})
    recovery_diag["headings_pre_count_before_recovery"] = 0

    if not recovery_result.applied:
        recovery_diag["headings_pre_count_after_recovery"] = 0
        return [], elements, recovery_diag

    recovered_headings = build_heading_candidates(
        recovery_result.elements,
        document_id=document_id,
        toc_match_index=None,
    )
    recovery_diag["headings_pre_count_after_recovery"] = len(recovered_headings)

    if recovered_headings:
        return recovered_headings, recovery_result.elements, recovery_diag

    recovery_diag["reason"] = "recovery_applied_but_no_headings_detected_after_rerun"
    return [], elements, recovery_diag


def _emit_structure_built_telemetry(
    collector: "TelemetryCollector",
    *,
    document_id: str,
    segment_id: str | None,
    assessment: Any,
    gate_decision: Any,
    recovery_audit: Any,
    resolution_audit: Any,
    root_nodes: list,
    nodes: dict,
    headings: list,
    elapsed_ms: float,
) -> None:
    """
    Phase 13.2: emit StructureBuiltEvent в collector.

    Failure-isolated: любая ошибка логируется и игнорируется.
    Вынесено в отдельную функцию для чистоты build_single_segment_tree().
    """
    try:
        from services.telemetry._events import StructureBuiltEvent

        orphans_detected = _safe_int(
            getattr(recovery_audit, "orphans_detected", 0)
        )
        orphans_unresolved = _safe_int(
            getattr(recovery_audit, "orphans_unresolved", 0)
        )
        headings_count = len(headings)
        orphan_ratio = (
            min(1.0, orphans_unresolved / max(1, headings_count))
            if headings_count > 0 else 0.0
        )

        # grammar_violation_ratio берём из grammar_consistency компонента
        # assessment, а не из tree_consistency_confidence (это score, не ratio).
        grammar_violation_ratio = _safe_float(
            getattr(
                getattr(assessment, "grammar_consistency", None),
                "violation_ratio",
                0.0,
            )
        )

        rewrite_ratio: float | None = None
        if resolution_audit is not None:
            raw_rr = getattr(resolution_audit, "rewrite_ratio", None)
            if raw_rr is not None:
                rewrite_ratio = round(_safe_float(raw_rr), 4)

        collector.emit(StructureBuiltEvent(
            document_id=document_id,
            segment_id=segment_id,
            elapsed_ms=elapsed_ms,
            total_nodes=len(nodes),
            root_nodes_count=len(root_nodes),
            headings_count=headings_count,
            orphans_detected=orphans_detected,
            orphans_unresolved=orphans_unresolved,
            orphan_ratio=round(min(1.0, max(0.0, orphan_ratio)), 4),
            grammar_violation_ratio=round(
                min(1.0, max(0.0, grammar_violation_ratio)), 4
            ),
            rewrite_ratio=rewrite_ratio,
            overall_score=round(_safe_float(
                getattr(assessment, "overall_score", 0.0)
            ), 4),
            retrieval_safe_phase5=_safe_bool(
                getattr(assessment, "retrieval_safe", False)
            ),
            degraded=_safe_bool(getattr(assessment, "degraded", True)),
            final_mode=_safe_str(getattr(gate_decision, "final_mode", "unknown")),
        ))
    except Exception as exc:
        logger.warning(
            "TELEMETRY structure_built_emit_failed",
            document_id=document_id,
            segment_id=segment_id,
            error=str(exc),
        )


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
    collector: "TelemetryCollector | None" = None,  # Phase 13.2
) -> ClauseTree:
    build_started = time.perf_counter()
    normalized_scope_name = _safe_str(scope_name, default="main_contract").strip() or "main_contract"

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
    headings_pre, effective_elements, record_heading_recovery_diag = (
        _build_initial_headings_with_record_recovery(
            document_id=document_id,
            elements=elements,
        )
    )
    log_timing(f"{log_prefix} headings_pass_1", t_h1)

    if not headings_pre:
        return degraded_tree(
            document_id=document_id,
            elements=effective_elements,
            structure_confidence=STRUCTURE_CONFIDENCE_LOW,
            diagnostics=_build_early_fallback_quality_diagnostics(
                "no_headings_in_pass_1",
                record_heading_recovery=record_heading_recovery_diag,
            ),
            scope_name=normalized_scope_name,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
        )

    analysis = analyze_toc_with_guard(
        effective_elements,
        headings_pre,
        document_id=document_id,
    )

    annotated_elements, body_recovered_count, guard_fp_count = annotate_elements_with_guard(
        effective_elements,
        analysis.guard,
    )

    suppressed_indexes = compute_suppressed_indexes(
        elements=annotated_elements,
        analysis=analysis,
    )

    body_elements = [
        el for idx, el in enumerate(annotated_elements)
        if idx not in suppressed_indexes
    ]

    # Phase 2: единственный scoring pass — возвращает оба артефакта.
    # Раньше здесь было два отдельных вызова (build_heading_candidates +
    # build_structure_evidence_bundle), каждый из которых запускал scoring
    # независимо. Теперь scoring выполняется ровно один раз.
    phase2_result = run_phase2(
        body_elements,
        document_id=document_id,
        toc_match_index=analysis.toc_match_index,
    )
    headings = phase2_result.accepted_headings
    raw_evidence_bundle = phase2_result.evidence_bundle

    # Phase 2 enrichment: добавляем TOC-сигналы в bundle.
    # Создаём НОВЫЙ immutable bundle — исходный raw_evidence_bundle не мутируется.
    evidence_bundle = _enrich_evidence_bundle_immutable(
        document_id=document_id,
        evidence_bundle=raw_evidence_bundle,
        analysis=analysis,
        suppressed_indexes=suppressed_indexes,
        body_recovered_count=body_recovered_count,
        guard_fp_count=guard_fp_count,
        body_elements_count=len(body_elements),
        original_elements_count=len(elements),
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

    # Phase 3-4: typed HierarchyBuildResult вместо tuple.
    hierarchy_result = build_clause_hierarchy(
        headings=headings,
        elements=body_elements,
        document_id=document_id,
        stable_element_id_resolver=stable_element_id,
        structure_evidence=evidence_bundle,
    )

    # Распаковываем для backward-compatibility с downstream кодом этой функции.
    # После полного перехода на HierarchyBuildResult эти переменные
    # можно будет заменить на hierarchy_result.root_nodes и т.д.
    root_nodes = hierarchy_result.root_nodes
    nodes = hierarchy_result.nodes_index
    element_to_effective_uid = hierarchy_result.element_to_effective_uid
    structure_degraded = hierarchy_result.structure_degraded
    fsm_summary = hierarchy_result.fsm_summary
    resolution_audit = hierarchy_result.resolution_audit
    recovery_audit = hierarchy_result.recovery_audit

    # Phase 7: получаем graph + structured audit вместо только graph.
    crossref_result = build_cross_reference_graph_with_audit(
        body_elements,
        element_to_effective_uid,
        nodes,
        document_id=document_id,
        stable_element_id_resolver=stable_element_id,
    )
    cross_reference_graph = crossref_result.graph

    coverage = calculate_node_coverage(nodes=nodes, elements=body_elements)
    heading_summary = summarize_headings(headings)
    crossref_stats = _read_crossref_stats(cross_reference_graph)

    diagnostics: dict[str, Any] = {
        "record_heading_recovery": record_heading_recovery_diag,
    }

    diagnostics = embed_toc_diagnostics(diagnostics, toc_diag_obj)
    diagnostics = embed_parse_quality_diagnostics(diagnostics, parse_quality_obj)

    evidence_signals = _read_evidence_signals(
        document_id=document_id,
        evidence_bundle=evidence_bundle,
        analysis=analysis,
        suppressed_indexes=suppressed_indexes,
        body_recovered_count=body_recovered_count,
        guard_fp_count=guard_fp_count,
        body_elements_count=len(body_elements),
        original_elements_count=len(elements),
    )

    root_sections_count = _count_root_sections(root_nodes)
    appendix_root_count = _count_appendix_roots(root_nodes)

    diagnostics = _embed_structure_evidence_diagnostics(
        diagnostics,
        evidence_signals=evidence_signals,
    )
    diagnostics = _embed_crossref_diagnostics(
        diagnostics,
        crossref_graph=cross_reference_graph,
        crossref_stats=crossref_stats,
    )

    hierarchy_input, evidence_input, crossref_input = _build_assessment_inputs(
        coverage=coverage,
        heading_summary=heading_summary,
        structure_degraded=structure_degraded,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
        evidence_signals=evidence_signals,
        crossref_stats=crossref_stats,
        # Передаём оригинальные артефакты для полного extraction
        evidence_bundle=evidence_bundle,
        crossref_graph=cross_reference_graph,
    )

    assessment = compute_structure_assessment(
        hierarchy=hierarchy_input,
        evidence=evidence_input,
        crossrefs=crossref_input,
        fsm_summary=fsm_summary,
        resolution_audit=resolution_audit,
        recovery_audit=recovery_audit,
        layout_degraded=False,
    )
    gate_decision = decide_structure_gate(
        assessment=assessment,
        hierarchy=hierarchy_input,
        evidence=evidence_input,
        crossrefs=crossref_input,
    )

    confidence_report = build_structure_confidence_report(
        coverage=coverage,
        headings_count=_safe_int(heading_summary.get("total", 0)),
        numeric_ratio=_safe_float(heading_summary.get("numeric_ratio", 0.0)),
        empty_title_count=_safe_int(heading_summary.get("empty_title_count", 0)),
        structure_degraded=_safe_bool(structure_degraded),
        layout_degraded=False,
        structure_evidence=evidence_bundle,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
        cross_references_count=_safe_int(crossref_stats.get("references_count", 0)),
        fsm_summary=fsm_summary,
        resolution_audit=resolution_audit,
        recovery_audit=recovery_audit,
    )
    diagnostics["structure_confidence"] = confidence_report.to_dict()

    diagnostics = _embed_quality_gate_diagnostics(
        diagnostics,
        coverage=coverage,
        heading_summary=heading_summary,
        structure_degraded=structure_degraded,
        evidence_signals=evidence_signals,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
        crossref_stats=crossref_stats,
        assessment=assessment,
        gate_decision=gate_decision,
    )

    diagnostics["hierarchy_builder"] = {
        "fsm_summary": (
            fsm_summary.to_dict()
            if callable(getattr(fsm_summary, "to_dict", None))
            else None
        ),
        "resolution_audit": (
            resolution_audit.to_dict()
            if callable(getattr(resolution_audit, "to_dict", None))
            else None
        ),
        "recovery_audit": (
            recovery_audit.to_dict()
            if callable(getattr(recovery_audit, "to_dict", None))
            else None
        ),
        # DegradationInfo: полный breakdown вместо только bool
        "degradation": (
            hierarchy_result.degradation.to_dict()
            if callable(getattr(hierarchy_result.degradation, "to_dict", None))
            else None
        ),
        # Для удобного доступа Phase 8+
        "hierarchy_diagnostics_summary": {
            "root_nodes_count": len(root_nodes),
            "nodes_count": len(nodes),
            "headings_count": len(headings),
        },
    }

    # Phase 7 audit: structured diagnostics по unresolved/ambiguous ссылкам.
    diagnostics["crossref_audit"] = crossref_result.audit.to_dict()


    if gate_decision.gate_mode == QUALITY_GATE_BLOCK_AND_FALLBACK:
        return degraded_tree(
            document_id=document_id,
            elements=body_elements,
            coverage=coverage,
            structure_confidence=assessment.confidence,
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
        cross_reference_graph=cross_reference_graph,
        structure_confidence=assessment.confidence,
        degraded=bool(
            assessment.degraded
            and not gate_decision.semantic_tree_preserved_despite_low_confidence
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

    # ── Phase 13.2: emit StructureBuiltEvent ─────────────────────────────
    if collector is not None:
        _emit_structure_built_telemetry(
            collector,
            document_id=document_id,
            segment_id=segment_id,
            assessment=assessment,
            gate_decision=gate_decision,
            recovery_audit=recovery_audit,
            resolution_audit=resolution_audit,
            root_nodes=root_nodes,
            nodes=nodes,
            headings=headings,
            elapsed_ms=round(
                (time.perf_counter() - build_started) * 1000, 1
            ),
        )

    log_timing(f"{log_prefix} build_total", build_started)
    return result


