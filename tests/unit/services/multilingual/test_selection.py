# tests/unit/services/multilingual/test_selection.py

"""
Unit тесты для Layer 5: Selection.

Покрывает:
- ParallelGroup: target visible, other hidden с полным контекстом
- ParallelGroup без target_language (ambiguous fallback)
- OrphanGroup target vs foreign
- MonolingualGroup: все visible
- Bypass groups (structured, neutral): всегда visible
- orphan_display_prefix локализация
- Fallback для сегментов вне групп
- Deterministic output
"""

from __future__ import annotations

import pytest

from services.multilingual.models import (
    BBox,
    LanguageSegment,
    MonolingualGroup,
    OrphanGroup,
    ParallelGroup,
)
from services.multilingual.selection import (
    _get_orphan_foreign_prefix,
    apply_visibility,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    segment_id: str,
    language: str = "ru",
    page: int = 1,
    source_element_id: str | None = None,
) -> LanguageSegment:
    return LanguageSegment(
        segment_id=segment_id,
        source_element_id=source_element_id or segment_id.replace("s", "e"),
        sub_index=0,
        text="Test",
        page=page,
        bbox=BBox(10, 20, 100, 40),
        bbox_is_approximate=False,
        bbox_split_method="original",
        reading_order_raw=0,
        anchor_uid=None,
        is_table_cell=False,
        cell_position=None,
        source_element_type="text",
        split_reason="none",
        split_confidence=1.0,
        language=language,
        script="cyrillic" if language == "ru" else "latin",
        detection_confidence=0.95,
        detection_method="lingua",
        is_reliable=True,
    )


# ---------------------------------------------------------------------------
# Basic
# ---------------------------------------------------------------------------


class TestBasic:
    def test_empty_input(self) -> None:
        segments, warnings = apply_visibility([], [], "ru")
        assert segments == []
        assert warnings == []

    def test_single_segment_no_group_gets_default_visible(self) -> None:
        seg = _make_segment("s1", "ru")
        segments, warnings = apply_visibility([seg], [], "ru")

        assert segments[0].visibility == "visible"
        # Warning генерируется для сегментов без группы
        assert any(w.warning_type == "segment_not_in_any_group" for w in warnings)


# ---------------------------------------------------------------------------
# ParallelGroup: target visible, other hidden
# ---------------------------------------------------------------------------


class TestParallelGroupTargetRu:
    def test_target_ru_visible_en_hidden(self) -> None:
        seg_en = _make_segment("s_en", "en")
        seg_ru = _make_segment("s_ru", "ru")

        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={"en": ["s_en"], "ru": ["s_ru"]},
            alignment_confidence=0.95,
            alignment_method="structural_anchor",
        )

        segments, _ = apply_visibility([seg_en, seg_ru], [group], "ru")

        # RU visible
        assert seg_ru.visibility == "visible"
        assert seg_ru.hidden_reason is None
        assert seg_ru.parallel_group_id == "pair_001"

        # EN hidden с полным контекстом
        assert seg_en.visibility == "hidden"
        assert seg_en.hidden_reason == "parallel_translation_available"
        assert seg_en.translation_of == ["s_ru"]
        assert seg_en.translation_pair_confidence == 0.95
        assert seg_en.translation_language == "ru"
        assert seg_en.parallel_group_id == "pair_001"

    def test_target_ru_visible_has_translation_of_partner(self) -> None:
        # Visible target тоже хранит translation_of - для LLM context
        seg_en = _make_segment("s_en", "en")
        seg_ru = _make_segment("s_ru", "ru")

        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={"en": ["s_en"], "ru": ["s_ru"]},
            alignment_confidence=0.9,
        )

        segments, _ = apply_visibility([seg_en, seg_ru], [group], "ru")

        # RU visible, но translation_of содержит EN партнёра
        assert seg_ru.translation_of == ["s_en"]
        assert seg_ru.translation_language == "en"


