from services.structure.heading_builder import collect_scored_heading_candidates


def test_collect_scored_heading_candidates_propagates_toc_metadata():
    elements = [
        {
            "text": "1. Definitions",
            "page": 1,
            "scope": "main_contract",
            "segment_id": "seg-1",
            "segment_type": "contract",
            "segment_order": 0,
            "element_type": "heading_candidate",
            "page_offset": 0.01,
            "formatting": {"is_bold": True},
            "ocr_confidence": 0.99,
        }
    ]

    toc_match_index = {
        ("1", "definitions"): {
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 3,
            "toc_missing_in_body": False,
        }
    }

    candidates = collect_scored_heading_candidates(
        elements,
        document_id="doc-1",
        toc_match_index=toc_match_index,
    )

    assert len(candidates) == 1
    candidate = candidates[0]

    assert candidate.decision == "accepted"
    assert candidate.metadata["toc_match"] is not None
    assert candidate.metadata["toc_match_type"] == "exact"
    assert candidate.metadata["toc_match_score"] == 0.05



    