"""Unit tests for citation_resolver (B2b)."""

from __future__ import annotations

import hashlib

import pytest

from core.anchors.models import CheckAnchorMethod
from engine.checks.citation_resolver import (
    _compute_content_hash,
    _exact_span,
    _fuzzy_span,
    _span_to_element_ids,
    resolve_quote_in_source,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _el(
    element_id: str,
    text: str,
    page: int = 1,
    seq: int = 0,
) -> dict:
    return {
        "element_id": element_id,
        "text": text,
        "page": page,
        "_seq": seq,
    }


def _source_from_elements(*elements: dict) -> str:
    """Воспроизвести логику materialize_text_from_element_ids."""
    sorted_els = sorted(elements, key=lambda e: int(e.get("_seq", 0)))
    pieces: list[str] = []
    last_page = None
    for el in sorted_els:
        text = (el.get("text") or "").strip()
        if not text:
            continue
        page = el.get("page")
        if last_page is not None and page != last_page:
            pieces.append("")
        pieces.append(text)
        last_page = page if isinstance(page, int) else last_page
    return "\n\n".join(pieces).strip()


# ---------------------------------------------------------------------------
# resolve_quote_in_source — exact / fuzzy / fallback
# ---------------------------------------------------------------------------


def test_exact_span_single_element() -> None:
    source = "Стороны обязуются соблюдать конфиденциальность."
    quote = "соблюдать конфиденциальность"
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[],
        fallback_clause_uid="main_contract:5.1",
    )
    assert anchor.anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert anchor.anchor_confidence == 1.0
    assert anchor.anchor_validation_passed is True
    assert anchor.span_start is not None
    assert anchor.span_end is not None
    assert source[anchor.span_start : anchor.span_end] == quote
    assert anchor.clause_uid == "main_contract:5.1"
    assert anchor.source_content_hash is not None


def test_exact_span_with_normalization() -> None:
    source = "Стороны \u00abобязуются\u00bb соблюдать  конфиденциальность."
    quote = '"обязуются" соблюдать конфиденциальность'
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[],
    )
    assert anchor.anchor_method == CheckAnchorMethod.EXACT_SPAN
    # span в оригинале содержит кавычки-ёлочки
    assert "\u00ab" in source[anchor.span_start : anchor.span_end]


def test_exact_span_maps_to_layout_element() -> None:
    el1 = _el("ru:node:1:0001", "Заголовок", page=1, seq=0)
    el2 = _el("ru:node:1:0002", "Стороны обязуются соблюдать конфиденциальность.", page=1, seq=1)
    source = _source_from_elements(el1, el2)

    quote = "соблюдать конфиденциальность"
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[el1, el2],
    )
    assert anchor.anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert anchor.layout_element_ids == ["ru:node:1:0002"]


def test_exact_span_spans_multiple_elements() -> None:
    el1 = _el("ru:node:1:0001", "Стороны обязуются", page=1, seq=0)
    el2 = _el("ru:node:1:0002", "соблюдать конфиденциальность", page=1, seq=1)
    source = _source_from_elements(el1, el2)

    # quote пересекает границу элементов
    quote = "обязуются\n\nсоблюдать"
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[el1, el2],
    )
    assert anchor.anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert set(anchor.layout_element_ids) == {"ru:node:1:0001", "ru:node:1:0002"}


def test_exact_span_layout_offset_mismatch_returns_empty_element_ids() -> None:
    source = "Стороны обязуются соблюдать конфиденциальность."
    # layout_elements не соответствуют source
    wrong = [_el("ru:node:9:9999", "Другой текст, не совпадающий.", seq=0)]
    anchor = resolve_quote_in_source(
        quote="соблюдать конфиденциальность",
        source_text=source,
        layout_elements=wrong,
    )
    assert anchor.anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert anchor.layout_element_ids == []
    assert anchor.anchor_diagnostics.get("layout_offset_mismatch") is True


def test_fuzzy_span_high_ratio() -> None:
    source = "Стороны обязуются соблюдать полную конфиденциальность условий сделки."
    # немного другая формулировка — сработает fuzzy
    quote = "обязуются соблюдать конфиденциальность условий"
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[],
    )
    assert anchor.anchor_method in (
        CheckAnchorMethod.EXACT_SPAN,
        CheckAnchorMethod.FUZZY_SPAN,
    )
    # если fuzzy — должен быть помечен compactness + window_multiplier
    # (B6.1/R13: вместо LCS-ratio используем минимальное окно с полным
    # покрытием токенов цитаты; compactness = quote_len / span_len).
    if anchor.anchor_method == CheckAnchorMethod.FUZZY_SPAN:
        assert "compactness" in anchor.anchor_diagnostics
        assert "window_multiplier" in anchor.anchor_diagnostics
        assert 0.0 < anchor.anchor_diagnostics["compactness"] <= 1.0
        assert 1.0 <= anchor.anchor_diagnostics["window_multiplier"] <= 2.5


def test_fuzzy_span_below_threshold_falls_back() -> None:
    source = "Совершенно другой текст о поставке товаров и услуг."
    quote = "соблюдать конфиденциальность"
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[],
        fallback_clause_uid="main_contract:5.1",
    )
    assert anchor.anchor_method == CheckAnchorMethod.CLAUSE_ONLY
    assert anchor.anchor_confidence == 0.5


