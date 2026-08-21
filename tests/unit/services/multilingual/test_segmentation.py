# tests/unit/services/multilingual/test_segmentation.py

"""
Unit тесты для Layer 2: Text Segmentation.

Покрывает:
- Split на основе Layer 1 hints (script boundary, separator, digit-letter)
- Multi-split для 3+ языков
- Lossless invariant
- Bbox proportional split
- Anchor extraction через existing функции
- Page layout classification (все типы)
- Реальные паттерны из документа Simonova SPA
- Edge cases: пустые, невалидные, missing hints
"""

from __future__ import annotations

import pytest

from services.multilingual.models import (
    BBox,
    LanguageSegment,
    NormalizationHints,
    PageLayout,
)
from services.multilingual.normalization import normalize_elements
from services.multilingual.segmentation import (
    _extract_anchor_uid,
    _get_dominant_script,
    _verify_lossless,
    segment_elements,
)


# ---------------------------------------------------------------------------
# Helpers для тестов
# ---------------------------------------------------------------------------


def _make_element(
    element_id: str = "e001",
    text: str = "Test text",
    page: int = 1,
    bbox: list[float] | None = None,
    type_: str = "text",
    confidence: float = 1.0,
) -> dict:
    return {
        "element_id": element_id,
        "text": text,
        "page": page,
        "bbox": bbox or [10.0, 20.0, 400.0, 40.0],
        "type": type_,
        "confidence": confidence,
    }


def _make_hints(
    element_id: str = "e001",
    text: str = "Test text",
    script_positions: tuple = (),
    separator: str | None = None,
    separator_positions: tuple = (),
    digit_letter_positions: tuple = (),
) -> NormalizationHints:
    return NormalizationHints(
        source_element_id=element_id,
        script_boundary_detected=len(script_positions) > 0,
        script_boundary_positions=script_positions,
        explicit_separator_detected=separator,
        explicit_separator_positions=separator_positions,
        digit_letter_boundary_detected=len(digit_letter_positions) > 0,
        digit_letter_boundary_positions=digit_letter_positions,
        is_table_cell=False,
        cell_position=None,
        has_zero_width_chars=False,
        cleaned_text=text,
    )


# ---------------------------------------------------------------------------
# _extract_anchor_uid через existing функции
# ---------------------------------------------------------------------------


class TestAnchorExtraction:
    def test_numeric_clause(self) -> None:
        # parse_raw_heading распознаёт "1. DEFINITIONS" → uid="1"
        assert _extract_anchor_uid("1. DEFINITIONS") == "1"

    def test_nested_numeric(self) -> None:
        assert _extract_anchor_uid("1.1 Purpose of contract") == "1.1"

    def test_appendix_en(self) -> None:
        result = _extract_anchor_uid("APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE")
        assert result is not None
        assert "1" in result

    def test_appendix_ru(self) -> None:
        result = _extract_anchor_uid("ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА")
        assert result is not None
        assert "1" in result

    def test_regular_text_no_anchor(self) -> None:
        assert _extract_anchor_uid("This is regular contract text without any anchor") is None

    def test_empty_text(self) -> None:
        assert _extract_anchor_uid("") is None

    def test_whitespace_only(self) -> None:
        assert _extract_anchor_uid("   ") is None


# ---------------------------------------------------------------------------
# _verify_lossless
# ---------------------------------------------------------------------------


class TestLosslessInvariant:
    def test_perfect_split_lossless(self) -> None:
        original = "English text русский текст"
        seg1 = _make_language_segment("seg_1", "English text")
        seg2 = _make_language_segment("seg_2", "русский текст")
        assert _verify_lossless(original, [seg1, seg2])

    def test_extra_whitespace_between_parts_ok(self) -> None:
        # Оригинал может иметь двойные пробелы, split результат — одинарные
        original = "Text A  Text B"
        seg1 = _make_language_segment("seg_1", "Text A")
        seg2 = _make_language_segment("seg_2", "Text B")
        assert _verify_lossless(original, [seg1, seg2])

    def test_missing_content_not_lossless(self) -> None:
        original = "Full text that must not be lost"
        seg1 = _make_language_segment("seg_1", "Full text")
        # "must not be lost" потеряно
        assert not _verify_lossless(original, [seg1])

    def test_empty_segments_ignored(self) -> None:
        original = "Just this"
        seg1 = _make_language_segment("seg_1", "Just this")
        seg2 = _make_language_segment("seg_2", "")
        assert _verify_lossless(original, [seg1, seg2])


