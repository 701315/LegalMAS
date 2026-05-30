# src/services/structure/chunk_planner/_planner.py

"""
Phase 10 — Chunk Planner: core logic.

Читает FileStructureAnalysisResult (Phase 9 output) и строит FileChunkPlan.

Архитектурные принципы:
- detерминированный: один input → один output;
- не вызывает LLM, не читает файлы, не пишет в БД;
- работает только с типизированными объектами из Phase 8/9;
- graceful degradation: если Phase 9 report недоступен →
  консервативный LAYOUT_FALLBACK;
- warnings объясняют каждое нетривиальное решение.

Логика выбора mode:
  Priority 1: report.recommended_chunking_mode (из Phase 9)
  Priority 2: metric-based fallback если report недоступен:
    - fallback_fragment_ratio >= 0.50 → LAYOUT_FALLBACK
    - retrieval_safe=False            → HYBRID
    - иначе                           → STRUCTURE_FIRST
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logging import get_logger
from services.structure._models._analysis import (
    RecommendedChunkingMode,
    SegmentAnalysisArtifacts,
    StructureQualityReport,
)
from services.structure.chunk_planner._types import (
    ChunkingModeDecision,
    ChunkingTokenParams,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
    TOKENS_MODE_B,
    TOKENS_MODE_C,
)

if TYPE_CHECKING:
    from services.structure._models._analysis import FileStructureAnalysisResult

logger = get_logger(__name__)

# ─── Mode-specific flags ──────────────────────────────────────────────────────

# Mode A: структура надёжна.
_MODE_A_FLAGS = {
    "allow_section_chunks": True,
    "allow_subclause_splitting": True,
    "drop_technical_fallback_nodes": False,
    "prefer_layout_fallback": False,
}

# Mode B: структура есть, но с шумом.
_MODE_B_FLAGS = {
    "allow_section_chunks": False,
    "allow_subclause_splitting": True,
    "drop_technical_fallback_nodes": True,
    "prefer_layout_fallback": False,
}

# Mode C: структура ненадёжна.
_MODE_C_FLAGS = {
    "allow_section_chunks": False,
    "allow_subclause_splitting": False,
    "drop_technical_fallback_nodes": True,
    "prefer_layout_fallback": True,
}

_MODE_FLAGS = {
    RecommendedChunkingMode.STRUCTURE_FIRST: _MODE_A_FLAGS,
    RecommendedChunkingMode.HYBRID: _MODE_B_FLAGS,
    RecommendedChunkingMode.LAYOUT_FALLBACK: _MODE_C_FLAGS,
}

_MODE_TOKENS = {
    RecommendedChunkingMode.STRUCTURE_FIRST: TOKENS_MODE_A,
    RecommendedChunkingMode.HYBRID: TOKENS_MODE_B,
    RecommendedChunkingMode.LAYOUT_FALLBACK: TOKENS_MODE_C,
}


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _safe_document_id(analysis: "FileStructureAnalysisResult") -> str:
    """Извлечь document_id безопасно."""
    try:
        return str(
            analysis.file_structure.primary_tree.document_id or "unknown"
        )
    except Exception:
        return "unknown"


def _mode_from_report(report: StructureQualityReport) -> RecommendedChunkingMode:
    """
    Извлечь mode из Phase 9 report.
    Priority 1: доверяем Phase 9.
    """
    return report.recommended_chunking_mode


def _mode_from_metrics_fallback(
    retrieval_safe: bool,
    fallback_fragment_ratio: float,
) -> tuple[RecommendedChunkingMode, str]:
    """
    Metric-based mode selection если Phase 9 report недоступен.
    Priority 2: fallback по метрикам.

    Returns (mode, reason).
    """
    if fallback_fragment_ratio >= 0.50:
        return (
            RecommendedChunkingMode.LAYOUT_FALLBACK,
            f"no quality report available; "
            f"fallback_fragment_ratio={fallback_fragment_ratio:.3f} >= 0.50",
        )
    if not retrieval_safe:
        return (
            RecommendedChunkingMode.HYBRID,
            "no quality report available; retrieval_safe=False",
        )
    return (
        RecommendedChunkingMode.STRUCTURE_FIRST,
        "no quality report available; metrics suggest safe structure",
    )


def _build_mode_decision_from_report(
    report: StructureQualityReport,
) -> ChunkingModeDecision:
    """
    Строит ChunkingModeDecision из Phase 9 StructureQualityReport.

    Доверяем Phase 9 mode как primary source of truth.
    Добавляем warnings из метрик для audit trail.
    """
    mode = _mode_from_report(report)
    flags = _MODE_FLAGS[mode]
    token_params = _MODE_TOKENS[mode]

    warnings: list[str] = []
    sm = report.structure_metrics

    # Объясняем ключевые метрики в warnings для audit
    if sm.fallback_fragment_ratio >= 0.90:
        warnings.append(
            f"is_full_fallback=True: "
            f"fallback_fragment_ratio={sm.fallback_fragment_ratio:.3f} >= 0.90; "
            f"tree consists almost entirely of technical fallback nodes"
        )
    elif sm.fallback_fragment_ratio >= 0.50:
        warnings.append(
            f"fallback_fragment_ratio={sm.fallback_fragment_ratio:.3f} >= 0.50; "
            f"significant portion of tree is technical fallback"
        )

    if not report.retrieval_safe:
        warnings.append(
            f"retrieval_safe=False: "
            f"retrieval_safety_score={report.retrieval_safety_score:.3f} < "
            f"threshold={report.thresholds.retrieval_safety_threshold:.3f}"
        )

    if report.orphan_ratio > report.thresholds.orphan_ratio_warning:
        warnings.append(
            f"orphan_ratio={report.orphan_ratio:.3f} > "
            f"threshold={report.thresholds.orphan_ratio_warning:.3f}"
        )

    if (
        report.grammar_violation_ratio
        > report.thresholds.grammar_violation_ratio_warning
    ):
        warnings.append(
            f"grammar_violation_ratio={report.grammar_violation_ratio:.3f} > "
            f"threshold={report.thresholds.grammar_violation_ratio_warning:.3f}"
        )

    if report.has_critical_warnings:
        critical_codes = [
            w.code.value
            for w in report.warnings
            if w.severity.value == "critical"
        ]
        warnings.append(
            f"critical warnings from Phase 9: {', '.join(critical_codes)}"
        )

    # Формируем reason — кратко и audit-friendly
    reason = (
        f"Phase 9 recommended mode={mode.value}; "
        f"retrieval_safe={report.retrieval_safe}; "
        f"retrieval_safety_score={report.retrieval_safety_score:.3f}; "
        f"fallback_fragment_ratio={sm.fallback_fragment_ratio:.3f}"
    )

    return ChunkingModeDecision(
        mode=mode,
        retrieval_safe=report.retrieval_safe,
        reason=reason,
        token_params=token_params,
        allow_section_chunks=flags["allow_section_chunks"],
        allow_subclause_splitting=flags["allow_subclause_splitting"],
        drop_technical_fallback_nodes=flags["drop_technical_fallback_nodes"],
        prefer_layout_fallback=flags["prefer_layout_fallback"],
        warnings=tuple(warnings),
    )


def _build_mode_decision_no_report(
    document_id: str,
) -> ChunkingModeDecision:
    """
    Строит conservative fallback ChunkingModeDecision когда Phase 9 недоступна.

    Если у нас нет quality report — мы не знаем состояние структуры.
    Консервативно используем HYBRID: clause-based chunking,
    но technical fallback nodes исключаем.
    """
    mode = RecommendedChunkingMode.HYBRID
    flags = _MODE_FLAGS[mode]
    token_params = _MODE_TOKENS[mode]

    warnings = (
        "Phase 9 quality report unavailable; "
        "falling back to HYBRID mode as conservative default",
    )

    reason = (
        f"no Phase 9 report for document={document_id}; "
        f"conservative HYBRID fallback applied"
    )

    logger.warning(
        "CHUNK_PLANNER no_quality_report_fallback",
        extra={
            "document_id": document_id,
            "mode": mode.value,
        },
    )

    return ChunkingModeDecision(
        mode=mode,
        retrieval_safe=False,
        reason=reason,
        token_params=token_params,
        allow_section_chunks=flags["allow_section_chunks"],
        allow_subclause_splitting=flags["allow_subclause_splitting"],
        drop_technical_fallback_nodes=flags["drop_technical_fallback_nodes"],
        prefer_layout_fallback=flags["prefer_layout_fallback"],
        warnings=warnings,
    )


def _build_segment_plan(
    artifacts: SegmentAnalysisArtifacts,
    file_mode_decision: ChunkingModeDecision,
) -> SegmentChunkPlan:
    """
    Строит SegmentChunkPlan для одного сегмента.

    Если у сегмента есть собственный quality report — используем его.
    Иначе наследуем file-level mode_decision.

    Сегмент может получить более строгий mode чем file-level если:
    - его fallback_fragment_ratio критически высок,
    - даже если file-level mode = STRUCTURE_FIRST.
    """
    segment_id = artifacts.segment_id
    report = artifacts.quality_report

    warnings: list[str] = []

    if report is not None:
        # У сегмента есть свой report — используем его mode
        segment_mode = _mode_from_report(report)
        retrieval_safe = report.retrieval_safe
        fallback_fragment_ratio = (
            report.structure_metrics.fallback_fragment_ratio
        )

        # Определяем segment_type из report (segment_id → type недоступен здесь)
        # используем segment_id как proxy
        segment_type = "unknown"

        # Проверяем нужно ли ужесточить mode относительно file-level
        # (segment может быть хуже чем file в целом)
        if (
            segment_mode == RecommendedChunkingMode.STRUCTURE_FIRST
            and fallback_fragment_ratio >= 0.50
        ):
            # Phase 9 иногда может дать STRUCTURE_FIRST даже при высоком
            # fallback_fragment_ratio если других проблем нет.
            # Мы будем консервативны.
            segment_mode = RecommendedChunkingMode.HYBRID
            warnings.append(
                f"segment mode upgraded from STRUCTURE_FIRST to HYBRID: "
                f"fallback_fragment_ratio={fallback_fragment_ratio:.3f} >= 0.50"
            )

        flags = _MODE_FLAGS[segment_mode]
        token_params = _MODE_TOKENS[segment_mode]

        # Добавляем warnings если сегмент хуже чем file-level
        file_mode = file_mode_decision.mode
        if (
            segment_mode == RecommendedChunkingMode.LAYOUT_FALLBACK
            and file_mode != RecommendedChunkingMode.LAYOUT_FALLBACK
        ):
            warnings.append(
                f"segment requires LAYOUT_FALLBACK "
                f"while file-level mode={file_mode.value}; "
                f"segment chunking will be degraded"
            )

        if not retrieval_safe and file_mode_decision.retrieval_safe:
            warnings.append(
                f"segment retrieval_safe=False "
                f"while file-level retrieval_safe=True; "
                f"segment chunks may contain structural noise"
            )

    else:
        # Нет report для сегмента — наследуем file-level
        segment_mode = file_mode_decision.mode
        retrieval_safe = file_mode_decision.retrieval_safe
        fallback_fragment_ratio = 0.0
        segment_type = "unknown"
        flags = _MODE_FLAGS[segment_mode]
        token_params = _MODE_TOKENS[segment_mode]
        warnings.append(
            "no quality report for segment; inheriting file-level mode"
        )

    return SegmentChunkPlan(
        segment_id=segment_id,
        segment_type=segment_type,
        mode=segment_mode,
        token_params=token_params,
        allow_section_chunks=flags["allow_section_chunks"],
        allow_subclause_splitting=flags["allow_subclause_splitting"],
        drop_technical_fallback_nodes=flags["drop_technical_fallback_nodes"],
        retrieval_safe=retrieval_safe,
        fallback_fragment_ratio=fallback_fragment_ratio,
        warnings=tuple(warnings),
    )


# ─── Main planner function ────────────────────────────────────────────────────

def plan_chunking(
    analysis: "FileStructureAnalysisResult",
) -> FileChunkPlan:
    """
    Главная функция Phase 10.

    Читает FileStructureAnalysisResult (Phase 8 + Phase 9 output)
    и строит FileChunkPlan — deterministic plan chunking для всего файла.

    Логика:
    1. Извлечь document_id.
    2. Получить primary artifacts → Phase 9 report.
    3. Если report есть → build mode decision от него (Priority 1).
    4. Если report нет → conservative fallback (Priority 2).
    5. Для каждого сегмента построить SegmentChunkPlan.
    6. Вернуть FileChunkPlan.

    Args:
        analysis: FileStructureAnalysisResult из Phase 8/9.

    Returns:
        FileChunkPlan — immutable plan для downstream chunk assembly.

    Raises:
        ValueError: если analysis is None.
    """
    if analysis is None:
        raise ValueError("plan_chunking: analysis must not be None")

    document_id = _safe_document_id(analysis)

    logger.info(
        "CHUNK_PLANNER plan_chunking_started",
        extra={
            "document_id": document_id,
            "segment_count": len(analysis.segment_artifacts),
            "overall_retrieval_safe": analysis.overall_retrieval_safe,
            "all_segments_full_fallback": analysis.all_segments_full_fallback,
        },
    )

    # ── File-level mode decision ──────────────────────────────────────────
    primary_artifacts = analysis.primary_artifacts

    if primary_artifacts is not None and primary_artifacts.quality_report is not None:
        mode_decision = _build_mode_decision_from_report(
            primary_artifacts.quality_report
        )
    else:
        mode_decision = _build_mode_decision_no_report(document_id)

    # ── Per-segment plans ─────────────────────────────────────────────────
    segment_plans: list[SegmentChunkPlan] = []

    for artifacts in analysis.segment_artifacts:
        segment_plan = _build_segment_plan(
            artifacts=artifacts,
            file_mode_decision=mode_decision,
        )
        segment_plans.append(segment_plan)

    file_plan = FileChunkPlan(
        document_id=document_id,
        mode_decision=mode_decision,
        segment_plans=tuple(segment_plans),
    )

    logger.info(
        "CHUNK_PLANNER plan_chunking_complete",
        extra={
            "document_id": document_id,
            "mode": mode_decision.mode.value,
            "retrieval_safe": mode_decision.retrieval_safe,
            "overall_retrieval_safe": file_plan.overall_retrieval_safe,
            "any_layout_fallback": file_plan.any_layout_fallback,
            "all_segments_full_fallback": file_plan.all_segments_full_fallback,
            "segment_plans_count": len(segment_plans),
            "allow_section_chunks": mode_decision.allow_section_chunks,
            "drop_technical_fallback_nodes": (
                mode_decision.drop_technical_fallback_nodes
            ),
        },
    )

    return file_plan


__all__ = ["plan_chunking"]



