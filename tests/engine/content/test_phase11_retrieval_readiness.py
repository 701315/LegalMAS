from services.structure.chunk_planner import (
    build_retrieval_readiness_report,
)
from engine.content._document_content_chunks import (
    enrich_chunk_with_planning_signal,
)
from services.structure._models._analysis import RecommendedChunkingMode


def _make_chunk(meta: dict):
    return {
        "id": "chunk-1",
        "text": "Some legal clause text.",
        "metadata": meta,
    }


def test_enrich_without_planning():
    ch = _make_chunk({})
    enriched = enrich_chunk_with_planning_signal(
        ch,
        segment_planning=None,
    )
    assert enriched["metadata"]["retrieval_safe"] is True


def test_enrich_with_planning():
    ch = _make_chunk({})
    planning = {
        "mode": "hybrid",
        "retrieval_safe": False,
        "prefer_layout_fallback": False,
    }
    enriched = enrich_chunk_with_planning_signal(
        ch,
        segment_planning=planning,
    )
    assert enriched["metadata"]["retrieval_safe"] is False
    assert enriched["metadata"]["chunking_mode"] == "hybrid"


def test_readiness_all_safe():
    chunks = [
        _make_chunk({"retrieval_safe": True}),
        _make_chunk({"retrieval_safe": True}),
    ]
    report = build_retrieval_readiness_report(
        document_id="doc-1",
        chunks=chunks,
    )
    assert report.recommended_action == "proceed"


def test_readiness_partial_degraded():
    chunks = [
        _make_chunk({"retrieval_safe": True}),
        _make_chunk({"retrieval_safe": False}),
    ]
    report = build_retrieval_readiness_report(
        document_id="doc-1",
        chunks=chunks,
    )
    assert report.recommended_action == "proceed_with_caution"


def test_readiness_all_degraded():
    chunks = [
        _make_chunk({"retrieval_safe": False}),
        _make_chunk({"retrieval_safe": False}),
    ]
    report = build_retrieval_readiness_report(
        document_id="doc-1",
        chunks=chunks,
    )
    assert report.recommended_action == "skip"


    