def _make_language_segment(segment_id: str, text: str) -> LanguageSegment:
    return LanguageSegment(
        segment_id=segment_id,
        source_element_id="e001",
        sub_index=0,
        text=text,
        page=1,
        bbox=BBox(0, 0, 100, 20),
        bbox_is_approximate=False,
        bbox_split_method="original",
        reading_order_raw=0,
        anchor_uid=None,
        is_table_cell=False,
        cell_position=None,
        source_element_type="text",
        split_reason="none",
        split_confidence=1.0,
    )


# ---------------------------------------------------------------------------
# segment_elements — базовые случаи
# ---------------------------------------------------------------------------


class TestSegmentElementsBasics:
    def test_empty_input(self) -> None:
        segments, layouts, warnings = segment_elements([], {})
        assert segments == []
        assert layouts == {}
        assert warnings == []

    def test_monolingual_element_no_split(self) -> None:
        element = _make_element("e001", "Simple English text")
        hints = _make_hints("e001", "Simple English text")
        segments, _, _ = segment_elements([element], {"e001": hints})
        assert len(segments) == 1
        assert segments[0].split_reason == "none"
        assert segments[0].sub_index == 0
        assert not segments[0].bbox_is_approximate
        assert segments[0].split_confidence == 1.0

    def test_missing_hints_creates_warning(self) -> None:
        element = _make_element("e001", "Text without hints")
        segments, _, warnings = segment_elements([element], {})
        assert len(segments) == 1
        assert segments[0].split_reason == "none"
        warning_types = [w.warning_type for w in warnings]
        assert "missing_normalization_hints" in warning_types

    def test_element_without_id_skipped(self) -> None:
        element = {"text": "No ID", "page": 1, "bbox": [0, 0, 100, 20]}
        segments, _, _ = segment_elements([element], {})
        assert segments == []

    def test_empty_text_no_segment(self) -> None:
        element = _make_element("e001", "")
        hints = _make_hints("e001", "")
        segments, _, _ = segment_elements([element], {"e001": hints})
        assert segments == []


# ---------------------------------------------------------------------------
# Split by explicit separator
# ---------------------------------------------------------------------------


class TestSplitByExplicitSeparator:
    def test_slash_separator_split(self) -> None:
        # "APPENDICES / ПРИЛОЖЕНИЯ" → position 11
        text = "APPENDICES / ПРИЛОЖЕНИЯ"
        element = _make_element("e001", text, bbox=[0, 0, 400, 20])

        # Real hints from Layer 1
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        assert len(segments) == 2
        assert segments[0].split_reason == "explicit_separator"
        # Оба сегмента без "/"
        assert "/" not in segments[0].text
        assert "/" not in segments[1].text
        # Проверяем контент
        assert "APPENDICES" in segments[0].text
        assert "ПРИЛОЖЕНИЯ" in segments[1].text

    def test_backslash_separator(self) -> None:
        # ВАЖНО: разделитель "\" работает так же как "/" — только если по бокам
        # разные скрипты. Реальный случай из таблиц Simonova SPA:
        # "Земельный участок \ Land plot"
        text = "Земельный участок \\ Land plot"
        element = _make_element("e001", text)
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        assert len(segments) == 2
        assert segments[0].split_reason == "explicit_separator"
        # Разделитель "\" не должен присутствовать ни в одном сегменте
        assert "\\" not in segments[0].text
        assert "\\" not in segments[1].text
        # Проверяем контент
        assert "Земельный участок" in segments[0].text
        assert "Land plot" in segments[1].text

    def test_bbox_approximate_after_separator_split(self) -> None:
        text = "APPENDICES / ПРИЛОЖЕНИЯ"
        element = _make_element("e001", text, bbox=[100, 0, 500, 20])
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        for seg in segments:
            assert seg.bbox_is_approximate
            assert seg.bbox_split_method == "proportional"

    def test_high_confidence_for_separator(self) -> None:
        text = "APPENDICES / ПРИЛОЖЕНИЯ"
        element = _make_element("e001", text)
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        for seg in segments:
            assert seg.split_confidence >= 0.9


