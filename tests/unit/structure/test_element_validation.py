from services.structure._pipeline._element_validation import (
    ensure_element_segment_metadata,
)
from services.structure.models import SegmentDocument


def _segment() -> SegmentDocument:
    return SegmentDocument(
        document_id="document-1",
        segment_id="seg-1",
        segment_type="contract",
        segment_title="",
        segment_order=0,
        scope_name="main_contract",
        page_start=1,
        page_end=1,
        element_start=0,
        element_end=1,
        is_primary=True,
    )


def test_existing_element_type_is_preserved() -> None:
    prepared = ensure_element_segment_metadata(
        elements=[{"text": "x", "element_type": "toc_line"}],
        segment=_segment(),
    )

    assert prepared[0]["element_type"] == "toc_line"


def test_heading_layout_becomes_candidate_only_on_fallback() -> None:
    prepared = ensure_element_segment_metadata(
        elements=[{"text": "Title", "type": "heading", "label": "title"}],
        segment=_segment(),
    )

    assert prepared[0]["element_type"] == "heading_candidate"
    assert prepared[0]["metadata"]["structure_type_source"] == "layout_fallback"


def test_table_layout_becomes_table_content_on_fallback() -> None:
    prepared = ensure_element_segment_metadata(
        elements=[{"text": "x", "type": "table", "is_table": True}],
        segment=_segment(),
    )

    assert prepared[0]["element_type"] == "table_content"


def test_unknown_layout_is_not_rewritten_as_body_text() -> None:
    prepared = ensure_element_segment_metadata(
        elements=[{"text": "ordinary extracted block"}],
        segment=_segment(),
    )

    assert prepared[0]["element_type"] == "unknown_layout"



    