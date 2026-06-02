from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import services.structure.pipeline as pipeline


class _FakeFileStructureResult:
    def __init__(
        self,
        *,
        primary_tree,
        segment_trees,
        file_graph,
        coherence_result=None,
    ):
        self.primary_tree = primary_tree
        self.segment_trees = segment_trees
        self.file_graph = file_graph
        self.coherence_result = coherence_result


def _make_segment() -> SimpleNamespace:
    return SimpleNamespace(
        segment_id="seg-1",
        segment_type="contract",
        segment_title=None,
        page_start=1,
        page_end=1,
        segment_order=0,
        scope_name="main_contract",
        is_primary=True,
        element_start=0,
        element_end=1,
    )


def _make_raw_element() -> dict:
    return {
        "id": "el-1",
        "element_id": "el-1",
        "type": "NarrativeText",
        "text": "1. Definitions",
        "page": 1,
    }


def test_build_file_structure_classifies_before_segmentation(monkeypatch):
    call_order: list[str] = []

    raw_elements = [_make_raw_element()]
    classified_elements = [
        {
            **raw_elements[0],
            "element_type": "heading_candidate",
            "metadata": {"semantic_element_type": "section_heading"},
        }
    ]

    def fake_classify(elements, *, document_id=None):
        call_order.append("classify")
        assert elements == raw_elements
        return classified_elements

    def fake_segment_document(*, document_id, document_version_id, elements):
        call_order.append("segment")
        assert elements == classified_elements
        assert elements[0]["element_type"] == "heading_candidate"
        return [_make_segment()]

    def fake_build_single_segment_tree(**kwargs):
        prepared = kwargs["elements"]
        assert len(prepared) == 1
        assert prepared[0]["element_type"] == "heading_candidate"
        assert prepared[0]["scope"] == "main_contract"
        return MagicMock(name="tree")

    monkeypatch.setattr(pipeline, "FileStructureResult", _FakeFileStructureResult)
    monkeypatch.setattr(pipeline, "classify_elements", fake_classify)
    monkeypatch.setattr(pipeline, "segment_document", fake_segment_document)
    monkeypatch.setattr(pipeline, "build_single_segment_tree", fake_build_single_segment_tree)
    monkeypatch.setattr(pipeline, "build_file_graph", lambda **kwargs: MagicMock(name="file_graph"))

    result = pipeline.build_file_structure(
        document_id="doc-1",
        elements=raw_elements,
    )

    assert call_order == ["classify", "segment"]
    assert result.primary_tree is result.segment_trees[0]


def test_build_file_structure_classifier_failure_falls_back_to_clean_elements(monkeypatch):
    raw_elements = [_make_raw_element()]
    seen: dict[str, object] = {}

    def fake_classify(elements, *, document_id=None):
        raise RuntimeError("classifier failure")

    def fake_segment_document(*, document_id, document_version_id, elements):
        seen["elements"] = elements
        return [_make_segment()]

    monkeypatch.setattr(pipeline, "FileStructureResult", _FakeFileStructureResult)
    monkeypatch.setattr(pipeline, "classify_elements", fake_classify)
    monkeypatch.setattr(pipeline, "segment_document", fake_segment_document)
    monkeypatch.setattr(pipeline, "build_single_segment_tree", lambda **kwargs: MagicMock(name="tree"))
    monkeypatch.setattr(pipeline, "build_file_graph", lambda **kwargs: MagicMock(name="file_graph"))

    result = pipeline.build_file_structure(
        document_id="doc-1",
        elements=raw_elements,
    )

    assert result is not None
    assert seen["elements"] == raw_elements


def test_build_file_structure_empty_input_skips_classifier(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("classify_elements should not be called for empty input")

    monkeypatch.setattr(pipeline, "FileStructureResult", _FakeFileStructureResult)
    monkeypatch.setattr(pipeline, "classify_elements", fail_if_called)
    monkeypatch.setattr(
        pipeline,
        "make_single_segment_list",
        lambda **kwargs: [_make_segment()],
    )
    monkeypatch.setattr(pipeline, "build_single_segment_tree", lambda **kwargs: MagicMock(name="tree"))
    monkeypatch.setattr(pipeline, "build_file_graph", lambda **kwargs: MagicMock(name="file_graph"))

    result = pipeline.build_file_structure(
        document_id="doc-1",
        elements=[],
    )

    assert result is not None
    assert len(result.segment_trees) == 1


