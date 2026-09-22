"""Unit tests for citation_normalization (B2a)."""

from __future__ import annotations

import pytest

from engine.checks.citation_normalization import (
    _normalize_char,
    normalize_text,
    normalize_with_index_map,
)


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


def test_normalize_text_no_changes() -> None:
    assert normalize_text("hello world") == "hello world"


def test_normalize_text_yo_to_ye() -> None:
    assert normalize_text("ёж и Ёж") == "еж и Еж"


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("a\u00a0b", "a b"),      # NBSP
        ("a\u202fb", "a b"),      # narrow NBSP
        ("a\u2009b", "a b"),      # thin space
        ("a\u200ab", "a b"),      # hair space
    ],
)
def test_normalize_text_nbsp_to_space(input_: str, expected: str) -> None:
    assert normalize_text(input_) == expected


def test_normalize_text_quotes() -> None:
    assert normalize_text("«Привет»") == '"Привет"'
    assert normalize_text("„Hallo“") == '"Hallo"'
    assert normalize_text("‘one’") == "'one'"
    assert normalize_text("`code`") == "'code'"


def test_normalize_text_dashes() -> None:
    assert normalize_text("a—b–c−d") == "a-b-c-d"
    assert normalize_text("a‐b‑c‒d") == "a-b-c-d"


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("a    b\n\nc\t\td") == "a b c d"


def test_normalize_text_strips() -> None:
    assert normalize_text("   hello   ") == "hello"


def test_normalize_text_empty() -> None:
    assert normalize_text("") == ""
    assert normalize_text("   \n\t  ") == ""


def test_normalize_text_mixed() -> None:
    text = "  «Стороны»  \u00a0 обязуются — да.\n\nП. 1.2  "
    expected = '"Стороны" обязуются - да. П. 1.2'
    assert normalize_text(text) == expected


# ---------------------------------------------------------------------------
# normalize_with_index_map
# ---------------------------------------------------------------------------


def test_index_map_simple() -> None:
    norm, idx = normalize_with_index_map("hello")
    assert norm == "hello"
    assert idx == [0, 1, 2, 3, 4]


def test_index_map_yo_to_ye_identity() -> None:
    """Замена ё→е — 1:1, карта тривиальна."""
    norm, idx = normalize_with_index_map("ёж")
    assert norm == "еж"
    assert idx == [0, 1]


def test_index_map_collapses_spaces() -> None:
    # "a  b": a=0, space=1, space=2, b=3
    norm, idx = normalize_with_index_map("a  b")
    assert norm == "a b"
    assert idx == [0, 1, 3]  # 'b' в оригинале стоит на позиции 3


def test_index_map_strips_leading() -> None:
    norm, idx = normalize_with_index_map("   hi")
    assert norm == "hi"
    assert idx == [3, 4]


def test_index_map_strips_trailing() -> None:
    norm, idx = normalize_with_index_map("hi   ")
    assert norm == "hi"
    assert idx == [0, 1]


def test_index_map_empty() -> None:
    norm, idx = normalize_with_index_map("")
    assert norm == ""
    assert idx == []


def test_index_map_all_spaces() -> None:
    norm, idx = normalize_with_index_map("   \n\t  ")
    assert norm == ""
    assert idx == []


def test_index_map_quote_to_ascii_identity() -> None:
    text = "«x»"
    norm, idx = normalize_with_index_map(text)
    assert norm == '"x"'
    assert idx == [0, 1, 2]


@pytest.mark.parametrize(
    "text",
    [
        "abc",
        "a  b   c",
        "   abc   ",
        "ёж\n\nи  ещё",
        "«цитата»",
        "",
        " \n\t ",
        "a—b",
        "Привет,  мир!\n\nКак дела?",
    ],
)
def test_index_map_length_invariant(text: str) -> None:
    """Гарантия: len(norm) == len(idx) для любого входа."""
    norm, idx = normalize_with_index_map(text)
    assert len(norm) == len(idx)


@pytest.mark.parametrize(
    "text",
    [
        "abc",
        "a  b",
        "   abc   ",
        "ёж",
        "«x»",
        "",
        "a—b",
    ],
)
def test_index_map_equivalence_with_normalize_text(text: str) -> None:
    """normalize_text(s) == normalize_with_index_map(s)[0]."""
    assert normalize_text(text) == normalize_with_index_map(text)[0]


@pytest.mark.parametrize(
    "text",
    [
        "а  б  в",
        "  «Цитата» ",
        "ёж\n\nи ещё",
    ],
)
def test_index_map_reverse_mapping_correct(text: str) -> None:
    """
    Для каждой позиции i: normalized[i] == _normalize_char(text[idx[i]]).
    Это базовая гарантия корректности карты.
    """
    norm, idx = normalize_with_index_map(text)
    for i, ch in enumerate(norm):
        assert _normalize_char(text[idx[i]]) == ch, (
            f"mismatch at i={i} for text={text!r}"
        )
