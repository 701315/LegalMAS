"""
Tests for per-field location validator (V1.3b).

Covers numeric-core matching semantics:
- prefix-agnostic matching ("п. 22" vs "Пункт 22")
- word-boundary protection ("п. 7" не матчится в "п. 7.1")
- compound references ("п. 7.1.1, п. 7.1.2")
- NBSP + whitespace normalization
- RU + EN parity
"""

from __future__ import annotations

import pytest

from engine.detectors.location_validator import (
    _extract_numeric_cores,
    _find_numeric_core_in_text,
    validate_location,
)


# ─── Unit-тесты вспомогательных функций ───────────────────────────────────────


class TestExtractNumericCores:
    """Проверяет извлечение numeric cores из различных форм clause_ref."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # RU префиксы
            ("п. 22", ["22"]),
            ("Пункт 22", ["22"]),
            ("пункт 22", ["22"]),
            ("пп. 22", ["22"]),
            ("подп. 22", ["22"]),
            ("Подпункт 22", ["22"]),
            ("ст. 5", ["5"]),
            ("Статья 5", ["5"]),
            ("ч. 3", ["3"]),
            ("Часть 3", ["3"]),
            ("Раздел 2", ["2"]),
            # Без префикса
            ("22", ["22"]),
            ("7.1", ["7.1"]),
            ("7.1.2", ["7.1.2"]),
            # EN префиксы
            ("Section 12.1", ["12.1"]),
            ("section 12.1", ["12.1"]),
            ("Sec. 12.1", ["12.1"]),
            ("Clause 3", ["3"]),
            ("cl. 3", ["3"]),
            ("Article 5", ["5"]),
            ("Art. 5", ["5"]),
            # Universal
            ("§ 12.1", ["12.1"]),
            ("§12.1", ["12.1"]),
            # NBSP и множественные пробелы
            ("п.\u00a022", ["22"]),
            ("п.   22", ["22"]),
            ("  п. 22  ", ["22"]),
            # Compound references
            ("п. 7.1.1, п. 7.1.2", ["7.1.1", "7.1.2"]),
            ("п. 7.1.1 и п. 7.1.2", ["7.1.1", "7.1.2"]),
            ("Sections 3 and 5", ["3", "5"]),
            ("п. 7.1, 7.2, 7.3", ["7.1", "7.2", "7.3"]),
            ("п. 5; п. 6", ["5", "6"]),
            ("Article 3 / Article 4", ["3", "4"]),
            ("ст. 5 или ст. 6", ["5", "6"]),
            # Nested references (буквенные суффиксы)
            ("п. 12.1(а)", ["12.1(а)"]),
            ("Section 5(b)", ["5(b)"]),
            # Edge cases
            ("", []),
            ("   ", []),
            ("abc", []),
            ("п.", []),
            ("Section", []),
            ("§", []),
        ],
    )
    def test_extraction(self, raw: str, expected: list[str]) -> None:
        assert _extract_numeric_cores(raw) == expected

    def test_none_returns_empty(self) -> None:
        assert _extract_numeric_cores(None) == []  # type: ignore[arg-type]

    def test_non_string_returns_empty(self) -> None:
        assert _extract_numeric_cores(123) == []  # type: ignore[arg-type]

    def test_duplicates_are_deduplicated(self) -> None:
        assert _extract_numeric_cores("п. 5, п. 5, п. 5") == ["5"]


class TestFindNumericCoreInText:
    """Проверяет word-boundary safe substring поиск numeric core."""

    def test_simple_match(self) -> None:
        assert _find_numeric_core_in_text("22", "Пункт 22 ПРИМЕНИМОЕ ПРАВО")

    def test_match_at_start(self) -> None:
        assert _find_numeric_core_in_text("22", "22 ПРИМЕНИМОЕ ПРАВО")

    def test_match_at_end(self) -> None:
        assert _find_numeric_core_in_text("22", "смотри пункт 22")

    def test_dotted_core_match(self) -> None:
        assert _find_numeric_core_in_text("7.1", "п. 7.1 текст")
        assert _find_numeric_core_in_text("7.1.2", "п. 7.1.2 текст")

    def test_word_boundary_rejects_prefix_of_larger(self) -> None:
        """'7' не должно матчиться в '7.1'."""
        assert not _find_numeric_core_in_text("7", "п. 7.1 текст")

    def test_word_boundary_rejects_prefix_of_10(self) -> None:
        """'7' не должно матчиться в '7.10'."""
        assert not _find_numeric_core_in_text("7", "п. 7.10 текст")

    def test_word_boundary_rejects_digit_suffix(self) -> None:
        """'22' не должно матчиться в '223'."""
        assert not _find_numeric_core_in_text("22", "код 223 применяется")

    def test_word_boundary_rejects_digit_prefix(self) -> None:
        """'22' не должно матчиться в '122'."""
        assert not _find_numeric_core_in_text("22", "код 122 применяется")

    def test_empty_core_returns_false(self) -> None:
        assert not _find_numeric_core_in_text("", "любой текст")

    def test_empty_text_returns_false(self) -> None:
        assert not _find_numeric_core_in_text("22", "")

    def test_dotted_core_boundary(self) -> None:
        """'7.1' не должно матчиться в '7.1.2'."""
        assert not _find_numeric_core_in_text("7.1", "см. п. 7.1.2 текст")

    def test_core_followed_by_dot_space_matches(self) -> None:
        """'3' должно матчиться в '3. Payment' (legal citation с точкой на конце)."""
        assert _find_numeric_core_in_text("3", "3. Payment terms shall be ...")

    def test_core_followed_by_dot_end_matches(self) -> None:
        """'22' должно матчиться в '22.' (точка в конце предложения)."""
        assert _find_numeric_core_in_text("22", "См. пункт 22.")

    def test_core_followed_by_dot_letter_matches(self) -> None:
        """'5' должно матчиться в '5.а)' (точка+буква — legal enum)."""
        assert _find_numeric_core_in_text("5", "п. 5.а) применяется")

    def test_dotted_core_at_sentence_end(self) -> None:
        """'7.1' должно матчиться в '7.1.' (точка в конце предложения)."""
        assert _find_numeric_core_in_text("7.1", "См. подпункт 7.1.")


# ─── Интеграционные тесты validate_location ──────────────────────────────────


class TestValidateLocationBasics:
    """Базовые сценарии, оставшиеся с V1.3."""

    def test_none_location_returns_fallback(self) -> None:
        location, fallback = validate_location(
            None,
            context_text="п. 12.1 договор регулируется правом РФ",
            context_pages=[7],
        )
        assert location is None
        assert fallback is not None
        assert "не указал" in fallback.reason

    def test_page_as_string_is_rejected(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 12.1", "page": "7"},
            context_text="Согласно п. 12.1 договор регулируется правом РФ.",
            context_pages=[7],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "low"
        assert location.page is None
        assert location.clause_ref == "п. 12.1"

    def test_neither_match_gives_fallback(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 99.9", "page": 99},
            context_text="Согласно п. 12.1 договор регулируется правом РФ.",
            context_pages=[7],
        )
        assert location is None
        assert fallback is not None
        assert "не подтверждена" in fallback.reason


class TestValidateLocationPrefixAgnostic:
    """
    Главная проблема пилота: LLM возвращает 'п. 22',
    в тексте написано 'Пункт 22' — должно матчиться.
    """

    def test_p_dot_matches_punkt_word(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 22", "page": 40},
            context_text="Пункт 22 ПРИМЕНИМОЕ ПРАВО текст текст.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"
        assert location.clause_ref == "п. 22"
        assert location.page == 40

    def test_punkt_word_matches_p_dot(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "Пункт 22", "page": 40},
            context_text="п. 22 регулирует данный вопрос.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_bare_number_matches_punkt_word(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "22", "page": 40},
            context_text="Пункт 22 ПРИМЕНИМОЕ ПРАВО.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_ru_statya_matches(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "ст. 5", "page": 3},
            context_text="Статья 5 договора устанавливает ...",
            context_pages=[3],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_bare_number_matches_leading_number(self) -> None:
        """
        Реальный кейс из пилота: в тексте '22 ПРИМЕНИМОЕ ПРАВО',
        LLM вернул 'п. 22'.
        """
        location, fallback = validate_location(
            {"clause_ref": "п. 22", "page": 40},
            context_text="22 ПРИМЕНИМОЕ ПРАВО. Взаимоотношения Сторон.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"


class TestValidateLocationEnParity:
    """EN префиксы работают наравне с RU."""

    def test_section_matches_section(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "Section 12.1", "page": 7},
            context_text="Section 12.1 governs dispute resolution.",
            context_pages=[7],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_section_matches_case_insensitive(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "SECTION 12.1", "page": 7},
            context_text="section 12.1 governs dispute resolution.",
            context_pages=[7],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_clause_matches_bare_number(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "Clause 3", "page": 2},
            context_text="3. Payment terms shall be ...",
            context_pages=[2],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_section_symbol_matches(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "§ 12.1", "page": 7},
            context_text="§ 12.1 applies here.",
            context_pages=[7],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"


class TestValidateLocationWordBoundary:
    """
    Критично: word-boundary защита не должна создавать ложные позитивы.
    """

    def test_p_7_does_not_match_p_7_1(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 7", "page": 3},
            context_text="Согласно п. 7.1 договор регулируется.",
            context_pages=[3],
        )
        # 7 не должно матчиться в 7.1 → clause_ref_ok=False,
        # но page валидна → low confidence
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "low"

    def test_p_7_does_not_match_p_7_10(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 7", "page": 99},
            context_text="См. п. 7.10 договора.",
            context_pages=[3],
        )
        # 7 не должно матчиться в 7.10, page тоже нет → fallback
        assert location is None
        assert fallback is not None

    def test_bare_22_does_not_match_223(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "22", "page": 99},
            context_text="код 223 упоминается в тексте.",
            context_pages=[3],
        )
        assert location is None
        assert fallback is not None


class TestValidateLocationCompoundReferences:
    """
    Главная проблема пилота: LLM возвращает 'п. 7.1.1, п. 7.1.2',
    в тексте эти пункты по отдельности — должно матчиться по любому core.
    """

    def test_compound_matches_by_first_core(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 7.1.1, п. 7.1.2", "page": 5},
            context_text="Согласно п. 7.1.1 договор регулируется.",
            context_pages=[5],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"
        assert location.clause_ref == "п. 7.1.1, п. 7.1.2"

    def test_compound_matches_by_second_core(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 7.1.1, п. 7.1.2", "page": 5},
            context_text="Согласно п. 7.1.2 договор регулируется.",
            context_pages=[5],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_compound_with_i_separator(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 11.1 и п. 11.2", "page": 7},
            context_text="Согласно п. 11.1 договор регулируется.",
            context_pages=[7],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_compound_with_and_separator_en(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "Sections 3 and 5", "page": 2},
            context_text="Section 5 applies to this matter.",
            context_pages=[2],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_compound_without_prefix_repetition(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 7.1, 7.2, 7.3", "page": 5},
            context_text="Согласно п. 7.2 договор регулируется.",
            context_pages=[5],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_compound_no_matches_gives_fallback(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 99.9, п. 100.1", "page": 99},
            context_text="Совсем другой текст без нужных ссылок.",
            context_pages=[7],
        )
        assert location is None
        assert fallback is not None


class TestValidateLocationWhitespace:
    """Нормализация non-breaking space и множественных пробелов."""

    def test_nbsp_between_prefix_and_number(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п.\u00a022", "page": 40},
            context_text="п. 22 регулирует данный вопрос.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_multiple_spaces_between_prefix_and_number(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п.     22", "page": 40},
            context_text="Пункт 22 регулирует.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"


class TestValidateLocationDisplayString:
    """LocationInfo.clause_ref сохраняет исходную человеческую форму."""

    def test_display_preserves_llm_original(self) -> None:
        location, _ = validate_location(
            {"clause_ref": "п. 22", "page": 40},
            context_text="Пункт 22 текст.",
            context_pages=[40],
        )
        assert location is not None
        assert location.clause_ref == "п. 22"

    def test_display_preserves_compound_original(self) -> None:
        location, _ = validate_location(
            {"clause_ref": "п. 7.1.1, п. 7.1.2", "page": 5},
            context_text="п. 7.1.1 применяется.",
            context_pages=[5],
        )
        assert location is not None
        assert location.clause_ref == "п. 7.1.1, п. 7.1.2"

    def test_display_normalizes_nbsp_and_whitespace(self) -> None:
        location, _ = validate_location(
            {"clause_ref": "п.\u00a022", "page": 40},
            context_text="п. 22 регулирует.",
            context_pages=[40],
        )
        assert location is not None
        assert location.clause_ref == "п. 22"


class TestValidateLocationConfidenceLogic:
    """Проверка high/low/fallback комбинаций."""

    def test_high_when_both_valid(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 22", "page": 40},
            context_text="Пункт 22 текст.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "high"

    def test_low_when_only_clause_ref_valid(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 22", "page": 99},
            context_text="Пункт 22 текст.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "low"

    def test_low_when_only_page_valid(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 99.9", "page": 40},
            context_text="Пункт 22 текст.",
            context_pages=[40],
        )
        assert fallback is None
        assert location is not None
        assert location.location_confidence == "low"

    def test_fallback_when_neither_valid(self) -> None:
        location, fallback = validate_location(
            {"clause_ref": "п. 99.9", "page": 99},
            context_text="Пункт 22 текст.",
            context_pages=[40],
        )
        assert location is None
        assert fallback is not None