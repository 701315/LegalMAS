# tests/unit/core/anchors/test_clause_ref_parser.py
"""Unit tests for the universal clause reference parser (B7.9.2)."""

from __future__ import annotations

import pytest

from core.anchors.clause_ref_parser import (
    ClauseMarker,
    ClauseRefParseResult,
    MarkerKind,
    extract_clause_marker_values,
    extract_page_hint,
    parse_clause_ref,
)


class TestNumericMarkers:
    def test_simple_numeric(self):
        r = parse_clause_ref("п. 2")
        assert [m.value for m in r.markers] == ["2"]
        assert r.markers[0].kind == MarkerKind.NUMERIC
        assert r.page_hint is None

    def test_dotted_numeric(self):
        r = parse_clause_ref("п. 2.2")
        assert [m.value for m in r.markers] == ["2.2"]
        assert r.markers[0].kind == MarkerKind.NUMERIC

    def test_deeply_dotted_numeric(self):
        r = parse_clause_ref("п. 3.2.1.4")
        assert [m.value for m in r.markers] == ["3.2.1.4"]

    def test_bare_numeric(self):
        r = parse_clause_ref("2.2")
        assert [m.value for m in r.markers] == ["2.2"]
        assert r.markers[0].kind == MarkerKind.NUMERIC

    def test_section_prefix(self):
        r = parse_clause_ref("Section 12.1")
        assert [m.value for m in r.markers] == ["12.1"]

    def test_article_prefix_ru(self):
        r = parse_clause_ref("статья 5")
        assert [m.value for m in r.markers] == ["5"]

    def test_paragraph_symbol(self):
        r = parse_clause_ref("§ 4.2")
        assert [m.value for m in r.markers] == ["4.2"]

    def test_cl_prefix(self):
        r = parse_clause_ref("cl. 3.1")
        assert [m.value for m in r.markers] == ["3.1"]

    def test_uppercase_cyrillic_prefix(self):
        r = parse_clause_ref("П. 2.2")
        assert [m.value for m in r.markers] == ["2.2"]


class TestAlphaMarkers:
    def test_latin_single_letter(self):
        r = parse_clause_ref("п. S")
        assert [m.value for m in r.markers] == ["S"]
        assert r.markers[0].kind == MarkerKind.LATIN

    def test_latin_bare_single_letter(self):
        r = parse_clause_ref("S")
        assert [m.value for m in r.markers] == ["S"]
        assert r.markers[0].kind == MarkerKind.LATIN

    def test_cyrillic_single_letter(self):
        r = parse_clause_ref("п. А")
        assert [m.value for m in r.markers] == ["А"]
        assert r.markers[0].kind == MarkerKind.CYRILLIC

    def test_cyrillic_multi_letter(self):
        r = parse_clause_ref("п. АБВ")
        assert [m.value for m in r.markers] == ["АБВ"]
        assert r.markers[0].kind == MarkerKind.CYRILLIC

    def test_synthetic_marker_with_hyphen(self):
        r = parse_clause_ref("п. S-1")
        assert [m.value for m in r.markers] == ["S-1"]
        assert r.markers[0].kind == MarkerKind.MIXED

    def test_lowercase_letter_is_not_a_marker(self):
        r = parse_clause_ref("п. s")
        assert r.markers == ()


class TestMixedMarkers:
    def test_numeric_with_latin_suffix(self):
        r = parse_clause_ref("п. 2a")
        assert [m.value for m in r.markers] == ["2a"]
        assert r.markers[0].kind == MarkerKind.MIXED

    def test_dotted_numeric_with_suffix(self):
        r = parse_clause_ref("п. 2.2a")
        assert [m.value for m in r.markers] == ["2.2a"]

    def test_numeric_with_cyrillic_suffix(self):
        r = parse_clause_ref("п. 2.2б")
        assert [m.value for m in r.markers] == ["2.2б"]


class TestAppendixMarkers:
    def test_russian_prilozhenie(self):
        r = parse_clause_ref("Приложение А")
        assert [m.value for m in r.markers] == ["А"]
        assert r.markers[0].kind == MarkerKind.APPENDIX

    def test_english_appendix(self):
        r = parse_clause_ref("Appendix B")
        assert [m.value for m in r.markers] == ["B"]
        assert r.markers[0].kind == MarkerKind.APPENDIX

    def test_schedule(self):
        r = parse_clause_ref("Schedule 1")
        assert [m.value for m in r.markers] == ["1"]
        assert r.markers[0].kind == MarkerKind.APPENDIX

    def test_prilozhenie_abbreviation(self):
        r = parse_clause_ref("прил. В")
        assert [m.value for m in r.markers] == ["В"]
        assert r.markers[0].kind == MarkerKind.APPENDIX


class TestPageHints:
    def test_page_only_ru(self):
        r = parse_clause_ref("стр. 5")
        assert r.markers == ()
        assert r.page_hint == 5

    def test_page_only_en(self):
        r = parse_clause_ref("page 12")
        assert r.markers == ()
        assert r.page_hint == 12

    def test_clause_and_page(self):
        r = parse_clause_ref("п. 2.2, стр. 3")
        assert [m.value for m in r.markers] == ["2.2"]
        assert r.page_hint == 3

    def test_page_before_clause(self):
        r = parse_clause_ref("стр. 5, п. 2.2")
        assert [m.value for m in r.markers] == ["2.2"]
        assert r.page_hint == 5

    def test_short_page_prefix_p(self):
        r = parse_clause_ref("p. 7")
        assert r.markers == ()
        assert r.page_hint == 7

    def test_short_page_prefix_s(self):
        r = parse_clause_ref("с. 5")
        assert r.markers == ()
        assert r.page_hint == 5


