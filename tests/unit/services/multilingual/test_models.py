# tests/unit/services/multilingual/test_models.py

"""
Unit тесты для models.py v3.

Покрывает:
- BBox: создание, нормализация, from_list, to_list, свойства
- NormalizationHints: needs_split, all_split_positions
- LanguageSegment: дефолты, is_bypass, инварианты полей
- PageLayout: все типы, block_boundaries
- ParallelGroup: languages sorted, all_segment_ids
- OrphanGroup, MonolingualGroup: базовые поля
- QualityMetrics: compute для граничных значений
- ProcessingWarning, ProcessingTrace
- PipelineMetadata: to_dict deterministic
- PipelineResult: get_visible/hidden, to_monolingual_layout, to_dict
"""

from __future__ import annotations

import pytest

from services.multilingual.models import (
    ANALYSIS_SOURCE_KIND,
    SCHEMA_VERSION,
    BBox,
    MonolingualGroup,
    NormalizationHints,
    OrphanGroup,
    OutputElement,
    PageLayout,
    ParallelGroup,
    PipelineMetadata,
    PipelineResult,
    ProcessingTrace,
    ProcessingWarning,
    QualityMetrics,
    LanguageSegment,
)


# ---------------------------------------------------------------------------
# BBox
# ---------------------------------------------------------------------------


class TestBBox:
    def test_normal_creation(self) -> None:
        bbox = BBox(x0=10.0, top=20.0, x1=100.0, bottom=80.0)
        assert bbox.x0 == 10.0
        assert bbox.top == 20.0
        assert bbox.x1 == 100.0
        assert bbox.bottom == 80.0

    def test_inverted_x_normalized(self) -> None:
        bbox = BBox(x0=100.0, top=20.0, x1=10.0, bottom=80.0)
        assert bbox.x0 == 10.0
        assert bbox.x1 == 100.0

    def test_inverted_y_normalized(self) -> None:
        bbox = BBox(x0=10.0, top=80.0, x1=100.0, bottom=20.0)
        assert bbox.top == 20.0
        assert bbox.bottom == 80.0

    def test_from_list_normal(self) -> None:
        bbox = BBox.from_list([10.0, 20.0, 100.0, 80.0])
        assert bbox.to_list() == [10.0, 20.0, 100.0, 80.0]

    def test_from_list_none_returns_zero(self) -> None:
        bbox = BBox.from_list(None)
        assert bbox.is_zero

    def test_from_list_empty_returns_zero(self) -> None:
        assert BBox.from_list([]).is_zero

    def test_from_list_too_short_returns_zero(self) -> None:
        assert BBox.from_list([1.0, 2.0]).is_zero

    def test_from_list_invalid_values_become_zero(self) -> None:
        bbox = BBox.from_list([10.0, "bad", 100.0, 80.0])
        assert bbox.top == 0.0
        assert bbox.x0 == 10.0

    def test_from_list_string_numbers(self) -> None:
        bbox = BBox.from_list(["10.5", "20.5", "100.5", "80.5"])
        assert bbox.x0 == 10.5

    def test_to_list_returns_list(self) -> None:
        bbox = BBox(10.0, 20.0, 100.0, 80.0)
        assert isinstance(bbox.to_list(), list)

    def test_y_center(self) -> None:
        bbox = BBox(0.0, 20.0, 100.0, 80.0)
        assert bbox.y_center == pytest.approx(50.0)

    def test_x_center(self) -> None:
        bbox = BBox(10.0, 0.0, 110.0, 50.0)
        assert bbox.x_center == pytest.approx(60.0)

    def test_width_height(self) -> None:
        bbox = BBox(10.0, 20.0, 60.0, 70.0)
        assert bbox.width == pytest.approx(50.0)
        assert bbox.height == pytest.approx(50.0)

    def test_is_zero_true(self) -> None:
        assert BBox(0.0, 0.0, 0.0, 0.0).is_zero

    def test_is_zero_false(self) -> None:
        assert not BBox(0.0, 0.0, 10.0, 10.0).is_zero

    def test_frozen_immutability(self) -> None:
        bbox = BBox(10.0, 20.0, 100.0, 80.0)
        with pytest.raises((AttributeError, TypeError)):
            bbox.x0 = 999.0  # type: ignore[misc]

    def test_from_list_extra_values_ignored(self) -> None:
        bbox = BBox.from_list([10.0, 20.0, 100.0, 80.0, 999.0])
        assert bbox.to_list() == [10.0, 20.0, 100.0, 80.0]


