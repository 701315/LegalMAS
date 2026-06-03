from __future__ import annotations

from types import SimpleNamespace

from workers.build_primary_language_source import (
    _determine_primary_source_build_mode,
    _primary_layout_materially_differs,
)


def _layout(elements: list[dict], *, metadata: dict | None = None) -> dict:
    return {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "elements": elements,
        "tables": [],
        "metadata": metadata or {},
    }


def test_primary_layout_materially_differs_false_for_identical_layouts():
    raw_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
            {"page": 1, "type": "text", "text": "Текст договора"},
        ]
    )
    primary_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
            {"page": 1, "type": "text", "text": "Текст договора"},
        ]
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is False


def test_primary_layout_materially_differs_false_for_metadata_only_changes():
    raw_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
        ],
        metadata={},
    )
    primary_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
        ],
        metadata={
            "language_pipeline": {"target_language": "ru"},
            "language_filter": {"structural_filter_used": False},
        },
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is False


def test_primary_layout_materially_differs_false_for_whitespace_only_text_changes():
    raw_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1   ДОГОВОР"},
        ]
    )
    primary_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
        ]
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is False


def test_primary_layout_materially_differs_true_when_element_removed_by_filter():
    raw_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
            {"page": 1, "type": "heading", "text": "1 SALE AGREEMENT"},
        ]
    )
    primary_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
        ]
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is True


def test_primary_layout_materially_differs_true_when_text_changed_by_filter():
    raw_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР / SALE AGREEMENT"},
        ]
    )
    primary_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
        ]
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is True


def test_determine_primary_source_build_mode_returns_reuse_for_unchanged_non_bilingual():
    decision = SimpleNamespace(is_bilingual=False)
    raw_layout = _layout(
        [{"page": 1, "type": "heading", "text": "1 ДОГОВОР"}]
    )
    primary_layout = _layout(
        [{"page": 1, "type": "heading", "text": "1 ДОГОВОР"}]
    )

    mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=raw_layout,
        primary_layout=primary_layout,
    )

    assert mode == "monolingual_reuse"


def test_determine_primary_source_build_mode_returns_filtered_pdf_for_changed_non_bilingual():
    decision = SimpleNamespace(is_bilingual=False)
    raw_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
            {"page": 1, "type": "heading", "text": "1 SALE AGREEMENT"},
        ]
    )
    primary_layout = _layout(
        [
            {"page": 1, "type": "heading", "text": "1 ДОГОВОР"},
        ]
    )

    mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=raw_layout,
        primary_layout=primary_layout,
    )

    assert mode == "monolingual_filtered_pdf"


def test_determine_primary_source_build_mode_returns_single_language_pdf_for_bilingual():
    decision = SimpleNamespace(is_bilingual=True)
    raw_layout = _layout(
        [{"page": 1, "type": "heading", "text": "1 ДОГОВОР"}]
    )
    primary_layout = _layout(
        [{"page": 1, "type": "heading", "text": "1 ДОГОВОР"}]
    )

    mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=raw_layout,
        primary_layout=primary_layout,
    )

    assert mode == "single_language_pdf"


    