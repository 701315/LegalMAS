"""Юнит-тесты: element_offsets — pre-normalize и post-normalize."""
from engine.content.element_offsets import (
    _strip_element_lines,
    compute_element_offsets,
    compute_element_offsets_for_normalized_text,
    span_to_element_ids,
)


# ── compute_element_offsets (pre-normalize) ────────────────────────────────

def test_pre_normalize_two_elements_same_page():
    els = [
        {"element_id": "el_1", "text": "ДОГОВОР", "page": 1, "_seq": 0},
        {"element_id": "el_2", "text": "Между ООО Ромашка", "page": 1, "_seq": 1},
    ]
    src = "ДОГОВОР\n\nМежду ООО Ромашка"
    offsets, ok = compute_element_offsets(els, src)
    assert ok is True
    assert offsets == [("el_1", 0, 7), ("el_2", 9, 26)]


def test_pre_normalize_page_boundary_inserts_extra_separator():
    # Page change adds an empty piece -> text becomes 4 newlines.
    els = [
        {"element_id": "el_1", "text": "ДОГОВОР", "page": 1, "_seq": 0},
        {"element_id": "el_2", "text": "Между ООО Ромашка", "page": 2, "_seq": 1},
    ]
    src = "ДОГОВОР\n\n\n\nМежду ООО Ромашка"
    offsets, ok = compute_element_offsets(els, src)
    assert ok is True
    assert offsets == [("el_1", 0, 7), ("el_2", 11, 28)]


def test_pre_normalize_sort_by_seq():
    els = [
        {"element_id": "el_2", "text": "ВТОРОЙ", "page": 1, "_seq": 1},
        {"element_id": "el_1", "text": "ПЕРВЫЙ", "page": 1, "_seq": 0},
    ]
    src = "ПЕРВЫЙ\n\nВТОРОЙ"
    offsets, ok = compute_element_offsets(els, src)
    assert ok is True
    assert [eid for eid, _, _ in offsets] == ["el_1", "el_2"]


def test_pre_normalize_mismatch_ok_false():
    els = [{"element_id": "el_1", "text": "ДОГОВОР", "page": 1, "_seq": 0}]
    offsets, ok = compute_element_offsets(els, "ДРУГОЙ ТЕКСТ")
    assert ok is False


# ── compute_element_offsets_for_normalized_text (post-normalize) ───────────

def test_post_normalize_two_elements_same_page():
    els = [
        {"element_id": "el_1", "text": "ДОГОВОР", "page": 1, "_seq": 0},
        {"element_id": "el_2", "text": "Между ООО Ромашка", "page": 1, "_seq": 1},
    ]
    src = "ДОГОВОР\n\nМежду ООО Ромашка"
    offsets, ok = compute_element_offsets_for_normalized_text(els, src)
    assert ok is True
    assert offsets == [("el_1", 0, 7), ("el_2", 9, 26)]


def test_post_normalize_page_boundary_collapsed_to_two_newlines():
    # This is the exact scenario that broke the previous test:
    # after normalize, page boundary == within-page separator.
    els = [
        {"element_id": "el_1", "text": "ДОГОВОР", "page": 1, "_seq": 0},
        {"element_id": "el_2", "text": "Между ООО Ромашка", "page": 2, "_seq": 1},
    ]
    src = "ДОГОВОР\n\nМежду ООО Ромашка"  # normalized output
    offsets, ok = compute_element_offsets_for_normalized_text(els, src)
    assert ok is True
    assert offsets == [("el_1", 0, 7), ("el_2", 9, 26)]


def test_post_normalize_element_not_found():
    els = [
        {"element_id": "el_1", "text": "ДОГОВОР", "page": 1, "_seq": 0},
        {"element_id": "el_2", "text": "ОТСУТСТВУЕТ", "page": 1, "_seq": 1},
    ]
    src = "ДОГОВОР\n\nМежду ООО Ромашка"
    offsets, ok = compute_element_offsets_for_normalized_text(els, src)
    assert ok is False
    assert offsets == []


def test_post_normalize_duplicate_text_uses_cursor():
    els = [
        {"element_id": "el_1", "text": "А", "page": 1, "_seq": 0},
        {"element_id": "el_2", "text": "А", "page": 1, "_seq": 1},
    ]
    src = "А\n\nА"
    offsets, ok = compute_element_offsets_for_normalized_text(els, src)
    assert ok is True
    assert offsets == [("el_1", 0, 1), ("el_2", 3, 4)]


def test_post_normalize_multiline_element():
    els = [
        {"element_id": "el_1", "text": "Line1\nLine2", "page": 1, "_seq": 0},
        {"element_id": "el_2", "text": "After", "page": 1, "_seq": 1},
    ]
    src = "Line1\nLine2\n\nAfter"
    offsets, ok = compute_element_offsets_for_normalized_text(els, src)
    assert ok is True
    assert offsets == [("el_1", 0, 11), ("el_2", 13, 18)]


def test_post_normalize_whitespace_per_line_stripped():
    els = [
        {"element_id": "el_1", "text": "  Line1  \n  Line2  ", "page": 1, "_seq": 0},
    ]
    src = "Line1\nLine2"
    offsets, ok = compute_element_offsets_for_normalized_text(els, src)
    assert ok is True
    assert offsets == [("el_1", 0, 11)]


# ── span_to_element_ids ───────────────────────────────────────────────────

def test_span_to_element_ids_partial_overlap():
    offsets = [("el_1", 0, 7), ("el_2", 9, 26)]
    assert span_to_element_ids(5, 15, offsets) == ["el_1", "el_2"]


def test_span_to_element_ids_single_element():
    offsets = [("el_1", 0, 7), ("el_2", 9, 26)]
    assert span_to_element_ids(10, 15, offsets) == ["el_2"]


# ── _strip_element_lines ──────────────────────────────────────────────────

def test_strip_element_lines_collapses_blanks():
    assert _strip_element_lines("A\n\n\n\nB") == "A\n\nB"


def test_strip_element_lines_per_line_strip():
    assert _strip_element_lines("  A  \n  B  ") == "A\nB"


def test_strip_element_lines_empty():
    assert _strip_element_lines("") == ""
    assert _strip_element_lines("   \n  \n ") == ""
