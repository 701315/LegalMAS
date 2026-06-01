"""
tests/services/structure/test_phase13_7_pipeline_collector_plumbing.py

Phase 13.7 — pipeline collector plumbing tests.

Покрытие:
- build_file_structure() прокидывает collector в build_single_segment_tree()
  на empty-document path
- build_file_structure() прокидывает collector в build_single_segment_tree()
  на segmented path
- build_file_structure() вызывает coherence resolver с collector/document_id
  только когда segment_trees > 1
- build_file_structure_with_analysis() прокидывает collector дальше
- build_file_structure_with_chunk_plan() прокидывает collector дальше
"""

from __future__ import annotations

from dataclasses import dataclass

import services.structure.pipeline as pipeline_module


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _FakeSegment:
    segment_id: str
    segment_type: str = "main"
    segment_title: str | None = None
    page_start: int = 1
    page_end: int = 1
    segment_order: int = 0
    scope_name: str = "main_contract"
    is_primary: bool = False
    element_start: int = 0
    element_end: int = 0


@dataclass
class _FakeTree:
    segment_id: str
    document_id: str = "doc-1"


class _FakeResult:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeResolver:
    def __init__(self, *, coherence_result):
        self.coherence_result = coherence_result
        self.calls: list[dict] = []

    def resolve(self, segment_trees, **kwargs):
        self.calls.append({
            "segment_trees": segment_trees,
            **kwargs,
        })
        return self.coherence_result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: build_file_structure
# ─────────────────────────────────────────────────────────────────────────────

def test_build_file_structure_empty_document_forwards_collector(monkeypatch):
    collector = object()
    fake_tree = _FakeTree(segment_id="seg-1", document_id="doc-1")

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        pipeline_module,
        "clean_elements",
        lambda document_id, elements: [],
    )
    monkeypatch.setattr(
        pipeline_module,
        "make_single_segment_list",
        lambda document_id, document_version_id, elements: [
            _FakeSegment(
                segment_id="seg-1",
                page_start=1,
                page_end=1,
                segment_order=0,
                is_primary=True,
            )
        ],
    )

    def _fake_build_single_segment_tree(**kwargs):
        captured["build_single_segment_tree_kwargs"] = kwargs
        return fake_tree

    monkeypatch.setattr(
        pipeline_module,
        "build_single_segment_tree",
        _fake_build_single_segment_tree,
    )
    monkeypatch.setattr(
        pipeline_module,
        "build_file_graph",
        lambda **kwargs: {"fake": "graph"},
    )
    monkeypatch.setattr(
        pipeline_module,
        "FileStructureResult",
        _FakeResult,
    )

    result = pipeline_module.build_file_structure(
        document_id="doc-1",
        elements=[],
        collector=collector,
    )

    kwargs = captured["build_single_segment_tree_kwargs"]
    assert kwargs["collector"] is collector
    assert kwargs["document_id"] == "doc-1"
    assert kwargs["elements"] == []
    assert result.primary_tree is fake_tree
    assert result.segment_trees == [fake_tree]
    assert result.file_graph == {"fake": "graph"}


def test_build_file_structure_segmented_path_forwards_collector_and_calls_coherence(monkeypatch):
    collector = object()
    fake_tree_1 = _FakeTree(segment_id="seg-1", document_id="doc-1")
    fake_tree_2 = _FakeTree(segment_id="seg-2", document_id="doc-1")
    fake_coherence = {"links_found": 1}

    build_tree_calls: list[dict] = []

    monkeypatch.setattr(
        pipeline_module,
        "clean_elements",
        lambda document_id, elements: [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}],
    )
    monkeypatch.setattr(
        pipeline_module,
        "segment_document",
        lambda document_id, document_version_id, elements: [
            _FakeSegment(
                segment_id="seg-1",
                page_start=1,
                page_end=2,
                segment_order=0,
                is_primary=True,
                element_start=0,
                element_end=2,
            ),
            _FakeSegment(
                segment_id="seg-2",
                page_start=3,
                page_end=4,
                segment_order=1,
                is_primary=False,
                element_start=2,
                element_end=3,
            ),
        ],
    )
    monkeypatch.setattr(
        pipeline_module,
        "ensure_element_segment_metadata",
        lambda elements, segment: elements,
    )

    def _fake_build_single_segment_tree(**kwargs):
        build_tree_calls.append(kwargs)
        if kwargs["segment_id"] == "seg-1":
            return fake_tree_1
        return fake_tree_2

    monkeypatch.setattr(
        pipeline_module,
        "build_single_segment_tree",
        _fake_build_single_segment_tree,
    )
    monkeypatch.setattr(
        pipeline_module,
        "build_file_graph",
        lambda **kwargs: {"fake": "graph"},
    )
    monkeypatch.setattr(
        pipeline_module,
        "FileStructureResult",
        _FakeResult,
    )

    fake_resolver = _FakeResolver(coherence_result=fake_coherence)
    monkeypatch.setattr(
        pipeline_module,
        "_COHERENCE_RESOLVER",
        fake_resolver,
    )

    result = pipeline_module.build_file_structure(
        document_id="doc-1",
        elements=[{"id": "raw"}],
        collector=collector,
    )

    assert len(build_tree_calls) == 2
    assert all(call["collector"] is collector for call in build_tree_calls)

    assert len(fake_resolver.calls) == 1
    resolver_call = fake_resolver.calls[0]
    assert resolver_call["segment_trees"] == [fake_tree_1, fake_tree_2]
    assert resolver_call["collector"] is collector
    assert resolver_call["document_id"] == "doc-1"

    assert result.primary_tree is fake_tree_1
    assert result.segment_trees == [fake_tree_1, fake_tree_2]
    assert result.coherence_result == fake_coherence


