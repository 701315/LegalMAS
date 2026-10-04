"""Тест: Priority 0 использует element_spans через owner-chunk из chunk_map."""
from engine.checks.extraction import ExtractionExecutor


LONG_QUOTE = "Между ООО Ромашка"
LONG_SOURCE = "ДОГОВОР КРАТКОСРОЧНОЙ АРЕНДЫ\n\nМежду ООО Ромашка"


class _Dummy(ExtractionExecutor):
    def __init__(self):
        pass


def _ctx_with_spans(spans):
    return {"metadata": {"element_spans": spans}}


def test_owner_chunk_uses_element_spans_for_precise_page():
    """chunk_map содержит один чанк [0:47]; spans на стр.1 и стр.2."""
    ex = _Dummy()
    spans = [
        ["el_1", 1, 0, 28],
        ["el_2", 2, 30, 47],
    ]
    chunk_map = [(0, 47, _ctx_with_spans(spans), None)]
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        chunk_map=chunk_map,
        field_page=1,
    )
    assert anchor is not None
    assert anchor.page == 2


def test_owner_chunk_second_in_chain():
    """Два context'а: anchor попадает во второй; span сдвигается."""
    ex = _Dummy()
    chunk1_text = "ДОГОВОР КРАТКОСРОЧНОЙ АРЕНДЫ"
    chunk2_text = "Между ООО Ромашка"
    full = chunk1_text + "\n\n" + chunk2_text

    chunk1_start = 0
    chunk1_end = len(chunk1_text)
    chunk2_start = chunk1_end + 2
    chunk2_end = chunk2_start + len(chunk2_text)

    spans_c2 = [["el_x", 5, 0, len(chunk2_text)]]

    chunk_map = [
        (chunk1_start, chunk1_end, {"metadata": {}}, None),
        (chunk2_start, chunk2_end, _ctx_with_spans(spans_c2), None),
    ]

    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=full,
        fallback_clause_uid=None,
        fallback_page=None,
        chunk_map=chunk_map,
        field_page=1,
    )
    assert anchor is not None
    assert anchor.page == 5


def test_no_chunk_map_uses_field_page():
    ex = _Dummy()
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        chunk_map=None,
        field_page=7,
    )
    assert anchor is not None
    assert anchor.page == 7


def test_no_element_spans_uses_field_page():
    ex = _Dummy()
    chunk_map = [(0, 47, {"metadata": {}}, None)]
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        chunk_map=chunk_map,
        field_page=7,
    )
    assert anchor is not None
    assert anchor.page == 7
