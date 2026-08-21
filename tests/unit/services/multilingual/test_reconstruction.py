# tests/unit/services/multilingual/test_reconstruction.py

"""
Unit тесты для Layer 6: Reconstruction.

Покрывает:
- Reading order calculation (deterministic sort)
- OutputElement assembly с metadata
- Backward compatibility с classify_elements (все базовые поля)
- Tables processing (bilingual cell split)
- Quality metrics computation
- Deterministic output
- to_monolingual_layout works after reconstruction
"""

from __future__ import annotations

import pytest

from services.multilingual.models import (
    ANALYSIS_SOURCE_KIND,
    SCHEMA_VERSION,
    BBox,
    LanguageSegment,
    MonolingualGroup,
    OrphanGroup,
    ParallelGroup,
)
from services.multilingual.reconstruction import (
    _try_split_bilingual_cell,
    reconstruct,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(
    segment_id: str,
    text: str = "Test",
    language: str = "ru",
    page: int = 1,
    top: float = 100.0,
    x0: float = 50.0,
    sub_index: int = 0,
    source_element_id: str | None = None,
    visibility: str = "visible",
    anchor_uid: str | None = None,
    is_orphan_target: bool = False,
    is_orphan_foreign: bool = False,
    is_ambiguous: bool = False,
    translation_of: list | None = None,
    translation_language: str | None = None,
    parallel_group_id: str | None = None,
    hidden_reason: str | None = None,
    orphan_display_prefix: str | None = None,
) -> LanguageSegment:
    return LanguageSegment(
        segment_id=segment_id,
        source_element_id=source_element_id or segment_id.replace("s", "e"),
        sub_index=sub_index,
        text=text,
        page=page,
        bbox=BBox(x0, top, x0 + 300, top + 20),
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
        script="cyrillic" if language == "ru" else "latin",
        detection_confidence=0.95,
        detection_method="lingua",
        is_reliable=True,
        visibility=visibility,
        hidden_reason=hidden_reason,
        translation_of=translation_of or [],
        translation_language=translation_language,
        parallel_group_id=parallel_group_id,
        is_orphan_target=is_orphan_target,
        is_orphan_foreign=is_orphan_foreign,
        is_ambiguous=is_ambiguous,
        orphan_display_prefix=orphan_display_prefix,
    )


def _make_page_layout(page: int, layout_type: str = "monolingual") -> dict:
    from services.multilingual.models import PageLayout
    return PageLayout(page=page, layout_type=layout_type)


# ---------------------------------------------------------------------------
# Basic reconstruction
# ---------------------------------------------------------------------------


class TestBasicReconstruction:
    def test_empty_input(self) -> None:
        result = reconstruct(
            segments=[], groups=[], page_layouts={},
            tables=[],
            document_id="doc_001", document_version_id="ver_001",
            target_language="ru", detected_languages=[],
            language_ratios={}, warnings=[],
        )
        assert result.elements == []
        assert result.tables == []
        assert result.schema_version == SCHEMA_VERSION

    def test_single_segment(self) -> None:
        seg = _make_segment("s1", "Русский текст", "ru")
        result = reconstruct(
            segments=[seg], groups=[], page_layouts={},
            tables=[], document_id="doc_001", document_version_id="ver_001",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )

        assert len(result.elements) == 1
        assert result.elements[0].element_id == "s1"
        assert result.elements[0].text == "Русский текст"
        assert result.elements[0].reading_order == 0


# ---------------------------------------------------------------------------
# Reading order calculation
# ---------------------------------------------------------------------------


class TestReadingOrder:
    def test_sorted_by_page_top_x0(self) -> None:
        # Разные страницы, разные позиции
        segs = [
            _make_segment("s3", page=2, top=100, x0=50),
            _make_segment("s1", page=1, top=100, x0=50),
            _make_segment("s2", page=1, top=200, x0=50),
        ]
        result = reconstruct(
            segments=segs, groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )

        # Порядок: s1 (page1 top100), s2 (page1 top200), s3 (page2)
        assert result.elements[0].element_id == "s1"
        assert result.elements[1].element_id == "s2"
        assert result.elements[2].element_id == "s3"

        # reading_order сквозной
        assert result.elements[0].reading_order == 0
        assert result.elements[1].reading_order == 1
        assert result.elements[2].reading_order == 2

    def test_split_siblings_ordered_by_sub_index(self) -> None:
        # Два split-siblings с одинаковым top но разным sub_index
        seg1 = _make_segment("s_en", page=1, top=100, x0=50, sub_index=0)
        seg2 = _make_segment("s_ru", page=1, top=100, x0=350, sub_index=1)

        result = reconstruct(
            segments=[seg2, seg1],  # передаём в обратном порядке
            groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru", "en"],
            language_ratios={"ru": 0.5, "en": 0.5}, warnings=[],
        )

        # Sort по x0: s_en (x0=50) первый, s_ru (x0=350) второй
        assert result.elements[0].element_id == "s_en"
        assert result.elements[1].element_id == "s_ru"


# ---------------------------------------------------------------------------
# OutputElement backward compatibility
# ---------------------------------------------------------------------------


class TestOutputElementBackwardCompatibility:
    def test_has_all_base_fields(self) -> None:
        # OutputElement должен иметь все поля existing raw layout element
        seg = _make_segment("s1", "Text", "ru")
        result = reconstruct(
            segments=[seg], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )
        el = result.elements[0]

        # Базовые поля для classify_elements
        assert el.element_id == "s1"
        assert el.type == "text"
        assert el.text == "Text"
        assert el.page == 1
        assert isinstance(el.bbox, list)
        assert len(el.bbox) == 4
        assert el.confidence == 1.0
        assert el.clause_uid is None
        assert isinstance(el.reading_order, int)

    def test_metadata_contains_multilingual_fields(self) -> None:
        seg = _make_segment("s1", "Text", "ru", visibility="visible")
        result = reconstruct(
            segments=[seg], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )
        meta = result.elements[0].metadata

        # Проверяем ключевые multilingual поля
        assert "language" in meta
        assert meta["language"] == "ru"
        assert "visibility_in_target_language" in meta
        assert meta["visibility_in_target_language"] == "visible"
        assert "source_element_id" in meta
        assert "sub_index" in meta

    def test_hidden_segment_has_translation_context(self) -> None:
        seg = _make_segment(
            "s_en", "English", "en", visibility="hidden",
            translation_of=["s_ru"], translation_language="ru",
            hidden_reason="parallel_translation_available",
            parallel_group_id="pair_001",
        )
        seg.translation_pair_confidence = 0.95

        result = reconstruct(
            segments=[seg], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru", "en"],
            language_ratios={"ru": 0.5, "en": 0.5}, warnings=[],
        )
        meta = result.elements[0].metadata

        assert meta["hidden_reason"] == "parallel_translation_available"
        assert meta["translation_of"] == ["s_ru"]
        assert meta["translation_language"] == "ru"
        assert meta["translation_pair_confidence"] == 0.95
        assert meta["parallel_group_id"] == "pair_001"

    def test_orphan_foreign_has_display_prefix(self) -> None:
        seg = _make_segment(
            "s1", "English", "en",
            visibility="visible_orphan_foreign",
            is_orphan_foreign=True,
            orphan_display_prefix="[БЕЗ ПЕРЕВОДА]",
        )
        result = reconstruct(
            segments=[seg], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru", "en"],
            language_ratios={"ru": 0.5, "en": 0.5}, warnings=[],
        )
        meta = result.elements[0].metadata

        assert meta["is_orphan_foreign"] is True
        assert meta["orphan_display_prefix"] == "[БЕЗ ПЕРЕВОДА]"


# ---------------------------------------------------------------------------
# Tables processing
# ---------------------------------------------------------------------------


class TestTablesProcessing:
    def test_bilingual_cell_split_backslash(self) -> None:
        # Из real Simonova SPA: "Земельный участок ... \\ Land plot..."
        cell_text = "Земельный участок \\ Land plot"
        result = _try_split_bilingual_cell(cell_text)

        assert result is not None
        assert result["separator"] == "\\"
        assert len(result["split_parts"]) == 2
        assert result["split_parts"][0]["language"] == "ru"
        assert result["split_parts"][1]["language"] == "en"

    def test_bilingual_cell_split_slash(self) -> None:
        cell_text = "Приложение / Appendix"
        result = _try_split_bilingual_cell(cell_text)

        assert result is not None
        assert result["separator"] == "/"

    def test_no_separator_not_bilingual(self) -> None:
        assert _try_split_bilingual_cell("Just Russian text") is None

    def test_same_script_not_bilingual(self) -> None:
        # "path / to" - оба latin, не bilingual
        assert _try_split_bilingual_cell("path / to") is None

    def test_table_with_bilingual_cells(self) -> None:
        tables = [{
            "page": 28,
            "rows": [
                ["№", "Объекты \\ Objects", "Стоимость"],
                ["1", "Земельный участок \\ Land plot", "500 000"],
            ],
        }]
        result = reconstruct(
            segments=[], groups=[], page_layouts={},
            tables=tables, document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru", "en"],
            language_ratios={"ru": 0.5, "en": 0.5}, warnings=[],
        )

        assert len(result.tables) == 1
        assert "bilingual_cells" in result.tables[0]
        # Ячейки [0][1] и [1][1] bilingual
        assert "0,1" in result.tables[0]["bilingual_cells"]
        assert "1,1" in result.tables[0]["bilingual_cells"]


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------


class TestQualityMetrics:
    def test_parallel_groups_counted(self) -> None:
        seg_en = _make_segment("s_en", "en", visibility="hidden")
        seg_ru = _make_segment("s_ru", "ru", visibility="visible")

        group = ParallelGroup(
            group_id="p1", page=1,
            segments_by_language={"en": ["s_en"], "ru": ["s_ru"]},
            alignment_confidence=0.9,
            alignment_method="structural_anchor",
        )
        result = reconstruct(
            segments=[seg_en, seg_ru], groups=[group], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru", "en"],
            language_ratios={"ru": 0.5, "en": 0.5}, warnings=[],
        )

        assert result.metadata.quality_metrics.parallel_groups_count == 1
        assert result.metadata.quality_metrics.orphan_groups_count == 0

    def test_purity_precision_all_target(self) -> None:
        # Все visible на target -> precision = 1.0
        seg_ru = _make_segment("s1", "ru", visibility="visible")
        result = reconstruct(
            segments=[seg_ru], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )
        assert result.metadata.quality_metrics.language_purity_precision == 1.0

    def test_alignment_method_breakdown(self) -> None:
        seg_en1 = _make_segment("s_en_1", "en", visibility="hidden")
        seg_ru1 = _make_segment("s_ru_1", "ru", visibility="visible")
        seg_en2 = _make_segment("s_en_2", "en", visibility="hidden")
        seg_ru2 = _make_segment("s_ru_2", "ru", visibility="visible")

        groups = [
            ParallelGroup(
                group_id="p1", page=1,
                segments_by_language={"en": ["s_en_1"], "ru": ["s_ru_1"]},
                alignment_method="structural_anchor",
            ),
            ParallelGroup(
                group_id="p2", page=1,
                segments_by_language={"en": ["s_en_2"], "ru": ["s_ru_2"]},
                alignment_method="coordinate_columns",
            ),
        ]
        result = reconstruct(
            segments=[seg_en1, seg_ru1, seg_en2, seg_ru2], groups=groups,
            page_layouts={}, tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru", "en"],
            language_ratios={"ru": 0.5, "en": 0.5}, warnings=[],
        )

        methods = result.metadata.quality_metrics.alignments_by_method
        assert methods["structural_anchor"] == 1
        assert methods["coordinate_columns"] == 1


# ---------------------------------------------------------------------------
# to_monolingual_layout after reconstruction
# ---------------------------------------------------------------------------


class TestToMonolingualLayout:
    def test_monolingual_layout_excludes_hidden(self) -> None:
        seg_en = _make_segment("s_en", "en", visibility="hidden")
        seg_ru = _make_segment("s_ru", "ru", visibility="visible")

        result = reconstruct(
            segments=[seg_en, seg_ru], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru", "en"],
            language_ratios={"ru": 0.5, "en": 0.5}, warnings=[],
        )

        mono = result.to_monolingual_layout()
        assert len(mono["elements"]) == 1
        assert mono["elements"][0]["element_id"] == "s_ru"

    def test_monolingual_layout_has_analysis_source_kind(self) -> None:
        seg = _make_segment("s1", "ru")
        result = reconstruct(
            segments=[seg], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )

        mono = result.to_monolingual_layout()
        assert (
            mono["metadata"]["language_filter"]["analysis_source_kind"]
            == ANALYSIS_SOURCE_KIND
        )


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        seg1 = _make_segment("s1", "Text 1", "ru", page=1, top=100)
        seg2 = _make_segment("s2", "Text 2", "ru", page=1, top=200)

        result1 = reconstruct(
            segments=[seg1, seg2], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )
        result2 = reconstruct(
            segments=[seg2, seg1],  # обратный порядок
            groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )

        # Оба результата идентичны после сортировки
        assert [e.element_id for e in result1.elements] == [e.element_id for e in result2.elements]

    def test_to_dict_deterministic(self) -> None:
        seg = _make_segment("s1", "ru")
        result = reconstruct(
            segments=[seg], groups=[], page_layouts={},
            tables=[], document_id="d", document_version_id="v",
            target_language="ru", detected_languages=["ru"],
            language_ratios={"ru": 1.0}, warnings=[],
        )

        # to_dict должен быть JSON-serializable
        import json
        json_str = json.dumps(result.to_dict(), ensure_ascii=False)
        assert "s1" in json_str
        assert SCHEMA_VERSION in json_str



        