class TestParallelGroupTargetEn:
    def test_target_en_visible_ru_hidden(self) -> None:
        seg_en = _make_segment("s_en", "en")
        seg_ru = _make_segment("s_ru", "ru")

        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={"en": ["s_en"], "ru": ["s_ru"]},
            alignment_confidence=0.85,
        )

        segments, _ = apply_visibility([seg_en, seg_ru], [group], "en")

        assert seg_en.visibility == "visible"
        assert seg_ru.visibility == "hidden"
        assert seg_ru.hidden_reason == "parallel_translation_available"
        assert seg_ru.translation_of == ["s_en"]


class TestParallelGroupMultipleSegments:
    def test_multiple_segments_per_language(self) -> None:
        # Один параллельный блок с 2 EN и 2 RU сегментами
        seg_en1 = _make_segment("s_en1", "en")
        seg_en2 = _make_segment("s_en2", "en")
        seg_ru1 = _make_segment("s_ru1", "ru")
        seg_ru2 = _make_segment("s_ru2", "ru")

        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={
                "en": ["s_en1", "s_en2"],
                "ru": ["s_ru1", "s_ru2"],
            },
        )

        segments, _ = apply_visibility(
            [seg_en1, seg_en2, seg_ru1, seg_ru2], [group], "ru"
        )

        # Все RU visible
        assert seg_ru1.visibility == "visible"
        assert seg_ru2.visibility == "visible"

        # Все EN hidden с ссылкой на всех RU партнёров
        assert seg_en1.visibility == "hidden"
        assert seg_en2.visibility == "hidden"
        assert seg_en1.translation_of == ["s_ru1", "s_ru2"]
        assert seg_en2.translation_of == ["s_ru1", "s_ru2"]


class TestParallelGroupWithoutTarget:
    def test_pair_without_target_language_ambiguous(self) -> None:
        # Пара EN+FR, а target=RU
        seg_en = _make_segment("s_en", "en")
        seg_fr = _make_segment("s_fr", "fr")

        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={"en": ["s_en"], "fr": ["s_fr"]},
        )

        segments, warnings = apply_visibility([seg_en, seg_fr], [group], "ru")

        # Оба visible с флагом ambiguous
        assert seg_en.visibility == "visible_ambiguous"
        assert seg_en.is_ambiguous is True
        assert seg_fr.visibility == "visible_ambiguous"
        assert seg_fr.is_ambiguous is True

        # Warning сгенерирован
        assert any(
            w.warning_type == "parallel_group_without_target_language"
            for w in warnings
        )


# ---------------------------------------------------------------------------
# OrphanGroup
# ---------------------------------------------------------------------------


class TestOrphanGroupTarget:
    def test_orphan_target_language(self) -> None:
        # Orphan сегмент на target_language
        seg = _make_segment("s1", "ru")
        group = OrphanGroup(
            group_id="orph_001",
            page=1,
            orphan_language="ru",
            segment_ids=["s1"],
            orphan_reason="no_pair_found",
        )

        segments, _ = apply_visibility([seg], [group], "ru")

        assert seg.visibility == "visible_orphan_target"
        assert seg.is_orphan_target is True
        assert seg.is_orphan_foreign is False
        assert seg.orphan_display_prefix is None


class TestOrphanGroupForeign:
    def test_orphan_foreign_language_ru_target(self) -> None:
        # Orphan сегмент на EN, target=RU
        seg = _make_segment("s1", "en")
        group = OrphanGroup(
            group_id="orph_001",
            page=1,
            orphan_language="en",
            segment_ids=["s1"],
        )

        segments, _ = apply_visibility([seg], [group], "ru")

        assert seg.visibility == "visible_orphan_foreign"
        assert seg.is_orphan_target is False
        assert seg.is_orphan_foreign is True
        # Русский префикс
        assert seg.orphan_display_prefix == "[БЕЗ ПЕРЕВОДА]"

    def test_orphan_foreign_prefix_en_target(self) -> None:
        # target=EN → английский префикс
        seg = _make_segment("s1", "ru")
        group = OrphanGroup(
            group_id="orph_001",
            page=1,
            orphan_language="ru",
            segment_ids=["s1"],
        )

        segments, _ = apply_visibility([seg], [group], "en")

        assert seg.orphan_display_prefix == "[NO TRANSLATION]"

    def test_orphan_foreign_prefix_fr_target(self) -> None:
        seg = _make_segment("s1", "ru")
        group = OrphanGroup(
            group_id="orph_001",
            page=1,
            orphan_language="ru",
            segment_ids=["s1"],
        )

        segments, _ = apply_visibility([seg], [group], "fr")
        assert seg.orphan_display_prefix == "[SANS TRADUCTION]"


