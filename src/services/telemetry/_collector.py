# src/services/telemetry/_collector.py

"""
TelemetryCollector — per-document in-memory telemetry sink.

Phase 13.1 — Telemetry Foundation.

Принципы:
- Один collector на один document processing run.
- Thread-safe для базового использования.
- Failure-isolated: emit никогда не бросает исключение.
- Не пишет в БД или MinIO напрямую.
- Можно сериализовать через to_dict() для audit log.

Использование:
    collector = TelemetryCollector(document_id="doc123")
    collector.emit(StructureBuiltEvent(...))
    collector.emit(QualityEvaluatedEvent(...))
    summary = collector.build_document_summary()
    logger.info("pipeline_complete", **summary.to_dict())
"""

from __future__ import annotations

import time
from typing import Any

from core.logging import get_logger
from services.telemetry._events import (
    BaseTelemetryEvent,
    ChunkingCompletedEvent,
    DocumentProcessedEvent,
    EnrichmentCompletedEvent,
    QualityEvaluatedEvent,
    StructureBuiltEvent,
)

logger = get_logger(__name__)


class TelemetryCollector:
    """
    Per-document telemetry collector.

    Собирает typed events в процессе обработки документа.
    Умеет строить агрегированный DocumentProcessedEvent.
    """

    def __init__(self, *, document_id: str) -> None:
        self.document_id = document_id
        self._events: list[BaseTelemetryEvent] = []
        self._start_ms = time.monotonic() * 1000

    # ── Public API ────────────────────────────────────────────────────────

    def emit(self, event: BaseTelemetryEvent) -> None:
        """
        Добавить event в collector.

        Failure-isolated: любая ошибка логируется и игнорируется.
        """
        try:
            self._events.append(event)
            logger.debug(
                f"TELEMETRY {event.event_type}",
                **{k: v for k, v in event.to_dict().items()
                   if v is not None},
            )
        except Exception as exc:
            logger.warning(
                "TELEMETRY emit_failed",
                event_type=getattr(event, "event_type", "unknown"),
                error=str(exc),
            )

    def elapsed_ms(self) -> float:
        """Время с момента создания collector в ms."""
        return round(time.monotonic() * 1000 - self._start_ms, 1)

    def events_by_type(
        self,
        event_type: type,
    ) -> list[BaseTelemetryEvent]:
        """Вернуть все events заданного типа."""
        return [e for e in self._events if isinstance(e, event_type)]

    def build_document_summary(self) -> DocumentProcessedEvent:
        """
        Агрегировать все события в финальный DocumentProcessedEvent.
        """
        try:
            return self._aggregate()
        except Exception as exc:
            logger.warning(
                "TELEMETRY build_document_summary_failed",
                document_id=self.document_id,
                error=str(exc),
            )
            return DocumentProcessedEvent(
                document_id=self.document_id,
                elapsed_ms=self.elapsed_ms(),
            )

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать все events в список dict."""
        return {
            "document_id": self.document_id,
            "elapsed_ms": self.elapsed_ms(),
            "events_count": len(self._events),
            "events": [e.to_dict() for e in self._events],
        }

    # ── Internal aggregation ──────────────────────────────────────────────

    def _aggregate(self) -> DocumentProcessedEvent:
        structure_events = self.events_by_type(StructureBuiltEvent)
        quality_events = self.events_by_type(QualityEvaluatedEvent)
        chunking_events = self.events_by_type(ChunkingCompletedEvent)
        enrichment_events = self.events_by_type(EnrichmentCompletedEvent)

        # Structure aggregates
        total_nodes = sum(
            getattr(e, "total_nodes", 0) for e in structure_events
        )
        any_degraded = any(
            getattr(e, "degraded", False) for e in structure_events
        )
        any_technical_fallback = any(
            getattr(e, "final_mode", "") == "technical_fallback"
            for e in structure_events
        )
        avg_orphan_ratio = _safe_avg(
            [getattr(e, "orphan_ratio", 0.0) for e in structure_events]
        )
        avg_grammar_ratio = _safe_avg(
            [getattr(e, "grammar_violation_ratio", 0.0)
             for e in structure_events]
        )

        # Quality aggregates
        avg_safety = _safe_avg(
            [getattr(e, "retrieval_safety_score", 0.0)
             for e in quality_events]
        )

        # Chunking aggregates
        total_chunks = sum(
            getattr(e, "total_chunks", 0) for e in chunking_events
        )
        retrieval_safe_chunks = sum(
            getattr(e, "retrieval_safe_chunks", 0)
            for e in chunking_events
        )
        overall_retrieval_safe = (
            retrieval_safe_chunks == total_chunks and total_chunks > 0
        )
        recommended_action = _best_recommended_action(chunking_events)

        # Enrichment aggregates
        total_units = sum(
            getattr(e, "total_units", 0) for e in enrichment_events
        )
        enrichment_applied = sum(
            getattr(e, "applied_count", 0) for e in enrichment_events
        )
        enrichment_failed = sum(
            getattr(e, "failed_count", 0) for e in enrichment_events
        )
        enrichment_skipped = sum(
            getattr(e, "skipped_count", 0) for e in enrichment_events
        )
        llm_unavailable = any(
            getattr(e, "llm_unavailable", False)
            for e in enrichment_events
        )

        return DocumentProcessedEvent(
            document_id=self.document_id,
            elapsed_ms=self.elapsed_ms(),
            total_segments=max(
                len(structure_events),
                len(quality_events),
                len(chunking_events),
            ),
            total_nodes=total_nodes,
            total_chunks=total_chunks,
            total_units=total_units,
            avg_orphan_ratio=avg_orphan_ratio,
            avg_grammar_violation_ratio=avg_grammar_ratio,
            avg_retrieval_safety_score=avg_safety,
            any_degraded=any_degraded,
            any_technical_fallback=any_technical_fallback,
            enrichment_applied_count=enrichment_applied,
            enrichment_failed_count=enrichment_failed,
            enrichment_skipped_count=enrichment_skipped,
            enrichment_llm_unavailable=llm_unavailable,
            retrieval_safe_chunks=retrieval_safe_chunks,
            overall_retrieval_safe=overall_retrieval_safe,
            recommended_action=recommended_action,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _best_recommended_action(
    events: list[BaseTelemetryEvent],
) -> str:
    """
    Выбирает наихудшее recommended_action из всех chunking events.

    Порядок severity: skip > proceed_with_caution > proceed > unknown.
    """
    priority = {"skip": 3, "proceed_with_caution": 2, "proceed": 1, "unknown": 0}
    best = "unknown"
    for e in events:
        action = getattr(e, "retrieval_recommended_action", "unknown")
        if priority.get(action, 0) > priority.get(best, 0):
            best = action
    return best


