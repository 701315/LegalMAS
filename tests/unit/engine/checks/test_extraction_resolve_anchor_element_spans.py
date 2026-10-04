"""Юнит-тест: _resolve_field_anchor использует element_spans для точной page.

ВАЖНО: resolve_quote_in_source имеет минимальную длину quote
(см. citation_resolver._MIN_QUOTE_LEN). Короткие цитаты ("ДОГОВОР")
не матчатся, anchor возвращается NONE, и _resolve_field_anchor = None.
Поэтому все тесты используют quote длиной >= 15 символов.
"""
from engine.checks.extraction import ExtractionExecutor


LONG_QUOTE = "Между ООО Ромашка"
LONG_SOURCE = "ДОГОВОР КРАТКОСРОЧНОЙ АРЕНДЫ\n\nМежду ООО Ромашка"


class _Dummy(ExtractionExecutor):
    """ExtractionExecutor без полного __init__ - метод _resolve_field_anchor
    не использует self."""
    def __init__(self):  # noqa
        pass


def test_element_spans_overrides_field_page_for_multi_page_chunk():
    """LLM вернула field_page=1 (start_page чанка), но цитата на стр. 2."""
    ex = _Dummy()
    element_spans = [
        ["ru:node:1:0000", 1, 0, 28],
        ["ru:node:2:0000", 2, 30, 47],
    ]
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        element_spans=element_spans,
        field_page=1,
    )
    assert anchor is not None
    assert anchor.page == 2


def test_element_spans_exact_single_element_page():
    """Одна страница, один элемент - обычный случай."""
    ex = _Dummy()
    element_spans = [["el_1", 5, 30, 47]]
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        element_spans=element_spans,
        field_page=None,
    )
    assert anchor is not None
    assert anchor.page == 5


def test_element_spans_none_uses_field_page():
    """Backward compatibility: без element_spans работаем как раньше."""
    ex = _Dummy()
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        element_spans=None,
        field_page=7,
    )
    assert anchor is not None
    assert anchor.page == 7


def test_element_spans_empty_list_falls_back_to_field_page():
    """Пустой список - тоже fallback (не ошибка)."""
    ex = _Dummy()
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        element_spans=[],
        field_page=7,
    )
    assert anchor is not None
    assert anchor.page == 7


def test_element_spans_malformed_entries_ignored():
    """Битые записи в element_spans не ломают резолв."""
    ex = _Dummy()
    element_spans = [
        "not-a-list",
        ["el_1"],  # слишком короткий
        ["el_2", "not-int", 30, 47],  # page - не int
        ["el_3", 3, 30, 47],  # валидный
    ]
    anchor = ex._resolve_field_anchor(
        quote=LONG_QUOTE,
        source_text=LONG_SOURCE,
        fallback_clause_uid=None,
        fallback_page=None,
        element_spans=element_spans,
        field_page=1,
    )
    assert anchor is not None
    assert anchor.page == 3  # валидный элемент победил
