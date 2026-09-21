"""Unit tests for B0.5: score_breakdown propagation into context_trace."""
from __future__ import annotations

from engine.checks.executor import CheckExecutor
from engine.detectors.models import RetrievedChunk


def _rc(eid: str = "e", page: int = 1) -> RetrievedChunk:
    return RetrievedChunk(element_id=eid, text="t", page=page)


def test_trace_carries_top_level_score_breakdown():
    c = {
        "id": "x", "text": "t", "metadata": {},
        "score_breakdown": {"bm25_norm": 0.4, "dense_norm": 0.6, "combined_score": 0.75},
    }
    result = CheckExecutor._build_context_provenance_trace([c], [_rc()], max_items=5)
    assert result[0]["score_breakdown"] == {
        "bm25_norm": 0.4, "dense_norm": 0.6, "combined_score": 0.75,
    }


def test_trace_score_breakdown_none_when_absent():
    c = {"id": "y", "text": "t", "metadata": {}}
    result = CheckExecutor._build_context_provenance_trace([c], [_rc()], max_items=5)
    assert result[0]["score_breakdown"] is None


def test_trace_ignores_metadata_score_breakdown():
    """score_breakdown must come from top-level, not from metadata (contract)."""
    c = {
        "id": "z", "text": "t",
        "metadata": {"score_breakdown": {"bm25_norm": 9.9}},
    }
    result = CheckExecutor._build_context_provenance_trace([c], [_rc()], max_items=5)
    assert result[0]["score_breakdown"] is None


def test_trace_max_items_cap():
    contexts = [{"id": f"c{i}", "text": "t", "metadata": {}, "score_breakdown": {"x": i}} for i in range(10)]
    rcs = [_rc(f"e{i}") for i in range(10)]
    result = CheckExecutor._build_context_provenance_trace(contexts, rcs, max_items=5)
    assert len(result) == 5
    assert result[0]["score_breakdown"] == {"x": 0}
    assert result[4]["score_breakdown"] == {"x": 4}
