from services.telemetry._collector import TelemetryCollector
from services.telemetry._events import (
    ChunkingCompletedEvent,
    EnrichmentCompletedEvent,
    QualityEvaluatedEvent,
)


def test_document_summary_uses_chunk_corpus_as_canonical_retrieval_safety() -> None:
    collector = TelemetryCollector(document_id="doc-1")

    # legacy quality score не должен перетёреть real chunk-corpus truth
    collector.emit(QualityEvaluatedEvent(
        document_id="doc-1",
        segment_id="seg-1",
        retrieval_safety_score=0.2,
    ))

    collector.emit(ChunkingCompletedEvent(
        document_id="doc-1",
        segment_id="seg-1",
        total_chunks=3,
        section_chunks=1,
        legal_unit_chunks=2,
        retrieval_safe_chunks=3,
        retrieval_recommended_action="proceed",
    ))
    collector.emit(ChunkingCompletedEvent(
        document_id="doc-1",
        segment_id="seg-2",
        total_chunks=2,
        legal_unit_chunks=2,
        retrieval_safe_chunks=1,
        degraded_chunks=1,
        layout_fallback_chunks=1,
        retrieval_recommended_action="proceed_with_caution",
    ))

    summary = collector.build_document_summary()

    assert summary.total_chunks == 5
    assert summary.legal_unit_chunks == 4
    assert summary.retrieval_safe_chunks == 4
    assert summary.avg_retrieval_safety_score == 0.8
    assert summary.overall_retrieval_safe is False
    assert summary.recommended_action == "proceed_with_caution"


def test_document_summary_falls_back_to_quality_score_when_no_chunking_events() -> None:
    collector = TelemetryCollector(document_id="doc-2")

    collector.emit(QualityEvaluatedEvent(
        document_id="doc-2",
        segment_id="seg-1",
        retrieval_safety_score=0.7,
    ))
    collector.emit(QualityEvaluatedEvent(
        document_id="doc-2",
        segment_id="seg-2",
        retrieval_safety_score=0.9,
    ))

    summary = collector.build_document_summary()

    assert summary.total_chunks == 0
    assert summary.retrieval_safe_chunks == 0
    assert summary.avg_retrieval_safety_score == 0.8
    assert summary.legal_unit_chunks == 0


def test_document_summary_keeps_enrichment_units_separate_from_legal_unit_chunks() -> None:
    collector = TelemetryCollector(document_id="doc-3")

    collector.emit(ChunkingCompletedEvent(
        document_id="doc-3",
        segment_id="seg-1",
        total_chunks=4,
        section_chunks=1,
        legal_unit_chunks=3,
        retrieval_safe_chunks=4,
        retrieval_recommended_action="proceed",
    ))
    collector.emit(EnrichmentCompletedEvent(
        document_id="doc-3",
        segment_id="seg-1",
        total_units=2,
        applied_count=2,
    ))

    summary = collector.build_document_summary()

    assert summary.total_units == 2
    assert summary.legal_unit_chunks == 3
    assert summary.total_chunks == 4
    assert summary.retrieval_safe_chunks == 4
    assert summary.avg_retrieval_safety_score == 1.0
    assert summary.overall_retrieval_safe is True
    assert summary.to_dict()["legal_unit_chunks"] == 3

    