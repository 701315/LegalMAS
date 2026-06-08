from services.structure.chunk_planner._retrieval_readiness import (
    build_retrieval_readiness_report,
)


def test_retrieval_readiness_counts_legal_unit_chunks_as_retrieval_corpus() -> None:
    report = build_retrieval_readiness_report(
        document_id="doc-1",
        chunks=[
            {
                "id": "doc-1:u1",
                "text": "Definition 1",
                "metadata": {
                    "chunk_kind": "legal_unit",
                    "retrieval_safe": True,
                },
            },
            {
                "id": "doc-1:u2",
                "text": "Definition 2",
                "metadata": {
                    "chunk_kind": "legal_unit",
                    "retrieval_safe": True,
                },
            },
        ],
    )

    assert report.total_chunks == 2
    assert report.retrieval_safe_chunks == 2
    assert report.degraded_chunks == 0
    assert report.layout_fallback_chunks == 0
    assert report.overall_retrieval_safe is True
    assert report.recommended_action == "proceed"
    assert report.warnings == ()


def test_retrieval_readiness_marks_partial_legal_unit_corpus_as_cautious() -> None:
    report = build_retrieval_readiness_report(
        document_id="doc-2",
        chunks=[
            {
                "id": "doc-2:u1",
                "text": "Safe unit",
                "metadata": {
                    "chunk_kind": "legal_unit",
                    "retrieval_safe": True,
                },
            },
            {
                "id": "doc-2:u2",
                "text": "Unsafe unit",
                "metadata": {
                    "chunk_kind": "legal_unit",
                    "retrieval_safe": False,
                    "prefer_layout_fallback": True,
                },
            },
        ],
    )

    assert report.total_chunks == 2
    assert report.retrieval_safe_chunks == 1
    assert report.degraded_chunks == 1
    assert report.layout_fallback_chunks == 1
    assert report.overall_retrieval_safe is False
    assert report.recommended_action == "proceed_with_caution"
    assert "some_chunks_not_retrieval_safe" in report.warnings
    assert "layout_fallback_preferred_segments_present" in report.warnings


    