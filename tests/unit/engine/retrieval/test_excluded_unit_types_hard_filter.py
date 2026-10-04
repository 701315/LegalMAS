"""Тест: excluded_unit_types — hard filter, не soft penalty."""
from engine.retrieval.engine import RetrievalEngine


def _chunk(chunk_id, text, unit_type):
    return {
        "id": chunk_id,
        "text": text,
        "metadata": {"unit_type": unit_type, "summary": text[:30]},
    }


def test_excluded_chunk_absent_from_results():
    chunks = [
        _chunk("c1", "premble about parties and identities " * 5, "structural_anchor"),
        _chunk("c2", "real body text about tenant obligations " * 5, "obligation"),
        _chunk("c3", "more body text about rent payment " * 5, "payment_term"),
    ]
    engine = RetrievalEngine(chunks, excluded_unit_types=["structural_anchor"])
    results = engine.search("tenant", top_k=5)
    ids = [r["id"] for r in results]
    assert "c1" not in ids
    assert "c2" in ids
    assert "c3" in ids


def test_no_exclusions_returns_all():
    chunks = [
        _chunk("c1", "text about tenant", "structural_anchor"),
        _chunk("c2", "text about landlord", "obligation"),
    ]
    engine = RetrievalEngine(chunks)
    results = engine.search("text", top_k=5)
    assert len(results) == 2


def test_all_excluded_returns_empty():
    chunks = [
        _chunk("c1", "some text", "structural_anchor"),
        _chunk("c2", "some text", "structural_anchor"),
    ]
    engine = RetrievalEngine(chunks, excluded_unit_types=["structural_anchor"])
    results = engine.search("text", top_k=5)
    assert results == []


def test_unit_type_case_insensitive():
    chunks = [
        _chunk("c1", "text", "Structural_Anchor"),
        _chunk("c2", "text", "obligation"),
    ]
    engine = RetrievalEngine(chunks, excluded_unit_types=["structural_anchor"])
    results = engine.search("text", top_k=5)
    ids = [r["id"] for r in results]
    assert "c1" not in ids
