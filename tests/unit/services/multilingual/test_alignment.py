# tests/unit/services/multilingual/test_alignment.py

"""
Unit тесты для Layer 4: Alignment.

Покрывает:
- split_from_single_element (naивысший приоритет)
- structural_anchor matching (scope-aware)
- coordinate_columns matching
- stacked_pairs matching
- positional_sequential для stacked_blocks
- Bypass segments (structured, neutral)
- Orphan handling
- MonolingualGroup для monolingual pages
- Deterministic output
- Real document patterns
"""

from __future__ import annotations

import pytest

from services.multilingual.alignment import (
    _dominant_language,
    align_segments,
)
from services.multilingual.models import (
    BBox,
    LanguageSegment,
    MonolingualGroup,
    OrphanGroup,
    PageLayout,
    ParallelGroup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    segment_id: str,
    text: str,
    language: str,
    page: int = 1,
    source_element_id: str | None = None,
    sub_index: int = 0,
    bbox: BBox | None = None,
    anchor_uid: str | None = None,
    is_reliable: bool = True,
    detection_method: str = "lingua",
) -> LanguageSegment:
    return LanguageSegment(
        segment_id=segment_id,
        source_element_id=source_element_id or segment_id.replace("seg_", "e_"),
        sub_index=sub_index,
        text=text,
        page=page,
        bbox=bbox or BBox(10, 20, 400, 40),
        bbox_is_approximate=False,
        bbox_split_method="original",
        reading_order_raw=0,
        anchor_uid=anchor_uid,
        is_table_cell=False,
        cell_position=None,
        source_element_type="text",
        split_reason="none",
        split_confidence=1.0,
        language=language,
        script="latin" if language == "en" else "cyrillic" if language == "ru" else "other",
        detection_confidence=0.95 if is_reliable else 0.4,
        detection_method=detection_method,
        is_reliable=is_reliable,
    )


def _make_page_layout(
    page: int,
    layout_type: str,
    left_x_range: tuple | None = None,
    right_x_range: tuple | None = None,
    block_boundaries: list | None = None,
) -> PageLayout:
    return PageLayout(
        page=page,
        layout_type=layout_type,
        left_column_x_range=left_x_range,
        right_column_x_range=right_x_range,
        block_boundaries=block_boundaries or [],
    )


# ---------------------------------------------------------------------------
# Basic
# ---------------------------------------------------------------------------


class TestAlignSegmentsBasic:
    def test_empty_input(self) -> None:
        groups, warnings = align_segments([], {}, "ru")
        assert groups == []
        assert warnings == []

    def test_single_monolingual_segment(self) -> None:
        seg = _make_segment("seg_1", "Text", "ru")
        layouts = {1: _make_page_layout(1, "monolingual")}
        groups, _ = align_segments([seg], layouts, "ru")
        assert len(groups) == 1
        assert isinstance(groups[0], MonolingualGroup)


# ---------------------------------------------------------------------------
# Bypass groups
# ---------------------------------------------------------------------------


class TestBypassGroups:
    def test_structured_data_bypass(self) -> None:
        seg = _make_segment(
            "seg_1", "legal@company.com", "structured_data",
            detection_method="structured_data_bypass"
        )
        groups, _ = align_segments([seg], {}, "ru")
        # Structured data должен получить свою MonolingualGroup
        assert len(groups) == 1
        assert isinstance(groups[0], MonolingualGroup)
        assert groups[0].group_id.startswith("bypass_")

    def test_neutral_bypass(self) -> None:
        seg = _make_segment(
            "seg_1", "1.1", "neutral",
            detection_method="neutral_bypass"
        )
        groups, _ = align_segments([seg], {}, "ru")
        assert len(groups) == 1
        assert isinstance(groups[0], MonolingualGroup)
        assert groups[0].group_id.startswith("bypass_")

    def test_each_bypass_in_own_group(self) -> None:
        segments = [
            _make_segment("s1", "1.1", "neutral", detection_method="neutral_bypass"),
            _make_segment("s2", "email@x.com", "structured_data", detection_method="structured_data_bypass"),
            _make_segment("s3", "2.1", "neutral", detection_method="neutral_bypass"),
        ]
        groups, _ = align_segments(segments, {}, "ru")
        # Каждый в своей группе
        bypass_groups = [g for g in groups if g.group_id.startswith("bypass_")]
        assert len(bypass_groups) == 3


# ---------------------------------------------------------------------------
# Split from single element
# ---------------------------------------------------------------------------