class TestNDARegression:
    def test_preamble_clause_ref(self):
        r = parse_clause_ref(
            "пункт S, СОГЛАШЕНИЕ О КОНФИДЕНЦИАЛЬНОСТИ, стр. 1"
        )
        assert [m.value for m in r.markers] == ["S"]
        assert r.markers[0].kind == MarkerKind.LATIN
        assert r.page_hint == 1

    def test_preamble_clause_ref_does_not_yield_page_as_marker(self):
        r = parse_clause_ref(
            "пункт S, СОГЛАШЕНИЕ О КОНФИДЕНЦИАЛЬНОСТИ, стр. 1"
        )
        assert "1" not in [m.value for m in r.markers]

    def test_obshchie_usloviya(self):
        r = parse_clause_ref("ОБЩИЕ УСЛОВИЯ, п.2.2, стр. 2")
        assert [m.value for m in r.markers] == ["2.2"]
        assert r.page_hint == 2


class TestNegativeCases:
    def test_all_caps_title_without_prefix(self):
        r = parse_clause_ref("СОГЛАШЕНИЕ О КОНФИДЕНЦИАЛЬНОСТИ")
        assert r.markers == ()
        assert r.page_hint is None

    def test_long_word_not_marker(self):
        r = parse_clause_ref("предисловие X")
        assert r.markers == ()

    def test_empty_string(self):
        r = parse_clause_ref("")
        assert r.markers == ()
        assert r.page_hint is None

    def test_none_input(self):
        r = parse_clause_ref(None)
        assert r.markers == ()
        assert r.page_hint is None

    def test_whitespace_only(self):
        r = parse_clause_ref("   \t\n")
        assert r.markers == ()

    def test_multiple_free_text_words(self):
        r = parse_clause_ref("СОГЛАШЕНИЕ О КОНФИДЕНЦИАЛЬНОСТИ между сторонами")
        assert r.markers == ()

    def test_prefix_without_marker(self):
        r = parse_clause_ref("п.")
        assert r.markers == ()


class TestMultiMarker:
    def test_two_numeric_markers(self):
        r = parse_clause_ref("п. 7.1.1, п. 7.1.2")
        assert [m.value for m in r.markers] == ["7.1.1", "7.1.2"]

    def test_two_alpha_markers(self):
        r = parse_clause_ref("Appendix A, Appendix B")
        assert [m.value for m in r.markers] == ["A", "B"]

    def test_deduplication(self):
        r = parse_clause_ref("п. 2.2 и п. 2.2")
        assert [m.value for m in r.markers] == ["2.2"]


class TestPosition:

    def test_comma_separated_after_one_prefix(self):
        r = parse_clause_ref("п. 7.1.1, 7.1.2")
        assert [m.value for m in r.markers] == ["7.1.1", "7.1.2"]

    def test_comma_separated_three_markers(self):
        r = parse_clause_ref("п. 7.1.1, 7.1.2, 7.1.3")
        assert [m.value for m in r.markers] == ["7.1.1", "7.1.2", "7.1.3"]

    def test_semicolon_separated(self):
        r = parse_clause_ref("cl. 3.1; 3.2")
        assert [m.value for m in r.markers] == ["3.1", "3.2"]

    def test_page_stops_marker_list(self):
        r = parse_clause_ref("п. 7.1.1, стр. 3")
        assert [m.value for m in r.markers] == ["7.1.1"]
        assert r.page_hint == 3

    def test_appendix_list(self):
        r = parse_clause_ref("Appendix A, B")
        assert [m.value for m in r.markers] == ["A", "B"]

    def test_appendix_list_both_appendix_kind(self):
        r = parse_clause_ref("Appendix A, B")
        assert all(m.kind == MarkerKind.APPENDIX for m in r.markers)
    def test_position_is_offset_in_original_string(self):
        r = parse_clause_ref("п. 2.2, стр. 3")
        assert r.markers[0].position == 3

    def test_markers_sorted_by_position(self):
        r = parse_clause_ref("Appendix B, п. 2.2")
        assert [m.value for m in r.markers] == ["B", "2.2"]


class TestConvenienceHelpers:
    def test_extract_clause_marker_values(self):
        assert extract_clause_marker_values("п. 2.2, стр. 3") == ["2.2"]

    def test_extract_clause_marker_values_empty(self):
        assert extract_clause_marker_values("") == []

    def test_extract_page_hint(self):
        assert extract_page_hint("п. 2.2, стр. 3") == 3

    def test_extract_page_hint_none(self):
        assert extract_page_hint("п. 2.2") is None


class TestContract:
    def test_result_is_frozen(self):
        r = parse_clause_ref("п. 2.2")
        with pytest.raises(Exception):
            r.page_hint = 99  # type: ignore[misc]

    def test_marker_is_frozen(self):
        r = parse_clause_ref("п. 2.2")
        with pytest.raises(Exception):
            r.markers[0].value = "X"  # type: ignore[misc]

    def test_markers_is_tuple(self):
        r = parse_clause_ref("п. 2.2")
        assert isinstance(r.markers, tuple)

    def test_result_type(self):
        r = parse_clause_ref("п. 2.2")
        assert isinstance(r, ClauseRefParseResult)

    def test_marker_type(self):
        r = parse_clause_ref("п. 2.2")
        assert isinstance(r.markers[0], ClauseMarker)
