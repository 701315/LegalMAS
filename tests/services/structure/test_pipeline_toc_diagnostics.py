def test_pipeline_toc_diagnostics_contains_alignment_fields():
    diagnostics = {
        "toc": {
            "entries_total": 2,
            "toc_alignment_score": 0.91,
            "partial_reliability": 0.88,
            "is_reliable": True,
            "confidence_band": "high",
            "exact_matches": 1,
            "fuzzy_matches": 1,
            "no_matches": 0,
            "stale_entries": 0,
            "mismatch_details": [],
            "reasons": ["sufficient_exact_and_fuzzy_matches"],
            "match_index_size": 2,
        }
    }

    assert "toc_alignment_score" in diagnostics["toc"]
    assert "partial_reliability" in diagnostics["toc"]
    assert "is_reliable" in diagnostics["toc"]
    assert "mismatch_details" in diagnostics["toc"]

    