# ---------------------------------------------------------------------------
# NormalizationHints
# ---------------------------------------------------------------------------


class TestNormalizationHints:
    def _make(self, **overrides) -> NormalizationHints:
        defaults = {
            "source_element_id": "e_test",
            "script_boundary_detected": False,
            "script_boundary_positions": (),
            "explicit_separator_detected": None,
            "explicit_separator_positions": (),
            "digit_letter_boundary_detected": False,
            "digit_letter_boundary_positions": (),
            "is_table_cell": False,
            "cell_position": None,
            "has_zero_width_chars": False,
            "cleaned_text": "test text",
        }
        defaults.update(overrides)
        return NormalizationHints(**defaults)

    def test_needs_split_false_default(self) -> None:
        assert not self._make().needs_split

    def test_needs_split_true_on_script_boundary(self) -> None:
        hints = self._make(
            script_boundary_detected=True,
            script_boundary_positions=(9,),
        )
        assert hints.needs_split

    def test_needs_split_true_on_separator(self) -> None:
        hints = self._make(
            explicit_separator_detected="/",
            explicit_separator_positions=(15,),
        )
        assert hints.needs_split

    def test_needs_split_true_on_digit_letter(self) -> None:
        hints = self._make(
            digit_letter_boundary_detected=True,
            digit_letter_boundary_positions=(3,),
        )
        assert hints.needs_split

    def test_all_split_positions_sorted_deduplicated(self) -> None:
        hints = self._make(
            script_boundary_detected=True,
            script_boundary_positions=(15, 30),
            explicit_separator_detected="/",
            explicit_separator_positions=(15, 45),
            digit_letter_boundary_detected=True,
            digit_letter_boundary_positions=(30,),
        )
        # 15 и 30 повторяются → должны быть дедуплицированы
        assert hints.all_split_positions == (15, 30, 45)

    def test_all_split_positions_empty(self) -> None:
        assert self._make().all_split_positions == ()

    def test_frozen(self) -> None:
        hints = self._make()
        with pytest.raises((AttributeError, TypeError)):
            hints.script_boundary_detected = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LanguageSegment
# ---------------------------------------------------------------------------


