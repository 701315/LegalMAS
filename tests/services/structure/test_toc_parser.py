from services.structure.toc_parser import (
    TOCBlock,
    ParsedTOC,
    parse_toc_entries,
)


def test_parse_toc_entries_supports_dot_leaders():
    toc_block = TOCBlock(
        detected=True,
        start_index=0,
        end_index=2,
        reason="marker_detected",
        elements=[
            {"text": "1. Definitions .......... 4", "page": 1},
            {"text": "2. Representations and Warranties .......... 8", "page": 1},
        ],
    )

    result = parse_toc_entries(toc_block)

    assert isinstance(result, ParsedTOC)
    assert result.detected is True
    assert len(result.entries) == 2

    assert result.entries[0].uid == "1"
    assert result.entries[0].title == "Definitions"
    assert result.entries[0].page_hint == 4

    assert result.entries[1].uid == "2"
    assert result.entries[1].title == "Representations and Warranties"
    assert result.entries[1].page_hint == 8


def test_parse_toc_entries_supports_multiline_entries():
    toc_block = TOCBlock(
        detected=True,
        start_index=0,
        end_index=2,
        reason="marker_detected",
        elements=[
            {"text": "3. Representations and", "page": 2},
            {"text": "Warranties .......... 11", "page": 2},
        ],
    )

    result = parse_toc_entries(toc_block)

    assert isinstance(result, ParsedTOC)
    assert len(result.entries) == 1
    assert result.entries[0].uid == "3"
    assert result.entries[0].title == "Representations and Warranties"
    assert result.entries[0].page_hint == 11
    assert result.entries[0].diagnostics["multiline"] is True