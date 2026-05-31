"""
Tests for Phase 13.1 — Telemetry Foundation.

Покрывают:
1. StructureBuiltEvent.to_dict() — корректность сериализации
2. QualityEvaluatedEvent.to_dict()
3. ChunkingCompletedEvent.to_dict()
4. EnrichmentCompletedEvent.to_dict()
5. DocumentProcessedEvent.to_dict()
6. TelemetryCollector.emit() — не бросает исключений
7. TelemetryCollector.emit() — events накапливаются
8. TelemetryCollector.events_by_type() — фильтрация по типу
9. TelemetryCollector.build_document_summary() — агрегация
10. TelemetryCollector.build_document_summary() — avg_orphan_ratio
11. TelemetryCollector.build_document_summary() — enrichment aggregates
12. TelemetryCollector.build_document_summary() — recommended_action worst-case
13. TelemetryCollector.build_document_summary() — empty collector
14. TelemetryCollector.emit() — failure-isolated (invalid event не падает)
15. TelemetryCollector.to_dict() — содержит нужные ключи
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.telemetry import (
    TelemetryCollector,
    StructureBuiltEvent,
    QualityEvaluatedEvent,
    ChunkingCompletedEvent,
    EnrichmentCompletedEvent,
    DocumentProcessedEvent,
)


# ---------------------------------------------------------------------------
# 1–5. Event serialization
# ---------------------------------------------------------------------------

class TestEventSerialization:

    def test_structure_built_event_to_dict(self):
        event = StructureBuiltEvent(
            document_id="doc1",
            segment_id="seg1",
            total_nodes=42,
            orphan_ratio=0.05,
            overall_score=0.82,
            degraded=False,
            final_mode="semantic_tree",
        )
        d = event.to_dict()
        assert d["event_type"] == "structure_built"
        assert d["document_id"] == "doc1"
        assert d["segment_id"] == "seg1"
        assert d["total_nodes"] == 42
        assert d["orphan_ratio"] == 0.05
        assert d["overall_score"] == 0.82
        assert d["degraded"] is False
        assert d["final_mode"] == "semantic_tree"

    def test_quality_evaluated_event_to_dict(self):
        event = QualityEvaluatedEvent(
            document_id="doc1",
            retrieval_safety_score=0.75,
            retrieval_safe=True,
            recommended_chunking_mode="structure_first",
            warnings_count=1,
            critical_warnings_count=0,
            cohesion_available=True,
            cohesion_avg_score=0.68,
        )
        d = event.to_dict()
        assert d["event_type"] == "quality_evaluated"
        assert d["retrieval_safety_score"] == 0.75
        assert d["retrieval_safe"] is True
        assert d["cohesion_avg_score"] == 0.68

    def test_chunking_completed_event_to_dict(self):
        event = ChunkingCompletedEvent(
            document_id="doc1",
            total_chunks=120,
            section_chunks=10,
            clause_chunks=60,
            subclause_chunks=50,
            retrieval_safe_chunks=118,
            degraded_chunks=2,
            retrieval_recommended_action="proceed",
        )
        d = event.to_dict()
        assert d["event_type"] == "chunking_completed"
        assert d["total_chunks"] == 120
        assert d["retrieval_safe_chunks"] == 118
        assert d["retrieval_recommended_action"] == "proceed"

    def test_enrichment_completed_event_to_dict(self):
        event = EnrichmentCompletedEvent(
            document_id="doc1",
            total_units=30,
            applied_count=25,
            rejected_count=3,
            skipped_count=2,
            failed_count=0,
            applied_ratio=0.833,
            llm_provider="llamacpp",
            llm_model="qwen2.5-7b",
        )
        d = event.to_dict()
        assert d["event_type"] == "enrichment_completed"
        assert d["applied_count"] == 25
        assert d["applied_ratio"] == 0.833
        assert d["llm_provider"] == "llamacpp"
        assert d["failed_count"] == 0

    def test_document_processed_event_to_dict(self):
        event = DocumentProcessedEvent(
            document_id="doc1",
            total_segments=3,
            total_chunks=150,
            total_units=80,
            avg_orphan_ratio=0.02,
            avg_retrieval_safety_score=0.78,
            overall_retrieval_safe=True,
            recommended_action="proceed",
        )
        d = event.to_dict()
        assert d["event_type"] == "document_processed"
        assert d["total_segments"] == 3
        assert d["overall_retrieval_safe"] is True
        assert d["recommended_action"] == "proceed"


# ---------------------------------------------------------------------------
# 6–15. TelemetryCollector
# ---------------------------------------------------------------------------

class TestTelemetryCollector:

    def test_emit_does_not_raise(self):
        collector = TelemetryCollector(document_id="doc1")
        event = StructureBuiltEvent(document_id="doc1", total_nodes=10)
        collector.emit(event)  # не должно падать

    def test_emit_accumulates_events(self):
        collector = TelemetryCollector(document_id="doc1")
        collector.emit(StructureBuiltEvent(document_id="doc1", total_nodes=5))
        collector.emit(StructureBuiltEvent(document_id="doc1", total_nodes=8))
        assert len(collector._events) == 2

    def test_events_by_type_filters_correctly(self):
        collector = TelemetryCollector(document_id="doc1")
        collector.emit(StructureBuiltEvent(document_id="doc1"))
        collector.emit(QualityEvaluatedEvent(document_id="doc1"))
        collector.emit(StructureBuiltEvent(document_id="doc1"))

        structure_events = collector.events_by_type(StructureBuiltEvent)
        quality_events = collector.events_by_type(QualityEvaluatedEvent)

        assert len(structure_events) == 2
        assert len(quality_events) == 1

    def test_build_document_summary_returns_document_processed_event(self):
        collector = TelemetryCollector(document_id="doc1")
        collector.emit(StructureBuiltEvent(document_id="doc1", total_nodes=50))
        collector.emit(QualityEvaluatedEvent(
            document_id="doc1",
            retrieval_safety_score=0.80,
            retrieval_safe=True,
        ))

        summary = collector.build_document_summary()
        assert isinstance(summary, DocumentProcessedEvent)
        assert summary.document_id == "doc1"
        assert summary.total_nodes == 50

    def test_build_document_summary_avg_orphan_ratio(self):
        collector = TelemetryCollector(document_id="doc1")
        collector.emit(StructureBuiltEvent(
            document_id="doc1", orphan_ratio=0.10
        ))
        collector.emit(StructureBuiltEvent(
            document_id="doc1", orphan_ratio=0.20
        ))

        summary = collector.build_document_summary()
        assert abs(summary.avg_orphan_ratio - 0.15) < 0.001

    def test_build_document_summary_enrichment_aggregates(self):
        collector = TelemetryCollector(document_id="doc1")
        collector.emit(EnrichmentCompletedEvent(
            document_id="doc1",
            total_units=20,
            applied_count=15,
            failed_count=2,
            skipped_count=3,
        ))
        collector.emit(EnrichmentCompletedEvent(
            document_id="doc1",
            total_units=10,
            applied_count=8,
            failed_count=0,
            skipped_count=2,
        ))

        summary = collector.build_document_summary()
        assert summary.total_units == 30
        assert summary.enrichment_applied_count == 23
        assert summary.enrichment_failed_count == 2
        assert summary.enrichment_skipped_count == 5

    def test_build_document_summary_worst_recommended_action(self):
        """worst-case wins: если хоть один segment skip → итог skip."""
        collector = TelemetryCollector(document_id="doc1")
        collector.emit(ChunkingCompletedEvent(
            document_id="doc1",
            total_chunks=50,
            retrieval_safe_chunks=50,
            retrieval_recommended_action="proceed",
        ))
        collector.emit(ChunkingCompletedEvent(
            document_id="doc1",
            total_chunks=10,
            retrieval_safe_chunks=0,
            retrieval_recommended_action="skip",
        ))

        summary = collector.build_document_summary()
        assert summary.recommended_action == "skip"

    def test_build_document_summary_empty_collector(self):
        """Пустой collector не падает."""
        collector = TelemetryCollector(document_id="doc1")
        summary = collector.build_document_summary()
        assert summary.document_id == "doc1"
        assert summary.total_segments == 0
        assert summary.total_chunks == 0
        assert summary.recommended_action == "unknown"

    def test_emit_failure_isolated(self):
        """emit с невалидным event не падает."""
        collector = TelemetryCollector(document_id="doc1")
        bad_event = MagicMock()
        bad_event.event_type = "bad"
        bad_event.to_dict.side_effect = RuntimeError("serialization error")
        # Не должно бросить исключение
        collector.emit(bad_event)

    def test_to_dict_has_required_keys(self):
        collector = TelemetryCollector(document_id="doc1")
        collector.emit(StructureBuiltEvent(document_id="doc1"))
        d = collector.to_dict()
        assert "document_id" in d
        assert "elapsed_ms" in d
        assert "events_count" in d
        assert "events" in d
        assert d["events_count"] == 1


        