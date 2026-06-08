# src/services/telemetry/_events.py

"""
Typed telemetry events для LegalMAS pipeline.

Phase 13.1 — Telemetry Foundation.

Каждый event — это immutable dataclass с:
- event_type: строка-идентификатор события
- document_id: привязка к документу
- timestamp_ms: время в ms (monotonic)
- payload: типизированные данные

Принципы:
- Events immutable (frozen=True).
- Нет зависимостей от БД, MinIO, LLM.
- Можно сериализовать в dict без внешних зависимостей.
- Все числовые поля имеют safe defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaseTelemetryEvent:
    """Базовый класс для всех pipeline telemetry events."""

    event_type: str = "base"
    document_id: str = ""
    segment_id: str | None = None
    elapsed_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "document_id": self.document_id,
            "segment_id": self.segment_id,
            "elapsed_ms": self.elapsed_ms,
        }


# ---------------------------------------------------------------------------
# Structure events (Phase 1-7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StructureBuiltEvent(BaseTelemetryEvent):
    """
    Событие: structure pipeline завершил построение дерева для сегмента.
    """

    event_type: str = "structure_built"

    total_nodes: int = 0
    root_nodes_count: int = 0
    headings_count: int = 0
    orphans_detected: int = 0
    orphans_unresolved: int = 0
    orphan_ratio: float = 0.0
    grammar_violation_ratio: float = 0.0
    rewrite_ratio: float | None = None
    overall_score: float = 0.0
    retrieval_safe_phase5: bool = False
    degraded: bool = True
    final_mode: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "total_nodes": self.total_nodes,
            "root_nodes_count": self.root_nodes_count,
            "headings_count": self.headings_count,
            "orphans_detected": self.orphans_detected,
            "orphans_unresolved": self.orphans_unresolved,
            "orphan_ratio": round(self.orphan_ratio, 4),
            "grammar_violation_ratio": round(self.grammar_violation_ratio, 4),
            "rewrite_ratio": (
                round(self.rewrite_ratio, 4)
                if self.rewrite_ratio is not None else None
            ),
            "overall_score": round(self.overall_score, 4),
            "retrieval_safe_phase5": self.retrieval_safe_phase5,
            "degraded": self.degraded,
            "final_mode": self.final_mode,
        })
        return base


# ---------------------------------------------------------------------------
# Quality events (Phase 9)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QualityEvaluatedEvent(BaseTelemetryEvent):
    """
    Событие: Phase 9 quality evaluation завершена для сегмента.
    """

    event_type: str = "quality_evaluated"

    retrieval_safety_score: float = 0.0
    retrieval_safe: bool = False
    recommended_chunking_mode: str = "layout_fallback"
    warnings_count: int = 0
    critical_warnings_count: int = 0
    cohesion_available: bool = False
    cohesion_avg_score: float | None = None
    fallback_fragment_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "retrieval_safety_score": round(self.retrieval_safety_score, 4),
            "retrieval_safe": self.retrieval_safe,
            "recommended_chunking_mode": self.recommended_chunking_mode,
            "warnings_count": self.warnings_count,
            "critical_warnings_count": self.critical_warnings_count,
            "cohesion_available": self.cohesion_available,
            "cohesion_avg_score": (
                round(self.cohesion_avg_score, 4)
                if self.cohesion_avg_score is not None else None
            ),
            "fallback_fragment_ratio": round(self.fallback_fragment_ratio, 4),
        })
        return base


# ---------------------------------------------------------------------------
# Cross-segment coherence events (Phase 13.7)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CrossSegmentCoherenceEvent(BaseTelemetryEvent):
    """
    Событие: Phase 13.7 cross-segment coherence pass завершён.

    Document-level event (не per-segment).
    """

    event_type: str = "cross_segment_coherence"

    segments_analyzed: int = 0
    links_found: int = 0
    avg_link_confidence: float = 0.0
    max_link_confidence: float = 0.0
    resolver_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "segments_analyzed": self.segments_analyzed,
            "links_found": self.links_found,
            "avg_link_confidence": round(self.avg_link_confidence, 4),
            "max_link_confidence": round(self.max_link_confidence, 4),
            "resolver_error": self.resolver_error,
        })
        return base


# ---------------------------------------------------------------------------
# Chunking events (Phase 10-11)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChunkingCompletedEvent(BaseTelemetryEvent):
    """
    Событие: chunking завершён для сегмента.

    total_chunks:
        Общее количество retrieval-visible chunks across all levels
        для данного segment snapshot.

    legal_unit_chunks:
        Число legal_unit-level retrieval chunks (P8.8d retrieval corpus).

    retrieval_safe_chunks:
        Число чанков с retrieval_safe=True по chunk metadata.
    """

    event_type: str = "chunking_completed"

    total_chunks: int = 0
    section_chunks: int = 0
    clause_chunks: int = 0
    subclause_chunks: int = 0
    legal_unit_chunks: int = 0          # P8.8d: новый retrieval уровень
    chunking_mode: str = "unknown"
    retrieval_safe_chunks: int = 0
    degraded_chunks: int = 0
    layout_fallback_chunks: int = 0
    retrieval_recommended_action: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "total_chunks": self.total_chunks,
            "section_chunks": self.section_chunks,
            "clause_chunks": self.clause_chunks,
            "subclause_chunks": self.subclause_chunks,
            "legal_unit_chunks": self.legal_unit_chunks,
            "chunking_mode": self.chunking_mode,
            "retrieval_safe_chunks": self.retrieval_safe_chunks,
            "degraded_chunks": self.degraded_chunks,
            "layout_fallback_chunks": self.layout_fallback_chunks,
            "retrieval_recommended_action": self.retrieval_recommended_action,
        })
        return base


# ---------------------------------------------------------------------------
# Enrichment events (Phase 12)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnrichmentCompletedEvent(BaseTelemetryEvent):
    """
    Событие: Phase 12 semantic enrichment завершён для сегмента.

    total_units:
        Число LegalUnit-ов, реально поданных на enrichment.
        Это enrichment-домен, не retrieval-домен.
        Не является размером retrieval corpus.
    """

    event_type: str = "enrichment_completed"

    total_units: int = 0
    applied_count: int = 0
    rejected_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    applied_ratio: float = 0.0
    llm_provider: str | None = None
    llm_model: str | None = None
    policy_version: str = "unknown"
    llm_unavailable: bool = False

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "total_units": self.total_units,
            "applied_count": self.applied_count,
            "rejected_count": self.rejected_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "applied_ratio": round(self.applied_ratio, 4),
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "policy_version": self.policy_version,
            "llm_unavailable": self.llm_unavailable,
        })
        return base


# ---------------------------------------------------------------------------
# Document-level summary event
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DocumentProcessedEvent(BaseTelemetryEvent):
    """
    Финальное событие: весь pipeline завершён для документа.

    Семантика counters:
    - total_chunks: общее число retrieval-visible chunks across all levels.
    - total_units: enrichment units (Phase 12), не retrieval units.
    - legal_unit_chunks: число legal_unit-level retrieval chunks (P8.8d).
    """

    event_type: str = "document_processed"

    total_segments: int = 0
    total_nodes: int = 0
    total_chunks: int = 0           # Retrieval-visible chunks across all levels.
    total_units: int = 0            # Enrichment units only (Phase 12), not retrieval corpus size.
    legal_unit_chunks: int = 0      # Retrieval chunks with kind=legal_unit.

    avg_orphan_ratio: float = 0.0
    avg_grammar_violation_ratio: float = 0.0
    avg_retrieval_safety_score: float = 0.0
    any_degraded: bool = False
    any_technical_fallback: bool = False

    enrichment_applied_count: int = 0
    enrichment_failed_count: int = 0
    enrichment_skipped_count: int = 0
    enrichment_llm_unavailable: bool = False

    retrieval_safe_chunks: int = 0
    overall_retrieval_safe: bool = False
    recommended_action: str = "unknown"

    # Cross-segment coherence (Phase 13.7)
    coherence_links_found: int = 0
    coherence_avg_confidence: float = 0.0
    coherence_resolver_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "total_segments": self.total_segments,
            "total_nodes": self.total_nodes,
            "total_chunks": self.total_chunks,
            "total_units": self.total_units,
            "legal_unit_chunks": self.legal_unit_chunks,
            "avg_orphan_ratio": round(self.avg_orphan_ratio, 4),
            "avg_grammar_violation_ratio": round(self.avg_grammar_violation_ratio, 4),
            "avg_retrieval_safety_score": round(self.avg_retrieval_safety_score, 4),
            "any_degraded": self.any_degraded,
            "any_technical_fallback": self.any_technical_fallback,
            "enrichment_applied_count": self.enrichment_applied_count,
            "enrichment_failed_count": self.enrichment_failed_count,
            "enrichment_skipped_count": self.enrichment_skipped_count,
            "enrichment_llm_unavailable": self.enrichment_llm_unavailable,
            "retrieval_safe_chunks": self.retrieval_safe_chunks,
            "overall_retrieval_safe": self.overall_retrieval_safe,
            "recommended_action": self.recommended_action,
            "coherence_links_found": self.coherence_links_found,
            "coherence_avg_confidence": round(self.coherence_avg_confidence, 4),
            "coherence_resolver_error": self.coherence_resolver_error,
        })
        return base