class TestLanguageSegment:
    def _make(self, **overrides) -> LanguageSegment:
        defaults = {
            "segment_id": "seg_e123_0",
            "source_element_id": "e123",
            "sub_index": 0,
            "text": "Договор купли-продажи",
            "page": 1,
            "bbox": BBox(10.0, 20.0, 400.0, 40.0),
            "bbox_is_approximate": False,
            "bbox_split_method": "original",
            "reading_order_raw": 0,
            "anchor_uid": None,
            "is_table_cell": False,
            "cell_position": None,
            "source_element_type": "text",
            "split_reason": "none",
            "split_confidence": 1.0,
        }
        defaults.update(overrides)
        return LanguageSegment(**defaults)

    def test_default_language_fields(self) -> None:
        seg = self._make()
        assert seg.language == "unknown"
        assert seg.script == "other"
        assert seg.detection_confidence == 0.0
        assert not seg.is_reliable

    def test_default_visibility_fields(self) -> None:
        seg = self._make()
        assert seg.visibility == "visible"
        assert seg.hidden_reason is None
        assert seg.translation_of == []
        assert seg.translation_pair_confidence is None
        assert seg.translation_language is None
        assert seg.parallel_group_id is None
        assert not seg.is_orphan_target
        assert not seg.is_orphan_foreign
        assert not seg.is_ambiguous

    def test_is_bypass_structured_data(self) -> None:
        seg = self._make()
        seg.language = "structured_data"
        assert seg.is_bypass()

    def test_is_bypass_neutral(self) -> None:
        seg = self._make()
        seg.language = "neutral"
        assert seg.is_bypass()

    def test_is_not_bypass_regular_language(self) -> None:
        seg = self._make()
        seg.language = "ru"
        assert not seg.is_bypass()

    def test_is_not_bypass_unknown(self) -> None:
        seg = self._make()
        seg.language = "unknown"
        assert not seg.is_bypass()

    def test_is_not_bypass_mixed(self) -> None:
        seg = self._make()
        seg.language = "mixed"
        assert not seg.is_bypass()

    def test_segment_key_equals_segment_id(self) -> None:
        seg = self._make(segment_id="seg_abc_1")
        assert seg.segment_key == "seg_abc_1"

    def test_language_can_be_mutated_by_layer3(self) -> None:
        seg = self._make()
        seg.language = "ru"
        seg.script = "cyrillic"
        seg.detection_confidence = 0.97
        assert seg.language == "ru"

    def test_visibility_can_be_mutated_by_layer5(self) -> None:
        seg = self._make()
        seg.visibility = "hidden"
        seg.hidden_reason = "parallel_translation_available"
        seg.translation_of = ["seg_xyz_0"]
        seg.translation_pair_confidence = 0.95
        seg.translation_language = "en"
        assert seg.visibility == "hidden"

    def test_bbox_original_not_approximate(self) -> None:
        seg = self._make(
            bbox_is_approximate=False,
            bbox_split_method="original",
            split_reason="none",
        )
        assert not seg.bbox_is_approximate
        assert seg.bbox_split_method == "original"

    def test_bbox_split_is_approximate(self) -> None:
        seg = self._make(
            bbox_is_approximate=True,
            bbox_split_method="proportional",
            split_reason="script_boundary",
            sub_index=1,
        )
        assert seg.bbox_is_approximate
        assert seg.bbox_split_method == "proportional"


# ---------------------------------------------------------------------------
# PageLayout
# ---------------------------------------------------------------------------


class TestPageLayout:
    def test_basic_creation(self) -> None:
        layout = PageLayout(page=1, layout_type="parallel_columns")
        assert layout.page == 1
        assert layout.layout_type == "parallel_columns"
        assert layout.left_column_x_range is None
        assert layout.right_column_x_range is None
        assert layout.interleave_languages == []
        assert layout.block_boundaries == []
        assert layout.confidence == 1.0

    def test_with_column_ranges(self) -> None:
        layout = PageLayout(
            page=2,
            layout_type="parallel_columns",
            left_column_x_range=(10.0, 290.0),
            right_column_x_range=(310.0, 580.0),
        )
        assert layout.left_column_x_range == (10.0, 290.0)

    def test_interleaved_with_languages(self) -> None:
        layout = PageLayout(
            page=3,
            layout_type="interleaved_lines",
            interleave_languages=["en", "ru"],
        )
        assert layout.interleave_languages == ["en", "ru"]

    def test_stacked_blocks_with_boundaries(self) -> None:
        layout = PageLayout(
            page=1,
            layout_type="stacked_blocks",
            block_boundaries=[0, 14],
        )
        assert layout.block_boundaries == [0, 14]

    def test_empty_page(self) -> None:
        layout = PageLayout(page=24, layout_type="empty")
        assert layout.layout_type == "empty"

    def test_table_page(self) -> None:
        layout = PageLayout(page=28, layout_type="table_page")
        assert layout.layout_type == "table_page"


# ---------------------------------------------------------------------------
# ParallelGroup
# ---------------------------------------------------------------------------