def test_build_file_structure_single_segment_does_not_call_coherence(monkeypatch):
    collector = object()
    fake_tree = _FakeTree(segment_id="seg-1", document_id="doc-1")

    monkeypatch.setattr(
        pipeline_module,
        "clean_elements",
        lambda document_id, elements: [{"id": "e1"}],
    )
    monkeypatch.setattr(
        pipeline_module,
        "segment_document",
        lambda document_id, document_version_id, elements: [
            _FakeSegment(
                segment_id="seg-1",
                page_start=1,
                page_end=1,
                segment_order=0,
                is_primary=True,
                element_start=0,
                element_end=1,
            )
        ],
    )
    monkeypatch.setattr(
        pipeline_module,
        "ensure_element_segment_metadata",
        lambda elements, segment: elements,
    )
    monkeypatch.setattr(
        pipeline_module,
        "build_single_segment_tree",
        lambda **kwargs: fake_tree,
    )
    monkeypatch.setattr(
        pipeline_module,
        "build_file_graph",
        lambda **kwargs: {"fake": "graph"},
    )
    monkeypatch.setattr(
        pipeline_module,
        "FileStructureResult",
        _FakeResult,
    )

    fake_resolver = _FakeResolver(coherence_result={"links_found": 99})
    monkeypatch.setattr(
        pipeline_module,
        "_COHERENCE_RESOLVER",
        fake_resolver,
    )

    result = pipeline_module.build_file_structure(
        document_id="doc-1",
        elements=[{"id": "raw"}],
        collector=collector,
    )

    assert fake_resolver.calls == []
    assert result.coherence_result is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: build_file_structure_with_analysis
# ─────────────────────────────────────────────────────────────────────────────

def test_build_file_structure_with_analysis_forwards_collector(monkeypatch):
    collector = object()
    fake_base_result = object()
    fake_analysis_result = object()

    captured: dict[str, object] = {}

    def _fake_build_file_structure(**kwargs):
        captured["build_file_structure_kwargs"] = kwargs
        return fake_base_result

    def _fake_analyze_file_structure(
        base_result,
        *,
        thresholds,
        sliding_window,
        crossref_neighborhood,
        collector,
    ):
        captured["analyze_file_structure_kwargs"] = {
            "base_result": base_result,
            "thresholds": thresholds,
            "sliding_window": sliding_window,
            "crossref_neighborhood": crossref_neighborhood,
            "collector": collector,
        }
        return fake_analysis_result

    monkeypatch.setattr(
        pipeline_module,
        "build_file_structure",
        _fake_build_file_structure,
    )
    monkeypatch.setattr(
        pipeline_module,
        "analyze_file_structure",
        _fake_analyze_file_structure,
    )

    result = pipeline_module.build_file_structure_with_analysis(
        document_id="doc-1",
        elements=[{"id": "e1"}],
        document_version_id="ver-1",
        quality_thresholds="thresholds",
        sliding_window=7,
        crossref_neighborhood=3,
        collector=collector,
    )

    assert result is fake_analysis_result

    build_kwargs = captured["build_file_structure_kwargs"]
    assert build_kwargs["document_id"] == "doc-1"
    assert build_kwargs["elements"] == [{"id": "e1"}]
    assert build_kwargs["document_version_id"] == "ver-1"
    assert build_kwargs["collector"] is collector

    analyze_kwargs = captured["analyze_file_structure_kwargs"]
    assert analyze_kwargs["base_result"] is fake_base_result
    assert analyze_kwargs["thresholds"] == "thresholds"
    assert analyze_kwargs["sliding_window"] == 7
    assert analyze_kwargs["crossref_neighborhood"] == 3
    assert analyze_kwargs["collector"] is collector


# ─────────────────────────────────────────────────────────────────────────────
# Tests: build_file_structure_with_chunk_plan
# ─────────────────────────────────────────────────────────────────────────────

def test_build_file_structure_with_chunk_plan_forwards_collector(monkeypatch):
    collector = object()
    fake_analysis = object()
    fake_plan = object()

    captured: dict[str, object] = {}

    def _fake_build_file_structure_with_analysis(**kwargs):
        captured["build_file_structure_with_analysis_kwargs"] = kwargs
        return fake_analysis

    def _fake_plan_chunking(analysis):
        captured["plan_chunking_analysis"] = analysis
        return fake_plan

    monkeypatch.setattr(
        pipeline_module,
        "build_file_structure_with_analysis",
        _fake_build_file_structure_with_analysis,
    )
    monkeypatch.setattr(
        pipeline_module,
        "plan_chunking",
        _fake_plan_chunking,
    )

    analysis, plan = pipeline_module.build_file_structure_with_chunk_plan(
        document_id="doc-1",
        elements=[{"id": "e1"}],
        document_version_id="ver-1",
        quality_thresholds="thresholds",
        collector=collector,
    )

    assert analysis is fake_analysis
    assert plan is fake_plan

    kwargs = captured["build_file_structure_with_analysis_kwargs"]
    assert kwargs["document_id"] == "doc-1"
    assert kwargs["elements"] == [{"id": "e1"}]
    assert kwargs["document_version_id"] == "ver-1"
    assert kwargs["quality_thresholds"] == "thresholds"
    assert kwargs["collector"] is collector

    assert captured["plan_chunking_analysis"] is fake_analysis


    