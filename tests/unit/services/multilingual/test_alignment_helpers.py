# tests/unit/services/multilingual/test_alignment_helpers.py

"""
Unit тесты для alignment_helpers.

Покрывает:
- cross_language_anchor_key: все категории, разные языки
- normalize_number_representation: пунктуация, пробелы
- ScopeTracker: переходы состояний, история
- Edge cases: None, пустые, невалидные
"""

from __future__ import annotations

import pytest

from services.multilingual.alignment_helpers import (
    ScopeTracker,
    cross_language_anchor_key,
    normalize_number_representation,
)


# ---------------------------------------------------------------------------
# cross_language_anchor_key
# ---------------------------------------------------------------------------


class TestCrossLanguageAnchorKey:
    def test_none_returns_none(self) -> None:
        assert cross_language_anchor_key(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert cross_language_anchor_key("") is None
        assert cross_language_anchor_key("   ") is None

    # Clause numbers
    def test_simple_number(self) -> None:
        assert cross_language_anchor_key("1") == ("clause", "1")

    def test_nested_number(self) -> None:
        assert cross_language_anchor_key("1.1") == ("clause", "1.1")

    def test_deeply_nested(self) -> None:
        assert cross_language_anchor_key("1.1.1") == ("clause", "1.1.1")

    def test_number_with_trailing_dot(self) -> None:
        assert cross_language_anchor_key("1.") == ("clause", "1")

    def test_number_with_trailing_paren(self) -> None:
        assert cross_language_anchor_key("1)") == ("clause", "1")

    # Appendix - разные языки должны дать один ключ
    def test_appendix_en(self) -> None:
        assert cross_language_anchor_key("appendix-1") == ("appendix", "1")

    def test_appendix_ru(self) -> None:
        assert cross_language_anchor_key("приложение-1") == ("appendix", "1")

    def test_appendix_ru_short(self) -> None:
        assert cross_language_anchor_key("прил-1") == ("appendix", "1")

    def test_appendix_fr(self) -> None:
        assert cross_language_anchor_key("annexe-1") == ("appendix", "1")

    def test_appendix_de(self) -> None:
        assert cross_language_anchor_key("anhang-1") == ("appendix", "1")

    def test_appendix_tr(self) -> None:
        assert cross_language_anchor_key("ek-1") == ("appendix", "1")

    def test_appendix_es(self) -> None:
        assert cross_language_anchor_key("anexo-1") == ("appendix", "1")

    def test_appendix_annex_synonym(self) -> None:
        assert cross_language_anchor_key("annex-1") == ("appendix", "1")

    def test_appendix_schedule_synonym(self) -> None:
        assert cross_language_anchor_key("schedule-1") == ("appendix", "1")

    def test_appendix_exhibit_synonym(self) -> None:
        assert cross_language_anchor_key("exhibit-1") == ("appendix", "1")

    def test_appendix_multi_digit(self) -> None:
        assert cross_language_anchor_key("appendix-15") == ("appendix", "15")

    # Cross-language equivalence
    def test_ru_and_en_appendix_same_key(self) -> None:
        """CRITICAL: RU и EN appendix должны иметь один ключ."""
        ru = cross_language_anchor_key("приложение-1")
        en = cross_language_anchor_key("appendix-1")
        assert ru == en

    def test_fr_de_ru_en_appendix_same_key(self) -> None:
        keys = [
            cross_language_anchor_key("приложение-3"),
            cross_language_anchor_key("appendix-3"),
            cross_language_anchor_key("annexe-3"),
            cross_language_anchor_key("anhang-3"),
        ]
        assert all(k == ("appendix", "3") for k in keys)

    # Amendment
    def test_amendment_en(self) -> None:
        assert cross_language_anchor_key("amendment-1") == ("amendment", "1")

    def test_amendment_addendum(self) -> None:
        assert cross_language_anchor_key("addendum-1") == ("amendment", "1")

    def test_amendment_ru(self) -> None:
        assert cross_language_anchor_key("дополнение-1") == ("amendment", "1")

    def test_ru_and_en_amendment_same_key(self) -> None:
        ru = cross_language_anchor_key("дополнение-2")
        en = cross_language_anchor_key("amendment-2")
        assert ru == en

    # Roman numerals
    def test_roman_uppercase(self) -> None:
        assert cross_language_anchor_key("I") == ("roman", "i")

    def test_roman_lowercase(self) -> None:
        assert cross_language_anchor_key("iv") == ("roman", "iv")

    def test_roman_case_normalized(self) -> None:
        # Upper и lower дают одинаковый ключ
        assert cross_language_anchor_key("V") == cross_language_anchor_key("v")

    # Letters
    def test_letter_english(self) -> None:
        assert cross_language_anchor_key("a") == ("letter", "a")

    def test_letter_uppercase(self) -> None:
        assert cross_language_anchor_key("A") == ("letter", "a")

    def test_letter_cyrillic(self) -> None:
        assert cross_language_anchor_key("а") == ("letter", "а")

    # List markers
    def test_list_marker(self) -> None:
        assert cross_language_anchor_key("(1)") == ("list_marker", "1")

    def test_list_marker_letter(self) -> None:
        assert cross_language_anchor_key("(a)") == ("list_marker", "a")

    # Unknown prefix
    def test_unknown_prefix_preserved(self) -> None:
        # Неизвестный prefix - помечаем как unknown но не теряем номер
        result = cross_language_anchor_key("something-1")
        assert result == ("unknown", "1")


# ---------------------------------------------------------------------------
# normalize_number_representation
# ---------------------------------------------------------------------------


class TestNormalizeNumberRepresentation:
    def test_simple_number(self) -> None:
        assert normalize_number_representation("1") == "1"

    def test_removes_trailing_dot(self) -> None:
        assert normalize_number_representation("1.") == "1"

    def test_removes_trailing_paren(self) -> None:
        assert normalize_number_representation("1)") == "1"

    def test_removes_leading_paren(self) -> None:
        assert normalize_number_representation("(1") == "1"

    def test_full_bracket(self) -> None:
        assert normalize_number_representation("(1)") == "1"

    def test_nested_numeric(self) -> None:
        assert normalize_number_representation("1.1") == "1.1"

    def test_nested_with_trailing(self) -> None:
        assert normalize_number_representation("1.1.") == "1.1"

    def test_trim_whitespace(self) -> None:
        assert normalize_number_representation(" 1 ") == "1"

    def test_ocr_spaces_collapsed(self) -> None:
        # OCR может дать "1. 1. 1" вместо "1.1.1"
        assert normalize_number_representation("1. 1. 1") == "1.1.1"

    def test_empty_returns_empty(self) -> None:
        assert normalize_number_representation("") == ""

    def test_none_input_handled(self) -> None:
        # None не подается напрямую, но if передадут через str -> ""
        assert normalize_number_representation("") == ""


# ---------------------------------------------------------------------------
# ScopeTracker
# ---------------------------------------------------------------------------


class TestScopeTracker:
    def test_initial_scope_empty(self) -> None:
        tracker = ScopeTracker()
        assert tracker.current_scope == ""

    def test_clause_does_not_change_scope(self) -> None:
        tracker = ScopeTracker()
        tracker.update("1")
        assert tracker.current_scope == ""

        tracker.update("1.1")
        assert tracker.current_scope == ""

    def test_appendix_changes_scope(self) -> None:
        tracker = ScopeTracker()
        tracker.update("appendix-1")
        assert tracker.current_scope == "appendix::1"

    def test_appendix_ru(self) -> None:
        tracker = ScopeTracker()
        tracker.update("приложение-1")
        assert tracker.current_scope == "appendix::1"

    def test_multiple_appendices(self) -> None:
        tracker = ScopeTracker()
        tracker.update("appendix-1")
        assert tracker.current_scope == "appendix::1"

        tracker.update("1.1")  # клауза внутри appendix
        assert tracker.current_scope == "appendix::1"

        tracker.update("appendix-2")  # новый appendix
        assert tracker.current_scope == "appendix::2"

    def test_amendment_changes_scope(self) -> None:
        tracker = ScopeTracker()
        tracker.update("amendment-1")
        assert tracker.current_scope == "amendment::1"

    def test_ru_and_en_appendix_same_scope(self) -> None:
        """Русский и английский appendix header должны дать один scope."""
        tracker_ru = ScopeTracker()
        tracker_ru.update("приложение-3")

        tracker_en = ScopeTracker()
        tracker_en.update("appendix-3")

        assert tracker_ru.current_scope == tracker_en.current_scope

    def test_none_anchor_no_change(self) -> None:
        tracker = ScopeTracker()
        tracker.update("appendix-1")
        assert tracker.current_scope == "appendix::1"

        tracker.update(None)
        assert tracker.current_scope == "appendix::1"

        tracker.update("")
        assert tracker.current_scope == "appendix::1"

    def test_reset(self) -> None:
        tracker = ScopeTracker()
        tracker.update("appendix-1")
        assert tracker.current_scope == "appendix::1"

        tracker.reset()
        assert tracker.current_scope == ""

    def test_history_tracking(self) -> None:
        tracker = ScopeTracker()
        tracker.update("appendix-1")
        tracker.update("1.1")
        tracker.update("appendix-2")
        tracker.update("amendment-1")

        history = tracker.history()
        assert "appendix::1" in history
        assert "appendix::2" in history
        assert "amendment::1" in history

    def test_history_no_duplicate_on_same_scope(self) -> None:
        # Если два раза подряд update с тем же anchor - history не дублируется
        tracker = ScopeTracker()
        tracker.update("appendix-1")
        tracker.update("appendix-1")
        tracker.update("1.1")

        history = tracker.history()
        # Only one entry for appendix-1
        assert history.count("appendix::1") == 1


# ---------------------------------------------------------------------------
# Real document scenarios
# ---------------------------------------------------------------------------


class TestRealDocumentScenarios:
    """
    Проверка на реальных сценариях из Simonova SPA документа.
    Симулируем reading order сегментов.
    """

    def test_toc_scope_stays_empty(self) -> None:
        """TOC entries из page 2: "1 DEFINITIONS", "2 SUBJECT"... не меняют scope."""
        tracker = ScopeTracker()
        anchors = ["1", "2", "3", "4", "5", "6", "7", "8"]  # клаузы TOC
        for a in anchors:
            tracker.update(a)
        assert tracker.current_scope == ""

    def test_appendix_transitions(self) -> None:
        """
        Реальный сценарий из Simonova:
        - Тело договора: клаузы 1, 1.1, 1.2 ... 8
        - Затем "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE"
        - Клаузы внутри Appendix 1
        - Затем "APPENDIX No. 2 TERMS AND CONDITIONS"
        - Клаузы внутри Appendix 2
        """
        tracker = ScopeTracker()

        # Тело договора
        tracker.update("1")
        tracker.update("1.1")
        assert tracker.current_scope == ""

        # Начало Appendix 1
        tracker.update("appendix-1")
        assert tracker.current_scope == "appendix::1"

        # Клаузы внутри Appendix 1
        tracker.update("1")
        tracker.update("1.1")
        assert tracker.current_scope == "appendix::1"

        # Переход к Appendix 2
        tracker.update("appendix-2")
        assert tracker.current_scope == "appendix::2"

    def test_bilingual_appendix_headers_scope_correct(self) -> None:
        """
        Если сегменты EN и RU appendix headers идут подряд (после split
        одного bilingual элемента), scope не должен переключаться дважды
        на тот же appendix.
        """
        tracker = ScopeTracker()

        # Bilingual header split - EN сначала
        tracker.update("appendix-1")
        assert tracker.current_scope == "appendix::1"

        # RU идёт следом - тот же appendix
        tracker.update("приложение-1")
        assert tracker.current_scope == "appendix::1"

        # History не должна иметь дубликатов
        assert tracker.history().count("appendix::1") == 1


        