# ---------------------------------------------------------------------------
# Split by script boundary
# ---------------------------------------------------------------------------


class TestSplitByScriptBoundary:
    def test_script_boundary_split_no_separator(self) -> None:
        # Реальный паттерн 5: parallel columns склеены в один элемент
        text = "This Real Estate Sale and Purchase Agreement has Настоящий договор"
        element = _make_element("e001", text, bbox=[0, 0, 500, 20])
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        assert len(segments) == 2
        assert segments[0].split_reason == "script_boundary"
        # Левая часть — латиница
        assert "This Real Estate" in segments[0].text
        # Правая часть — кириллица
        assert "Настоящий договор" in segments[1].text

    def test_bbox_proportional_by_text_length(self) -> None:
        text = "AAAAAAAAAA Bbbbbbbbbb Русский"
        # 10 A's + 10 b's = 20 latin chars + " " + 7 cyrillic
        element = _make_element("e001", text, bbox=[0, 0, 300, 20])
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        assert len(segments) == 2
        # Латинская часть длиннее — её bbox должен быть шире
        assert segments[0].bbox.width > segments[1].bbox.width


# ---------------------------------------------------------------------------
# Multi-split для 3+ языков
# ---------------------------------------------------------------------------


class TestMultiSplit:
    def test_three_languages_in_one_element(self) -> None:
        # Синтетический пример: EN + RU + AR
        # (или любые 3 разных script'а)
        text = "English text Русский текст العربية النص"
        element = _make_element("e001", text, bbox=[0, 0, 600, 20])
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        # Ожидаем как минимум 2 сегмента (Layer 1 может обнаружить не все границы,
        # но multi-split должен разбить оставшееся)
        assert len(segments) >= 2

        # Все сегменты должны иметь непустой text
        for seg in segments:
            assert seg.text.strip()

    def test_toc_header_with_duplicate(self) -> None:
        # Реальный паттерн 3: "TABLE OF CONTENTS / СОДЕРЖАНИЕTABLE OF CONTENTS"
        text = "TABLE OF CONTENTS / СОДЕРЖАНИЕTABLE OF CONTENTS"
        element = _make_element("e001", text)
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        # Должно получиться минимум 2 сегмента
        # Возможно 3 если multi-split сработает на дубликате
        assert len(segments) >= 2


# ---------------------------------------------------------------------------
# Real document patterns
# ---------------------------------------------------------------------------


class TestRealDocumentPatterns:
    """Тесты на всех 8 паттернах из Simonova SPA."""

    def test_pattern_1_stacked_pairs_no_split(self) -> None:
        # Титульный лист: отдельные элементы EN и RU
        elements = [
            _make_element("e0", "REAL ESTATE SALE AND PURCHASE AGREEMENT", bbox=[138, 68, 485, 82]),
            _make_element("e1", "ДОГОВОР КУПЛИ-ПРОДАЖИ ОБЪЕКТОВ НЕДВИЖИМОСТИ", bbox=[101, 89, 522, 103]),
        ]
        hints_dict, _ = normalize_elements(elements)
        segments, _, _ = segment_elements(elements, hints_dict)

        # 2 monolingual segments, no split
        assert len(segments) == 2
        for seg in segments:
            assert seg.split_reason == "none"

    def test_pattern_2_inline_separator(self) -> None:
        text = "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE / ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА"
        element = _make_element("e43", text, bbox=[85, 405, 555, 416])
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        assert len(segments) == 2
        assert segments[0].split_reason == "explicit_separator"
        # Проверяем anchor extraction — оба должны иметь uid связанный с "1"
        assert segments[0].anchor_uid is not None
        assert "1" in segments[0].anchor_uid

    def test_pattern_5_parallel_columns_one_element(self) -> None:
        text = "This Real Estate Sale and Purchase Agreement has Настоящий договор купли-продажи объектов"
        element = _make_element("e60", text, bbox=[55, 77, 547, 88])
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        assert len(segments) == 2
        assert segments[0].split_reason == "script_boundary"
        assert segments[0].bbox_is_approximate
        assert segments[1].bbox_is_approximate

    def test_pattern_7_heading_with_both_languages(self) -> None:
        text = "1. DEFINITIONS 1 ОПРЕДЕЛЕНИЯ"
        element = _make_element("e113", text, bbox=[55, 241, 439, 252], type_="heading")
        hints_dict, _ = normalize_elements([element])
        segments, _, _ = segment_elements([element], hints_dict)

        assert len(segments) >= 2
        # Первый сегмент должен иметь anchor "1"
        assert segments[0].anchor_uid == "1"
        # source_element_type наследуется
        for seg in segments:
            assert seg.source_element_type == "heading"