class TestParallelGroup:
    def test_group_type_fixed(self) -> None:
        group = ParallelGroup(group_id="pair_001", page=1)
        assert group.group_type == "parallel_pair"

    def test_languages_returned_sorted(self) -> None:
        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={"ru": ["seg_b"], "en": ["seg_a"]},
        )
        # Должны вернуться отсортированными
        assert group.languages == ["en", "ru"]

    def test_get_segment_ids_existing(self) -> None:
        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={"en": ["seg_a_0", "seg_a_1"]},
        )
        assert group.get_segment_ids("en") == ["seg_a_0", "seg_a_1"]

    def test_get_segment_ids_missing(self) -> None:
        group = ParallelGroup(group_id="pair_001", page=1)
        assert group.get_segment_ids("ru") == []

    def test_all_segment_ids_sorted(self) -> None:
        group = ParallelGroup(
            group_id="pair_001",
            page=1,
            segments_by_language={
                "en": ["seg_z", "seg_a"],
                "ru": ["seg_m"],
            },
        )
        assert group.all_segment_ids() == ["seg_a", "seg_m", "seg_z"]

    def test_default_alignment_method(self) -> None:
        assert ParallelGroup(group_id="p1", page=1).alignment_method == "structural_anchor"

    def test_scope_default_empty(self) -> None:
        assert ParallelGroup(group_id="p1", page=1).scope == ""

    def test_anchor_uid_normalized_optional(self) -> None:
        group = ParallelGroup(
            group_id="p1",
            page=1,
            anchor_uid_normalized=("clause", "1.1"),
        )
        assert group.anchor_uid_normalized == ("clause", "1.1")


# ---------------------------------------------------------------------------
# OrphanGroup
# ---------------------------------------------------------------------------


class TestOrphanGroup:
    def test_group_type_fixed(self) -> None:
        group = OrphanGroup(group_id="orp_1", page=1)
        assert group.group_type == "orphan"

    def test_default_reason(self) -> None:
        assert OrphanGroup(group_id="orp_1", page=1).orphan_reason == "no_pair_found"

    def test_default_language(self) -> None:
        assert OrphanGroup(group_id="orp_1", page=1).orphan_language == "unknown"

    def test_scope_default(self) -> None:
        assert OrphanGroup(group_id="orp_1", page=1).scope == ""


# ---------------------------------------------------------------------------
# MonolingualGroup
# ---------------------------------------------------------------------------


class TestMonolingualGroup:
    def test_group_type_fixed(self) -> None:
        group = MonolingualGroup(group_id="mono_1", page=1)
        assert group.group_type == "monolingual"

    def test_scope_default(self) -> None:
        assert MonolingualGroup(group_id="mono_1", page=1).scope == ""


# ---------------------------------------------------------------------------
# QualityMetrics
# ---------------------------------------------------------------------------


class TestQualityMetrics:
    def test_orphan_ratio_normal(self) -> None:
        qm = QualityMetrics(parallel_groups_count=8, orphan_groups_count=2)
        qm.compute()
        assert qm.orphan_ratio == pytest.approx(0.2)

    def test_orphan_ratio_zero_orphans(self) -> None:
        qm = QualityMetrics(parallel_groups_count=10, orphan_groups_count=0)
        qm.compute()
        assert qm.orphan_ratio == 0.0

    def test_orphan_ratio_no_groups(self) -> None:
        qm = QualityMetrics()
        qm.compute()
        assert qm.orphan_ratio == 0.0

    def test_orphan_ratio_monolingual_not_counted(self) -> None:
        qm = QualityMetrics(
            parallel_groups_count=8,
            orphan_groups_count=2,
            monolingual_groups_count=100,  # не влияет
        )
        qm.compute()
        assert qm.orphan_ratio == pytest.approx(0.2)

    def test_purity_precision(self) -> None:
        qm = QualityMetrics(
            visible_segments_count=100,
            target_language_segments_visible=95,
        )
        qm.compute()
        assert qm.language_purity_precision == pytest.approx(0.95)

    def test_purity_precision_zero_visible(self) -> None:
        qm = QualityMetrics(visible_segments_count=0)
        qm.compute()
        assert qm.language_purity_precision == 0.0

    def test_purity_recall(self) -> None:
        qm = QualityMetrics(
            target_language_segments_visible=90,
            total_target_segments_in_document=100,
        )
        qm.compute()
        assert qm.language_purity_recall == pytest.approx(0.9)

    def test_structural_fidelity_full(self) -> None:
        qm = QualityMetrics(expected_clause_count=10, found_clause_count=10)
        qm.compute()
        assert qm.structural_fidelity == pytest.approx(1.0)

    def test_structural_fidelity_partial(self) -> None:
        qm = QualityMetrics(expected_clause_count=10, found_clause_count=9)
        qm.compute()
        assert qm.structural_fidelity == pytest.approx(0.9)

    def test_structural_fidelity_no_clauses(self) -> None:
        qm = QualityMetrics(expected_clause_count=0)
        qm.compute()
        assert qm.structural_fidelity == 1.0

    def test_alignments_by_method_default_empty(self) -> None:
        qm = QualityMetrics()
        assert qm.alignments_by_method == {}

    def test_split_diagnostics_defaults(self) -> None:
        qm = QualityMetrics()
        assert qm.segments_split == 0
        assert qm.avg_split_confidence == 1.0
        assert qm.low_confidence_splits_count == 0


