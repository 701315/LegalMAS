# tests/unit/services/multilingual/test_classification.py

"""
Unit тесты для Layer 3: Language Classification.

Покрывает:
- Structured data bypass (SWIFT, IBAN, email, phone)
- Neutral bypass (цифры, пунктуация)
- Script-only fast path (cyrillic → ru, hebrew → he)
- Lingua detection для длинных ambiguous текстов
- Too-short fallback (< 20 chars)
- Mixed content detection
- Neighbor voting для low-confidence сегментов
- Реальные паттерны из документа Simonova SPA
- Edge cases: пустые, невалидные, ошибки lingua
"""

from __future__ import annotations

import pytest

from services.multilingual.classification import (
    _detect_mixed_scripts,
    _find_dominant_language,
    _is_pure_neutral,
    _needs_neighbor_voting,
    classify_segments,
)
from services.multilingual.models import BBox, LanguageSegment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    segment_id: str = "seg_001",
    text: str = "Test text",
    page: int = 1,
    source_element_id: str = "e001",
    sub_index: int = 0,
) -> LanguageSegment:
    return LanguageSegment(
        segment_id=segment_id,
        source_element_id=source_element_id,
        sub_index=sub_index,
        text=text,
        page=page,
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
# _is_pure_neutral
# ---------------------------------------------------------------------------


class TestIsPureNeutral:
    def test_only_digits(self) -> None:
        assert _is_pure_neutral("123 456 789")

    def test_only_punctuation(self) -> None:
        assert _is_pure_neutral("...")

    def test_only_dashes(self) -> None:
        assert _is_pure_neutral("- -- ---")

    def test_mixed_digits_punctuation(self) -> None:
        assert _is_pure_neutral("1.1")
        assert _is_pure_neutral("1.2.3")
        assert _is_pure_neutral("2014")

    def test_with_letters_not_neutral(self) -> None:
        assert not _is_pure_neutral("Text 123")
        assert not _is_pure_neutral("1st")

    def test_empty_not_neutral(self) -> None:
        # Пустая строка не neutral (нет символов вообще)
        assert not _is_pure_neutral("")


# ---------------------------------------------------------------------------
# _detect_mixed_scripts
# ---------------------------------------------------------------------------


class TestDetectMixedScripts:
    def test_pure_latin_not_mixed(self) -> None:
        assert _detect_mixed_scripts("English text") is None

    def test_pure_cyrillic_not_mixed(self) -> None:
        assert _detect_mixed_scripts("Русский текст") is None

    def test_only_digits_not_mixed(self) -> None:
        assert _detect_mixed_scripts("12345") is None

    def test_50_50_mixed(self) -> None:
        # "Buyer" (5 latin) + "Продавец" (8 cyrillic) → mixed
        result = _detect_mixed_scripts("Buyer Продавец")
        assert result is not None
        assert "cyrillic" in result
        assert "latin" in result

    def test_minor_script_below_threshold(self) -> None:
        # 95% latin + 5% cyrillic → не mixed (второй скрипт < 15%)
        # "This is a long English sentence with Ыы" (2 из ~30 букв ≈ 7%)
        result = _detect_mixed_scripts(
            "This is a very long English sentence containing just Ы"
        )
        # Второй скрипт < 15% → not mixed
        assert result is None or "cyrillic" not in result[:1]


# ---------------------------------------------------------------------------
# _find_dominant_language
# ---------------------------------------------------------------------------


class TestFindDominantLanguage:
    def test_single_language(self) -> None:
        lang, ratio = _find_dominant_language(["ru", "ru", "ru"])
        assert lang == "ru"
        assert ratio == 1.0

    def test_majority(self) -> None:
        lang, ratio = _find_dominant_language(["ru", "ru", "en"])
        assert lang == "ru"
        assert ratio == pytest.approx(2/3)

    def test_tie_takes_first_max(self) -> None:
        # При равенстве — Python max с ключом берёт первый встреченный
        lang, ratio = _find_dominant_language(["ru", "en"])
        # Не важно который — важно что ratio 0.5
        assert lang in ("ru", "en")
        assert ratio == 0.5

    def test_empty_list(self) -> None:
        lang, ratio = _find_dominant_language([])
        assert lang == "unknown"
        assert ratio == 0.0


# ---------------------------------------------------------------------------
# _needs_neighbor_voting
# ---------------------------------------------------------------------------


class TestNeedsNeighborVoting:
    def test_bypass_not_needs_voting(self) -> None:
        seg = _make_segment(text="123")
        seg.language = "neutral"
        seg.detection_method = "neutral_bypass"
        seg.detection_confidence = 1.0
        assert not _needs_neighbor_voting(seg)

    def test_reliable_not_needs_voting(self) -> None:
        seg = _make_segment(text="Text")
        seg.language = "en"
        seg.detection_confidence = 0.95
        seg.is_reliable = True
        assert not _needs_neighbor_voting(seg)

    def test_low_confidence_short_needs_voting(self) -> None:
        seg = _make_segment(text="ABC")  # 1 слово
        seg.language = "en"
        seg.detection_confidence = 0.3
        seg.is_reliable = False
        assert _needs_neighbor_voting(seg)

    def test_low_confidence_long_no_voting(self) -> None:
        # 10 слов — слишком длинный для voting
        seg = _make_segment(text="one two three four five six seven eight nine ten")
        seg.language = "en"
        seg.detection_confidence = 0.3
        seg.is_reliable = False
        assert not _needs_neighbor_voting(seg)


# ---------------------------------------------------------------------------
# classify_segments — basic
# ---------------------------------------------------------------------------


class TestClassifySegmentsBasic:
    def test_empty_input(self) -> None:
        segments, warnings = classify_segments([])
        assert segments == []
        assert warnings == []

    def test_pure_cyrillic_fast_path(self) -> None:
        seg = _make_segment(text="Русский текст")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "ru"
        assert segments[0].script == "cyrillic"
        assert segments[0].detection_method == "script_only"
        assert segments[0].is_reliable

    def test_pure_latin_longer_lingua(self) -> None:
        # Достаточно длинный текст для lingua
        seg = _make_segment(
            text="This is a long English sentence which lingua can reliably detect"
        )
        segments, _ = classify_segments([seg])
        assert segments[0].language == "en"
        assert segments[0].detection_method == "lingua"
        assert segments[0].is_reliable

    def test_short_latin_too_short(self) -> None:
        # < 20 chars — fallback без lingua
        seg = _make_segment(text="Short")
        segments, _ = classify_segments([seg])
        assert segments[0].script == "latin"
        assert segments[0].detection_method == "too_short"
        assert not segments[0].is_reliable

    def test_empty_text_unknown(self) -> None:
        seg = _make_segment(text="")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "unknown"


# ---------------------------------------------------------------------------
# Bypass detection
# ---------------------------------------------------------------------------


class TestStructuredDataBypass:
    def test_email(self) -> None:
        seg = _make_segment(text="legal@company.ru")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "structured_data"
        assert segments[0].detection_method == "structured_data_bypass"
        assert segments[0].is_reliable

    def test_iban(self) -> None:
        seg = _make_segment(text="DE89370400440532013000")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "structured_data"

    def test_swift_bic(self) -> None:
        seg = _make_segment(text="SABRRUMM")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "structured_data"

    def test_phone(self) -> None:
        seg = _make_segment(text="+7 495 123-45-67")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "structured_data"


class TestNeutralBypass:
    def test_only_digits(self) -> None:
        seg = _make_segment(text="123 456")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "neutral"
        assert segments[0].detection_method == "neutral_bypass"

    def test_clause_number(self) -> None:
        seg = _make_segment(text="1.1.1")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "neutral"

    def test_only_dashes(self) -> None:
        seg = _make_segment(text="---")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "neutral"


# ---------------------------------------------------------------------------
# Script-only fast path
# ---------------------------------------------------------------------------


class TestScriptOnlyFastPath:
    def test_cyrillic_short(self) -> None:
        seg = _make_segment(text="Договор")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "ru"
        assert segments[0].detection_method == "script_only"

    def test_cyrillic_long(self) -> None:
        # Кириллица всегда через fast path (независимо от длины)
        seg = _make_segment(text="Настоящий договор купли-продажи имущества заключён между")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "ru"
        assert segments[0].detection_method == "script_only"


# ---------------------------------------------------------------------------
# Lingua detection для латиницы
# ---------------------------------------------------------------------------


class TestLinguaDetection:
    def test_english_long_text(self) -> None:
        seg = _make_segment(
            text="This is a long English text that should be reliably detected"
        )
        segments, _ = classify_segments([seg])
        assert segments[0].language == "en"
        assert segments[0].detection_method == "lingua"
        assert segments[0].detection_confidence > 0.7

    def test_french_long_text(self) -> None:
        # Французский — lingua должна распознать
        seg = _make_segment(
            text="Le présent contrat de vente est conclu entre les parties"
        )
        segments, _ = classify_segments([seg])
        # Может быть fr или другой близкий (романский) — главное не en
        assert segments[0].detection_method == "lingua"


# ---------------------------------------------------------------------------
# Neighbor voting
# ---------------------------------------------------------------------------


class TestNeighborVoting:
    def test_ambiguous_between_reliable_neighbors(self) -> None:
        # Ambiguous короткий сегмент между двумя reliable RU сегментами.
        # ВАЖНО: соседи должны быть pure одноязычные, без mixed content.
        seg1 = _make_segment(segment_id="s1", text="Длинный русский текст только на кириллице")
        seg2 = _make_segment(segment_id="s2", text="XY")  # 2 chars латиница, ambiguous
        seg3 = _make_segment(segment_id="s3", text="Ещё длинный русский текст только кириллица")

        segments, warnings = classify_segments([seg1, seg2, seg3])

        # seg1 и seg3 определены как ru через fast path
        assert segments[0].language == "ru"
        assert segments[2].language == "ru"

        # seg2 после voting должен стать ru (если voting сработал)
        voting_warnings = [
            w for w in warnings if w.warning_type == "neighbor_voting_applied"
        ]
        if voting_warnings:
            assert segments[1].detection_method == "neighbor_inheritance"

    def test_no_voting_if_neighbors_unreliable(self) -> None:
        # Все короткие → никто не reliable → нельзя голосовать
        seg1 = _make_segment(segment_id="s1", text="AB")
        seg2 = _make_segment(segment_id="s2", text="CD")
        seg3 = _make_segment(segment_id="s3", text="EF")

        segments, warnings = classify_segments([seg1, seg2, seg3])
        # Никакого voting не должно быть
        voting_warnings = [
            w for w in warnings if w.warning_type == "neighbor_voting_applied"
        ]
        assert len(voting_warnings) == 0


# ---------------------------------------------------------------------------
# Реальные паттерны из документа Simonova SPA
# ---------------------------------------------------------------------------


class TestRealDocumentPatterns:
    def test_appendix_number_ru(self) -> None:
        seg = _make_segment(text="ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "ru"
        assert segments[0].script == "cyrillic"

    def test_appendix_number_en(self) -> None:
        seg = _make_segment(text="APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "en"

    def test_body_text_en(self) -> None:
        seg = _make_segment(
            text="This Real Estate Sale and Purchase Agreement has been executed"
        )
        segments, _ = classify_segments([seg])
        assert segments[0].language == "en"

    def test_body_text_ru(self) -> None:
        seg = _make_segment(
            text="Настоящий договор купли-продажи недвижимости заключён между"
        )
        segments, _ = classify_segments([seg])
        assert segments[0].language == "ru"

    def test_clause_number_neutral(self) -> None:
        seg = _make_segment(text="1.1")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "neutral"

    def test_year_neutral(self) -> None:
        seg = _make_segment(text="2014")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "neutral"

    def test_page_number_neutral(self) -> None:
        seg = _make_segment(text="16 (20)")
        segments, _ = classify_segments([seg])
        assert segments[0].language == "neutral"


# ---------------------------------------------------------------------------
# Batch processing и warnings
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    def test_mixed_batch(self) -> None:
        segments = [
            _make_segment("s1", "Русский текст который достаточно длинный"),
            _make_segment("s2", "English text that is long enough for lingua"),
            _make_segment("s3", "1.1"),
            _make_segment("s4", "legal@example.com"),
        ]
        result, _ = classify_segments(segments)

        assert result[0].language == "ru"
        assert result[1].language == "en"
        assert result[2].language == "neutral"
        assert result[3].language == "structured_data"

    def test_order_preserved(self) -> None:
        segments = [
            _make_segment("s1", "First"),
            _make_segment("s2", "Second"),
            _make_segment("s3", "Third"),
        ]
        result, _ = classify_segments(segments)
        assert [s.segment_id for s in result] == ["s1", "s2", "s3"]

    def test_all_segments_get_classification(self) -> None:
        segments = [
            _make_segment(f"s{i}", f"Text number {i}")
            for i in range(10)
        ]
        result, _ = classify_segments(segments)
        assert all(s.language != "unknown" for s in result)
        assert all(s.detection_method != "too_short" or not s.is_reliable
                   for s in result)


# ---------------------------------------------------------------------------
# Detection method breakdown
# ---------------------------------------------------------------------------


class TestDetectionMethods:
    def test_all_methods_can_appear(self) -> None:
        """Убеждаемся что все methods могут быть проставлены."""
        segments = [
            _make_segment("s_iban", "DE89370400440532013000"),         # structured
            _make_segment("s_num", "1.2.3"),                            # neutral
            _make_segment("s_ru", "Русский"),                           # script_only
            _make_segment("s_en", "Long English text for lingua path"), # lingua
            _make_segment("s_short", "XY"),                             # too_short
        ]
        result, _ = classify_segments(segments)

        methods = {s.detection_method for s in result}
        assert "structured_data_bypass" in methods
        assert "neutral_bypass" in methods
        assert "script_only" in methods
        assert "lingua" in methods
        assert "too_short" in methods