class TestOrphanForeignPrefix:
    def test_prefix_ru(self) -> None:
        assert _get_orphan_foreign_prefix("ru") == "[БЕЗ ПЕРЕВОДА]"

    def test_prefix_en(self) -> None:
        assert _get_orphan_foreign_prefix("en") == "[NO TRANSLATION]"

    def test_prefix_unknown_language_fallback(self) -> None:
        # Неизвестный язык → default EN prefix
        assert _get_orphan_foreign_prefix("xyz") == "[NO TRANSLATION]"


# ---------------------------------------------------------------------------
# MonolingualGroup: все visible
# ---------------------------------------------------------------------------


class TestMonolingualGroup:
    def test_all_segments_visible(self) -> None:
        seg1 = _make_segment("s1", "ru")
        seg2 = _make_segment("s2", "ru")
        seg3 = _make_segment("s3", "ru")

        group = MonolingualGroup(
            group_id="mono_001",
            page=1,
            segment_ids=["s1", "s2", "s3"],
        )

        segments, _ = apply_visibility([seg1, seg2, seg3], [group], "ru")

        for seg in segments:
            assert seg.visibility == "visible"
            assert seg.hidden_reason is None
            assert seg.translation_of == []
            assert seg.parallel_group_id is None
            assert seg.is_orphan_target is False
            assert seg.is_orphan_foreign is False

    def test_bypass_structured_data_visible(self) -> None:
        seg = _make_segment("s1", "structured_data")
        group = MonolingualGroup(
            group_id="bypass_001",
            page=1,
            segment_ids=["s1"],
        )

        segments, _ = apply_visibility([seg], [group], "ru")

        assert seg.visibility == "visible"
        assert seg.hidden_reason is None

    def test_bypass_neutral_visible(self) -> None:
        seg = _make_segment("s1", "neutral")
        group = MonolingualGroup(
            group_id="bypass_002",
            page=1,
            segment_ids=["s1"],
        )

        segments, _ = apply_visibility([seg], [group], "ru")
        assert seg.visibility == "visible"


# ---------------------------------------------------------------------------
# Coverage: все сегменты обработаны
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_all_segments_get_visibility_set(self) -> None:
        # Смешанный сценарий
        seg1 = _make_segment("s1", "ru")
        seg2 = _make_segment("s2", "en")
        seg3 = _make_segment("s3", "en")  # orphan foreign
        seg4 = _make_segment("s4", "neutral")

        groups = [
            ParallelGroup(
                group_id="pair_001", page=1,
                segments_by_language={"ru": ["s1"], "en": ["s2"]},
            ),
            OrphanGroup(
                group_id="orph_001", page=1,
                orphan_language="en", segment_ids=["s3"],
            ),
            MonolingualGroup(
                group_id="bypass_001", page=1,
                segment_ids=["s4"],
            ),
        ]

        segments, _ = apply_visibility([seg1, seg2, seg3, seg4], groups, "ru")

        # У каждого сегмента заполнен visibility
        for seg in segments:
            assert seg.visibility in (
                "visible", "hidden", "visible_orphan_target",
                "visible_orphan_foreign", "visible_ambiguous",
            )


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        seg_en = _make_segment("s_en", "en")
        seg_ru = _make_segment("s_ru", "ru")

        group = ParallelGroup(
            group_id="pair_001", page=1,
            segments_by_language={"en": ["s_en"], "ru": ["s_ru"]},
        )

        # Run twice
        segs1, _ = apply_visibility(
            [_make_segment("s_en", "en"), _make_segment("s_ru", "ru")],
            [group], "ru",
        )
        segs2, _ = apply_visibility(
            [_make_segment("s_en", "en"), _make_segment("s_ru", "ru")],
            [group], "ru",
        )

        # Оба run дают идентичный результат
        assert segs1[0].visibility == segs2[0].visibility
        assert segs1[0].translation_of == segs2[0].translation_of
        assert segs1[1].visibility == segs2[1].visibility
        assert segs1[1].translation_of == segs2[1].translation_of