# ---------------------------------------------------------------------------
# ProcessingWarning + Trace
# ---------------------------------------------------------------------------


class TestProcessingWarning:
    def test_creation(self) -> None:
        w = ProcessingWarning(
            warning_type="low_split_confidence",
            element_id="e123",
            page=5,
            details={"confidence": 0.55, "note": "short segments"},
        )
        assert w.warning_type == "low_split_confidence"
        assert w.element_id == "e123"

    def test_defaults(self) -> None:
        w = ProcessingWarning(warning_type="empty_page")
        assert w.element_id is None
        assert w.page is None
        assert w.details == {}


class TestProcessingTrace:
    def test_defaults(self) -> None:
        trace = ProcessingTrace()
        assert trace.schema_version == SCHEMA_VERSION
        assert trace.analysis_source_kind == ANALYSIS_SOURCE_KIND
        assert trace.pipeline_version == "1.0.0"
        assert trace.warnings == []
        assert trace.total_seconds == 0.0

    def test_warnings_can_be_appended(self) -> None:
        trace = ProcessingTrace()
        trace.warnings.append(ProcessingWarning(warning_type="empty_page", page=24))
        assert len(trace.warnings) == 1


# ---------------------------------------------------------------------------
# PipelineMetadata
# ---------------------------------------------------------------------------


class TestPipelineMetadata:
    def test_language_filter_defaults(self) -> None:
        meta = PipelineMetadata()
        assert meta.language_filter["analysis_source_kind"] == ANALYSIS_SOURCE_KIND
        assert meta.language_filter["contract_version"] == 2
        assert meta.language_filter["downstream_requires_primary_source"] is False

    def test_to_dict_contains_all_keys(self) -> None:
        meta = PipelineMetadata(
            detected_languages=["ru", "en"],
            target_language="ru",
        )
        d = meta.to_dict()
        assert "detected_languages" in d
        assert "target_language" in d
        assert "is_multilingual" in d
        assert "language_ratios" in d
        assert "target_language_ratio" in d
        assert "layout_type_summary" in d
        assert "quality_metrics" in d
        assert "processing_trace" in d
        assert "language_filter" in d

    def test_to_dict_detected_languages_sorted(self) -> None:
        meta = PipelineMetadata(detected_languages=["ru", "en", "ar"])
        d = meta.to_dict()
        assert d["detected_languages"] == ["ar", "en", "ru"]

    def test_to_dict_language_ratios_sorted(self) -> None:
        meta = PipelineMetadata(language_ratios={"ru": 0.6, "en": 0.4})
        d = meta.to_dict()
        keys = list(d["language_ratios"].keys())
        assert keys == sorted(keys)

    def test_to_dict_layout_summary_string_keys(self) -> None:
        meta = PipelineMetadata(
            layout_type_summary={1: "parallel_columns", 2: "monolingual"},
        )
        d = meta.to_dict()
        assert "1" in d["layout_type_summary"]
        assert "2" in d["layout_type_summary"]

    def test_to_dict_warnings_serialized(self) -> None:
        meta = PipelineMetadata()
        meta.processing_trace.warnings.append(
            ProcessingWarning(warning_type="empty_page", page=24)
        )
        d = meta.to_dict()
        warnings = d["processing_trace"]["warnings"]
        assert len(warnings) == 1
        assert warnings[0]["warning_type"] == "empty_page"
        assert warnings[0]["page"] == 24


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------