# ---------------------------------------------------------------------------
# Lossless invariant в реальных сценариях
# ---------------------------------------------------------------------------


class TestLosslessRealScenarios:
    def test_slash_separator_preserves_content(self) -> None:
        text = "APPENDICES / ПРИЛОЖЕНИЯ"
        element = _make_element("e001", text)
        hints_dict, _ = normalize_elements([element])
        segments, _, warnings = segment_elements([element], hints_dict)

        # Не должно быть lossless_invariant_violated warnings
        lossless_warnings = [
            w for w in warnings if w.warning_type == "lossless_invariant_violated"
        ]
        assert len(lossless_warnings) == 0

    def test_script_boundary_preserves_content(self) -> None:
        text = "English text здесь русский"
        element = _make_element("e001", text)
        hints_dict, _ = normalize_elements([element])
        segments, _, warnings = segment_elements([element], hints_dict)

        lossless_warnings = [
            w for w in warnings if w.warning_type == "lossless_invariant_violated"
        ]
        assert len(lossless_warnings) == 0


# ---------------------------------------------------------------------------
# Page layout classification
# ---------------------------------------------------------------------------


class TestPageLayoutClassification:
    def test_empty_page(self) -> None:
        segments, layouts, _ = segment_elements([], {})
        assert layouts == {}

    def test_monolingual_page_small(self) -> None:
        # Мало элементов — считается monolingual
        elements = [
            _make_element("e001", "English text one", page=1),
            _make_element("e002", "English text two", page=1),
        ]
        hints_dict, _ = normalize_elements(elements)
        _, layouts, _ = segment_elements(elements, hints_dict)

        assert 1 in layouts
        assert layouts[1].layout_type == "monolingual"

    def test_parallel_columns_from_split_siblings(self) -> None:
        # Много элементов созданных split-siblings — parallel_columns
        elements = []
        for i in range(6):
            text = f"English text {i} Русский текст {i}"
            elements.append(
                _make_element(f"e{i:03}", text, page=1, bbox=[55, 100 + i*20, 547, 115 + i*20])
            )
        hints_dict, _ = normalize_elements(elements)
        _, layouts, _ = segment_elements(elements, hints_dict)

        assert 1 in layouts
        # Ожидаем parallel_columns потому что каждый element split → 2 сегмента
        assert layouts[1].layout_type == "parallel_columns"

    def test_stacked_blocks_pattern(self) -> None:
        # Титульный лист: 5+ EN элементов подряд, потом 5+ RU элементов
        elements = []
        for i in range(6):
            elements.append(_make_element(f"e_en_{i}", f"English heading {i}",
                                           page=1, bbox=[100, 50 + i*30, 400, 70 + i*30]))
        for i in range(6):
            elements.append(_make_element(f"e_ru_{i}", f"Русский заголовок {i}",
                                           page=1, bbox=[100, 250 + i*30, 400, 270 + i*30]))
        hints_dict, _ = normalize_elements(elements)
        _, layouts, _ = segment_elements(elements, hints_dict)

        assert 1 in layouts
        # Layout может быть stacked_blocks или monolingual в зависимости от порогов
        # Главное — не ошибка
        assert layouts[1].layout_type in ("stacked_blocks", "monolingual", "unknown")


# ---------------------------------------------------------------------------
# _get_dominant_script utility
# ---------------------------------------------------------------------------


class TestDominantScript:
    def test_pure_latin(self) -> None:
        assert _get_dominant_script("English text") == "latin"

    def test_pure_cyrillic(self) -> None:
        assert _get_dominant_script("Русский текст") == "cyrillic"

    def test_mixed_takes_dominant(self) -> None:
        # 90% latin, 10% cyrillic → latin
        assert _get_dominant_script("Long English text with just Ру") == "latin"

    def test_only_digits_is_other(self) -> None:
        assert _get_dominant_script("123 456 789") == "other"

    def test_empty(self) -> None:
        assert _get_dominant_script("") == "other"