# ---------------------------------------------------------------------------
# Real document scenarios
# ---------------------------------------------------------------------------


class TestRealDocumentScenarios:
    def test_target_ru_bilingual_doc(self) -> None:
        """
        Реалистичный сценарий: билингвальный RU-EN документ, target=RU.
        - Заголовок пара -> RU visible, EN hidden
        - Body пара -> RU visible, EN hidden
        - Один orphan EN -> visible_orphan_foreign
        - Reference-номера (neutral) -> visible
        """
        seg_head_en = _make_segment("s_head_en", "en")
        seg_head_ru = _make_segment("s_head_ru", "ru")
        seg_body_en = _make_segment("s_body_en", "en")
        seg_body_ru = _make_segment("s_body_ru", "ru")
        seg_orphan = _make_segment("s_orphan", "en")
        seg_neutral = _make_segment("s_neutral", "neutral")

        groups = [
            ParallelGroup(
                group_id="pair_head", page=1,
                segments_by_language={"en": ["s_head_en"], "ru": ["s_head_ru"]},
            ),
            ParallelGroup(
                group_id="pair_body", page=1,
                segments_by_language={"en": ["s_body_en"], "ru": ["s_body_ru"]},
            ),
            OrphanGroup(
                group_id="orph_1", page=1,
                orphan_language="en", segment_ids=["s_orphan"],
            ),
            MonolingualGroup(
                group_id="bypass_1", page=1, segment_ids=["s_neutral"],
            ),
        ]

        all_segs = [seg_head_en, seg_head_ru, seg_body_en, seg_body_ru, seg_orphan, seg_neutral]
        segments, _ = apply_visibility(all_segs, groups, "ru")

        # RU в парах — visible
        assert seg_head_ru.visibility == "visible"
        assert seg_body_ru.visibility == "visible"

        # EN в парах — hidden
        assert seg_head_en.visibility == "hidden"
        assert seg_body_en.visibility == "hidden"

        # Orphan EN — visible с префиксом
        assert seg_orphan.visibility == "visible_orphan_foreign"
        assert seg_orphan.orphan_display_prefix == "[БЕЗ ПЕРЕВОДА]"

        # Neutral — visible
        assert seg_neutral.visibility == "visible"

    def test_visible_segments_count_matches_expected(self) -> None:
        """
        Проверка: для RU-EN документа с target=RU, visible = RU_segments + orphan_EN + neutral.
        Hidden = EN paired.
        """
        segments = []
        segments.append(_make_segment("ru_1", "ru"))
        segments.append(_make_segment("en_1", "en"))
        segments.append(_make_segment("ru_2", "ru"))
        segments.append(_make_segment("en_2", "en"))
        segments.append(_make_segment("orphan_en", "en"))

        groups = [
            ParallelGroup(
                group_id="p1", page=1,
                segments_by_language={"ru": ["ru_1"], "en": ["en_1"]},
            ),
            ParallelGroup(
                group_id="p2", page=1,
                segments_by_language={"ru": ["ru_2"], "en": ["en_2"]},
            ),
            OrphanGroup(
                group_id="o1", page=1,
                orphan_language="en", segment_ids=["orphan_en"],
            ),
        ]

        result, _ = apply_visibility(segments, groups, "ru")

        visible = [s for s in result if s.visibility in (
            "visible", "visible_orphan_target", "visible_orphan_foreign", "visible_ambiguous"
        )]
        hidden = [s for s in result if s.visibility == "hidden"]

        # 3 visible: ru_1, ru_2, orphan_en
        assert len(visible) == 3
        # 2 hidden: en_1, en_2
        assert len(hidden) == 2



        