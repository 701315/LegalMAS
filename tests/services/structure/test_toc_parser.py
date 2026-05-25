from services.structure.toc_parser import parse_toc_entries


def test_parse_toc_entries_supports_dot_leaders():
    toc_lines = [
        {"text": "1. Definitions .......... 4", "page": 1},
        {"text": "2. Representations and Warranties .......... 8", "page": 1},
    ]

    entries = parse_toc_entries(toc_lines)

    assert len(entries) == 2
    assert entries[0].uid == "1"
    assert entries[0].title == "Definitions"
    assert entries[0].page_hint == 4

    assert entries[1].uid == "2"
    assert entries[1].title == "Representations and Warranties"
    assert entries[1].page_hint == 8


def test_parse_toc_entries_supports_multiline_entries():
    toc_lines = [
        {"text": "3. Representations and", "page": 2},
        {"text": "Warranties .......... 11", "page": 2},
    ]

    entries = parse_toc_entries(toc_lines)

    assert len(entries) == 1
    assert entries[0].uid == "3"
    assert entries[0].title == "Representations and Warranties"
    assert entries[0].page_hint == 11

    