class TestSplitFromSingleElement:
    def test_split_siblings_form_parallel_group(self) -> None:
        # Два сегмента из одного элемента, разные языки
        seg_en = _make_segment(
            "seg_e1_0", "English text", "en",
            source_element_id="e_original", sub_index=0
        )
        seg_ru = _make_segment(
            "seg_e1_1", "Русский текст", "ru",
            source_element_id="e_original", sub_index=1
        )
        groups, _ = align_segments([seg_en, seg_ru], {}, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 1
        assert parallel[0].alignment_confidence == 1.0
        assert "en" in parallel[0].languages
        assert "ru" in parallel[0].languages
        assert parallel[0].group_id.startswith("pair_split_")

    def test_split_siblings_ignore_unknown(self) -> None:
        # Один сегмент unknown - не должно быть пары
        seg_en = _make_segment(
            "seg_e1_0", "English", "en",
            source_element_id="e_original", sub_index=0
        )
        seg_unk = _make_segment(
            "seg_e1_1", "???", "unknown", is_reliable=False,
            source_element_id="e_original", sub_index=1
        )
        groups, _ = align_segments([seg_en, seg_unk], {}, "ru")

        # Пары не должно быть - unknown исключается
        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 0


# ---------------------------------------------------------------------------
# Anchor matching
# ---------------------------------------------------------------------------


class TestAnchorMatching:
    def test_simple_anchor_match(self) -> None:
        seg_en = _make_segment(
            "seg_1", "1.1 DEFINITIONS", "en",
            source_element_id="e_1",
            anchor_uid="1.1"
        )
        seg_ru = _make_segment(
            "seg_2", "1.1 ОПРЕДЕЛЕНИЯ", "ru",
            source_element_id="e_2",
            anchor_uid="1.1"
        )
        groups, _ = align_segments([seg_en, seg_ru], {}, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 1
        assert parallel[0].alignment_method == "structural_anchor"
        assert parallel[0].anchor_uid_normalized == ("clause", "1.1")

    def test_cross_language_appendix_match(self) -> None:
        # RU и EN appendix с одним номером - должны сматчиться
        seg_en = _make_segment(
            "seg_1", "APPENDIX No. 1", "en",
            source_element_id="e_1",
            anchor_uid="appendix-1"
        )
        seg_ru = _make_segment(
            "seg_2", "ПРИЛОЖЕНИЕ № 1", "ru",
            source_element_id="e_2",
            anchor_uid="приложение-1"
        )
        groups, _ = align_segments([seg_en, seg_ru], {}, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 1
        assert parallel[0].anchor_uid_normalized == ("appendix", "1")

    def test_scope_isolates_appendix_from_body(self) -> None:
        # Клауза "1.1" в теле договора и клауза "1.1" в Appendix 1 - НЕ пара
        seg_body_en = _make_segment(
            "seg_1", "1.1 Body EN", "en",
            source_element_id="e_1",
            anchor_uid="1.1", page=1
        )
        seg_body_ru = _make_segment(
            "seg_2", "1.1 Тело RU", "ru",
            source_element_id="e_2",
            anchor_uid="1.1", page=1
        )
        seg_app_header = _make_segment(
            "seg_3", "APPENDIX No. 1", "en",
            source_element_id="e_3",
            anchor_uid="appendix-1", page=2
        )
        seg_app_1_1_en = _make_segment(
            "seg_4", "1.1 Appendix EN", "en",
            source_element_id="e_4",
            anchor_uid="1.1", page=3
        )
        seg_app_1_1_ru = _make_segment(
            "seg_5", "1.1 Приложение RU", "ru",
            source_element_id="e_5",
            anchor_uid="1.1", page=3
        )

        segments = [seg_body_en, seg_body_ru, seg_app_header, seg_app_1_1_en, seg_app_1_1_ru]
        groups, _ = align_segments(segments, {}, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        # Ожидаем 2 пары: одна в scope "", другая в scope "appendix::1"
        assert len(parallel) == 2

        # Проверяем что scopes разные
        scopes = {g.scope for g in parallel}
        assert "" in scopes
        assert "appendix::1" in scopes


# ---------------------------------------------------------------------------
# Coordinate columns
# ---------------------------------------------------------------------------


class TestCoordinateColumns:
    def test_parallel_columns_alignment(self) -> None:
        # Два сегмента на одной странице, левая и правая колонка, разные языки
        seg_left = _make_segment(
            "s1", "English text", "en", page=3,
            bbox=BBox(50, 100, 250, 120),  # x_center=150 (левая)
        )
        seg_right = _make_segment(
            "s2", "Русский текст", "ru", page=3,
            bbox=BBox(300, 100, 500, 120),  # x_center=400 (правая)
        )

        layouts = {3: _make_page_layout(3, "parallel_columns")}
        groups, _ = align_segments([seg_left, seg_right], layouts, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 1
        assert parallel[0].alignment_method == "coordinate_columns"

    def test_same_language_not_paired_in_columns(self) -> None:
        # Оба на английском - не пара
        seg_left = _make_segment(
            "s1", "English left", "en", page=3,
            bbox=BBox(50, 100, 250, 120),
        )
        seg_right = _make_segment(
            "s2", "English right", "en", page=3,
            bbox=BBox(300, 100, 500, 120),
        )

        layouts = {3: _make_page_layout(3, "parallel_columns")}
        groups, _ = align_segments([seg_left, seg_right], layouts, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 0


# ---------------------------------------------------------------------------
# Stacked pairs
# ---------------------------------------------------------------------------


class TestStackedPairs:
    def test_stacked_pair_alignment(self) -> None:
        # EN сверху, RU сразу под ним, одинаковый X
        seg_en = _make_segment(
            "s1", "English heading", "en", page=1,
            bbox=BBox(100, 50, 400, 65),
        )
        seg_ru = _make_segment(
            "s2", "Русский заголовок", "ru", page=1,
            bbox=BBox(100, 70, 400, 85),
        )

        layouts = {1: _make_page_layout(1, "stacked_pairs")}
        groups, _ = align_segments([seg_en, seg_ru], layouts, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 1
        assert parallel[0].alignment_method == "stacked_cells"

    def test_stacked_pair_too_far_apart_no_match(self) -> None:
        # EN и RU далеко по Y - не пара
        seg_en = _make_segment(
            "s1", "English", "en", page=1,
            bbox=BBox(100, 50, 400, 65),
        )
        seg_ru = _make_segment(
            "s2", "Русский", "ru", page=1,
            bbox=BBox(100, 200, 400, 215),  # y_delta > 30pt
        )

        layouts = {1: _make_page_layout(1, "stacked_pairs")}
        groups, _ = align_segments([seg_en, seg_ru], layouts, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        assert len(parallel) == 0


# ---------------------------------------------------------------------------
# Positional sequential (stacked_blocks)
# ---------------------------------------------------------------------------


class TestPositionalSequential:
    def test_positional_pairing_two_blocks(self) -> None:
        # Титульный лист: 4 EN элемента, потом 4 RU элемента
        segments = []
        for i in range(4):
            segments.append(
                _make_segment(
                    f"en_{i}", f"English {i}", "en", page=1,
                    bbox=BBox(100, 50 + i * 20, 400, 65 + i * 20),
                )
            )
        for i in range(4):
            segments.append(
                _make_segment(
                    f"ru_{i}", f"Русский {i}", "ru", page=1,
                    bbox=BBox(100, 200 + i * 20, 400, 215 + i * 20),
                )
            )

        # Layout с block_boundaries указывает где начинается каждый блок
        layout = _make_page_layout(
            1, "stacked_blocks",
            block_boundaries=[0, 4]  # блок 0: [0:4], блок 1: [4:8]
        )
        layouts = {1: layout}
        groups, _ = align_segments(segments, layouts, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        # Ожидаем 4 пары
        assert len(parallel) == 4
        for g in parallel:
            assert g.alignment_method == "positional_sequential"


# ---------------------------------------------------------------------------
# Orphan handling
# ---------------------------------------------------------------------------


class TestOrphanHandling:
    def test_single_language_no_pair_is_orphan(self) -> None:
        seg = _make_segment("s1", "Only English here", "en", page=3)
        layouts = {3: _make_page_layout(3, "parallel_columns")}
        groups, _ = align_segments([seg], layouts, "ru")

        orphans = [g for g in groups if isinstance(g, OrphanGroup)]
        assert len(orphans) == 1
        assert orphans[0].orphan_language == "en"

    def test_monolingual_page_creates_monolingual_group(self) -> None:
        seg1 = _make_segment("s1", "Text 1", "ru", page=1)
        seg2 = _make_segment("s2", "Text 2", "ru", page=1)
        seg3 = _make_segment("s3", "Text 3", "ru", page=1)
        layouts = {1: _make_page_layout(1, "monolingual")}
        groups, _ = align_segments([seg1, seg2, seg3], layouts, "ru")

        mono = [g for g in groups if isinstance(g, MonolingualGroup) and not g.group_id.startswith("bypass_")]
        assert len(mono) == 1
        assert len(mono[0].segment_ids) == 3


# ---------------------------------------------------------------------------
# Coverage: все сегменты попадают в группы
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_all_segments_covered(self) -> None:
        # Все сегменты должны быть в какой-то группе
        segments = [
            _make_segment("s1", "EN", "en", page=1),
            _make_segment("s2", "RU", "ru", page=1),
            _make_segment("s3", "1.1", "neutral", detection_method="neutral_bypass", page=1),
            _make_segment("s4", "Русский", "ru", page=2),
        ]
        layouts = {
            1: _make_page_layout(1, "monolingual"),
            2: _make_page_layout(2, "monolingual"),
        }
        groups, _ = align_segments(segments, layouts, "ru")

        all_segment_ids: set[str] = set()
        for g in groups:
            if isinstance(g, ParallelGroup):
                all_segment_ids.update(g.all_segment_ids())
            elif isinstance(g, (OrphanGroup, MonolingualGroup)):
                all_segment_ids.update(g.segment_ids)

        expected_ids = {"s1", "s2", "s3", "s4"}
        assert all_segment_ids == expected_ids


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_gives_same_groups(self) -> None:
        segments = [
            _make_segment(
                "s1", "APPENDIX 1", "en",
                source_element_id="e1", anchor_uid="appendix-1"
            ),
            _make_segment(
                "s2", "ПРИЛОЖЕНИЕ 1", "ru",
                source_element_id="e2", anchor_uid="приложение-1"
            ),
        ]

        groups1, _ = align_segments(segments, {}, "ru")
        groups2, _ = align_segments(segments, {}, "ru")

        # Одинаковые группы
        assert len(groups1) == len(groups2)
        for g1, g2 in zip(groups1, groups2):
            assert g1.group_id == g2.group_id


# ---------------------------------------------------------------------------
# _dominant_language
# ---------------------------------------------------------------------------


class TestDominantLanguage:
    def test_all_same_language(self) -> None:
        segs = [(_make_segment(f"s{i}", "T", "ru"), "") for i in range(3)]
        assert _dominant_language(segs) == "ru"

    def test_majority_60_percent(self) -> None:
        # 3 ru, 2 en → ru dominant (60%)
        segs = [(_make_segment(f"s{i}", "T", "ru"), "") for i in range(3)]
        segs.extend([(_make_segment(f"s{i}", "T", "en"), "") for i in range(3, 5)])
        assert _dominant_language(segs) == "ru"

    def test_no_dominant_below_60_percent(self) -> None:
        # 2 ru, 2 en → нет dominant (50%)
        segs = [
            (_make_segment("s1", "T", "ru"), ""),
            (_make_segment("s2", "T", "en"), ""),
            (_make_segment("s3", "T", "ru"), ""),
            (_make_segment("s4", "T", "en"), ""),
        ]
        assert _dominant_language(segs) is None

    def test_empty_returns_none(self) -> None:
        assert _dominant_language([]) is None

    def test_unknown_ignored(self) -> None:
        segs = [
            (_make_segment("s1", "T", "ru"), ""),
            (_make_segment("s2", "T", "unknown", is_reliable=False), ""),
            (_make_segment("s3", "T", "ru"), ""),
        ]
        assert _dominant_language(segs) == "ru"


# ---------------------------------------------------------------------------
# Real document scenarios
# ---------------------------------------------------------------------------


class TestRealDocumentScenarios:
    def test_toc_entries_pair_by_anchor(self) -> None:
        # Реальные TOC entries из Simonova SPA
        segments = [
            _make_segment(
                "s_toc_en_1", "1. DEFINITIONS", "en",
                source_element_id="e_toc_en_1",
                anchor_uid="1", page=2
            ),
            _make_segment(
                "s_toc_ru_1", "1 ОПРЕДЕЛЕНИЯ", "ru",
                source_element_id="e_toc_ru_1",
                anchor_uid="1", page=2
            ),
            _make_segment(
                "s_toc_en_2", "2. SUBJECT OF THE AGREEMENT", "en",
                source_element_id="e_toc_en_2",
                anchor_uid="2", page=2
            ),
            _make_segment(
                "s_toc_ru_2", "2 ПРЕДМЕТ ДОГОВОРА", "ru",
                source_element_id="e_toc_ru_2",
                anchor_uid="2", page=2
            ),
        ]
        groups, _ = align_segments(segments, {}, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        # Должно быть 2 пары через anchor matching
        assert len(parallel) == 2

    def test_split_from_bilingual_element_pairs(self) -> None:
        # Element[43]: "APPENDIX No. 1 FORM... / ПРИЛОЖЕНИЕ № 1 ФОРМА"
        # После Layer 2 split → 2 сегмента из одного source_element_id
        seg_en = _make_segment(
            "seg_e43_0", "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE", "en",
            source_element_id="e43", sub_index=0,
            anchor_uid="appendix-1"
        )
        seg_ru = _make_segment(
            "seg_e43_1", "ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА", "ru",
            source_element_id="e43", sub_index=1,
            anchor_uid="приложение-1"
        )
        groups, _ = align_segments([seg_en, seg_ru], {}, "ru")

        parallel = [g for g in groups if isinstance(g, ParallelGroup)]
        # split_siblings имеет приоритет над anchor matching
        assert len(parallel) == 1
        assert parallel[0].alignment_confidence == 1.0
        assert parallel[0].group_id.startswith("pair_split_")



        