def test_fuzzy_span_handles_edge_punctuation() -> None:
    # B6.1/R13 edge-punct: в source у слова есть запятая на краю
    # ("Стороны,"), в quote — нет ("Стороны"). Fuzzy должен найти окно.
    source = (
        "При наступлении смены контроля вся сумма задолженности Стороны, "
        "в отношении которой произошла смена контроля, подлежит досрочному "
        "погашению на условиях, указанных в настоящем пункте."
    )
    quote = (
        "При наступлении смены контроля вся сумма задолженности Стороны "
        "подлежит досрочному погашению"
    )
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[],
    )
    assert anchor.anchor_method == CheckAnchorMethod.FUZZY_SPAN
    assert anchor.anchor_diagnostics["compactness"] < 1.0
    assert 1.0 <= anchor.anchor_diagnostics["window_multiplier"] <= 2.5


def test_fuzzy_span_rejects_hallucination_after_normalization() -> None:
    # Токенов достаточно (>= 3), но ни один значимый токен не найден в source.
    source = "Совершенно другой текст о поставке товаров и услуг."
    quote = "обязуются соблюдать конфиденциальность"
    anchor = resolve_quote_in_source(
        quote=quote,
        source_text=source,
        layout_elements=[],
        fallback_clause_uid="main_contract:5.1",
    )
    assert anchor.anchor_method == CheckAnchorMethod.CLAUSE_ONLY


def test_clause_only_when_quote_empty_and_clause_provided() -> None:
    anchor = resolve_quote_in_source(
        quote=None,
        source_text="Some text",
        layout_elements=[],
        fallback_clause_uid="main_contract:1.1",
    )
    assert anchor.anchor_method == CheckAnchorMethod.CLAUSE_ONLY
    assert anchor.clause_uid == "main_contract:1.1"
    assert anchor.anchor_confidence == 0.5
    assert anchor.anchor_validation_passed is False


def test_page_only_when_no_quote_no_clause() -> None:
    anchor = resolve_quote_in_source(
        quote=None,
        source_text="Some text",
        layout_elements=[],
        fallback_page=4,
    )
    assert anchor.anchor_method == CheckAnchorMethod.PAGE_ONLY
    assert anchor.page == 4
    assert anchor.anchor_confidence == 0.3


def test_none_when_nothing_available() -> None:
    anchor = resolve_quote_in_source(
        quote=None,
        source_text="",
        layout_elements=[],
    )
    assert anchor.anchor_method == CheckAnchorMethod.NONE
    assert anchor.anchor_confidence == 0.0
    assert anchor.anchor_validation_passed is False


def test_quote_too_short_falls_back() -> None:
    anchor = resolve_quote_in_source(
        quote="ab",
        source_text="abc",
        layout_elements=[],
        fallback_clause_uid="main_contract:1.1",
    )
    assert anchor.anchor_method == CheckAnchorMethod.CLAUSE_ONLY


# ---------------------------------------------------------------------------
# source_content_hash
# ---------------------------------------------------------------------------


def test_source_content_hash_computed_automatically() -> None:
    source = "Стороны обязуются соблюдать конфиденциальность."
    anchor = resolve_quote_in_source(
        quote="соблюдать конфиденциальность",
        source_text=source,
        layout_elements=[],
    )
    expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert anchor.source_content_hash == expected


def test_source_content_hash_from_caller_not_recomputed() -> None:
    passed = "a" * 64
    anchor = resolve_quote_in_source(
        quote="соблюдать конфиденциальность",
        source_text="Стороны обязуются соблюдать конфиденциальность.",
        layout_elements=[],
        source_content_hash=passed,
    )
    assert anchor.source_content_hash == passed


def test_source_content_hash_none_for_empty_source() -> None:
    anchor = resolve_quote_in_source(
        quote=None,
        source_text="",
        layout_elements=[],
    )
    assert anchor.source_content_hash is None


# ---------------------------------------------------------------------------
# Глубокие unit-тесты внутренних helpers
# ---------------------------------------------------------------------------


def test_compute_content_hash_deterministic() -> None:
    a = _compute_content_hash("привет")
    b = _compute_content_hash("привет")
    assert a == b
    assert len(a) == 64
    assert a == a.lower()


def test_exact_span_returns_none_when_not_found() -> None:
    assert _exact_span("соблюдать конфиденциальность", "другой текст") is None


def test_exact_span_returns_none_for_short_quote() -> None:
    assert _exact_span("ab", "abc def ghi") is None


def test_fuzzy_span_returns_none_when_too_few_tokens() -> None:
    assert _fuzzy_span("ab cd", "ab cd ef gh") is None


def test_span_to_element_ids_empty_input() -> None:
    assert _span_to_element_ids(0, 10, []) == []


def test_span_to_element_ids_partial_overlap() -> None:
    offsets = [
        ("el1", 0, 10),
        ("el2", 12, 20),
        ("el3", 22, 30),
    ]
    # span [8, 15) пересекается с el1 (8<10) и el2 (12<15)
    assert _span_to_element_ids(8, 15, offsets) == ["el1", "el2"]


def test_span_to_element_ids_no_overlap() -> None:
    offsets = [("el1", 0, 5), ("el2", 10, 15)]
    assert _span_to_element_ids(5, 10, offsets) == []