def _make_output_element(
    element_id: str = "seg_001",
    text: str = "Тестовый текст",
    visibility: str = "visible",
    language: str = "ru",
    reading_order: int = 0,
) -> OutputElement:
    metadata = {
        "language": language,
        "language_confidence": 0.98,
        "script": "cyrillic" if language == "ru" else "latin",
        "detection_method": "lingua",
        "visibility_in_target_language": visibility,
        "source_element_id": "e_001",
        "sub_index": 0,
        "split_reason": "none",
        "split_confidence": 1.0,
        "bbox_is_approximate": False,
        "bbox_split_method": "original",
    }
    if visibility == "hidden":
        metadata["hidden_reason"] = "parallel_translation_available"
        metadata["translation_of"] = ["seg_partner"]
        metadata["translation_pair_confidence"] = 0.95
        metadata["translation_language"] = "en" if language == "ru" else "ru"
        metadata["parallel_group_id"] = "pair_001"

    return OutputElement(
        element_id=element_id,
        type="text",
        text=text,
        page=1,
        bbox=[10.0, 20.0, 400.0, 40.0],
        confidence=1.0,
        clause_uid=None,
        reading_order=reading_order,
        metadata=metadata,
    )


class TestPipelineResult:
    def test_get_visible_elements(self) -> None:
        result = PipelineResult(
            document_id="doc_001",
            elements=[
                _make_output_element("seg_001", visibility="visible"),
                _make_output_element("seg_002", visibility="hidden"),
                _make_output_element("seg_003", visibility="visible_orphan_target"),
                _make_output_element("seg_004", visibility="visible_orphan_foreign"),
            ],
        )
        visible = result.get_visible_elements()
        assert len(visible) == 3
        visible_ids = {el.element_id for el in visible}
        assert "seg_002" not in visible_ids

    def test_get_hidden_elements(self) -> None:
        result = PipelineResult(
            document_id="doc_001",
            elements=[
                _make_output_element("seg_001", visibility="visible"),
                _make_output_element("seg_002", visibility="hidden"),
                _make_output_element("seg_003", visibility="hidden"),
            ],
        )
        hidden = result.get_hidden_elements()
        assert len(hidden) == 2

    def test_to_monolingual_layout_excludes_hidden(self) -> None:
        result = PipelineResult(
            document_id="doc_001",
            document_version_id="ver_001",
            elements=[
                _make_output_element("seg_001", visibility="visible"),
                _make_output_element("seg_002", visibility="hidden"),
            ],
        )
        mono = result.to_monolingual_layout()
        assert len(mono["elements"]) == 1
        assert mono["elements"][0]["element_id"] == "seg_001"

    def test_to_monolingual_layout_has_required_fields(self) -> None:
        result = PipelineResult(
            document_id="doc_001",
            document_version_id="ver_001",
            elements=[_make_output_element("seg_001")],
        )
        mono = result.to_monolingual_layout()
        assert mono["document_id"] == "doc_001"
        assert mono["document_version_id"] == "ver_001"
        assert "elements" in mono
        assert "tables" in mono
        assert "metadata" in mono

    def test_to_monolingual_element_has_all_required_fields(self) -> None:
        # Проверяем что элемент monolingual layout совместим с classify_elements
        result = PipelineResult(
            document_id="doc_001",
            elements=[_make_output_element("seg_001")],
        )
        mono = result.to_monolingual_layout()
        el = mono["elements"][0]
        for required in ("element_id", "type", "text", "page", "bbox",
                          "confidence", "clause_uid", "reading_order"):
            assert required in el, f"Missing: {required}"

    def test_to_dict_includes_hidden(self) -> None:
        # Полный to_dict — visible + hidden
        result = PipelineResult(
            document_id="doc_001",
            elements=[
                _make_output_element("seg_001", visibility="visible"),
                _make_output_element("seg_002", visibility="hidden"),
            ],
        )
        d = result.to_dict()
        assert len(d["elements"]) == 2

    def test_to_dict_schema_version(self) -> None:
        result = PipelineResult(document_id="doc_001")
        assert result.to_dict()["schema_version"] == SCHEMA_VERSION

    def test_to_dict_analysis_source_kind(self) -> None:
        result = PipelineResult(document_id="doc_001")
        d = result.to_dict()
        assert (
            d["metadata"]["language_filter"]["analysis_source_kind"]
            == ANALYSIS_SOURCE_KIND
        )

    def test_to_dict_detected_languages_sorted(self) -> None:
        result = PipelineResult(
            document_id="doc_001",
            detected_languages=["ru", "en", "ar"],
        )
        d = result.to_dict()
        assert d["detected_languages"] == ["ar", "en", "ru"]

    def test_to_dict_empty_result(self) -> None:
        result = PipelineResult()
        d = result.to_dict()
        assert d["elements"] == []
        assert d["tables"] == []

    def test_tables_included_in_output(self) -> None:
        tables = [{"page": 28, "rows": [["A", "B"]]}]
        result = PipelineResult(document_id="doc_001", tables=tables)
        d = result.to_dict()
        assert d["tables"] == tables

    def test_hidden_element_has_translation_context(self) -> None:
        hidden_el = _make_output_element("seg_002", visibility="hidden", language="en")
        result = PipelineResult(document_id="doc_001", elements=[hidden_el])
        d = result.to_dict()
        el = d["elements"][0]
        assert el["metadata"]["hidden_reason"] == "parallel_translation_available"
        assert el["metadata"]["translation_of"] == ["seg_partner"]
        assert el["metadata"]["translation_pair_confidence"] == 0.95
        assert el["metadata"]["translation_language"] == "ru"
        assert el["metadata"]["parallel_group_id"] == "pair_001"


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """
    Тесты гарантии что один и тот же input → идентичный output.
    Критично для reproducibility, тестов, дифф-анализа.
    """

    def test_pipeline_metadata_to_dict_deterministic(self) -> None:
        meta1 = PipelineMetadata(
            detected_languages=["en", "ru"],
            language_ratios={"ru": 0.6, "en": 0.4},
        )
        meta2 = PipelineMetadata(
            detected_languages=["ru", "en"],  # другой порядок
            language_ratios={"en": 0.4, "ru": 0.6},  # другой порядок
        )
        assert meta1.to_dict() == meta2.to_dict()

    def test_parallel_group_languages_deterministic(self) -> None:
        g1 = ParallelGroup(
            group_id="p1",
            page=1,
            segments_by_language={"en": ["s1"], "ru": ["s2"]},
        )
        g2 = ParallelGroup(
            group_id="p1",
            page=1,
            segments_by_language={"ru": ["s2"], "en": ["s1"]},
        )
        assert g1.languages == g2.languages

    def test_pipeline_result_to_dict_deterministic(self) -> None:
        el1 = _make_output_element("seg_001")
        el2 = _make_output_element("seg_002")
        r1 = PipelineResult(
            document_id="doc",
            detected_languages=["en", "ru"],
            elements=[el1, el2],
        )
        r2 = PipelineResult(
            document_id="doc",
            detected_languages=["ru", "en"],
            elements=[el1, el2],
        )
        assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_schema_version_value(self) -> None:
        assert SCHEMA_VERSION == "primary_layout/v2"

    def test_analysis_source_kind_value(self) -> None:
        assert ANALYSIS_SOURCE_KIND == "canonical_filtered_layout_v2"



        