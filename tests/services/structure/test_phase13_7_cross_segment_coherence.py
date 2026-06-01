"""
tests/services/structure/test_phase13_7_cross_segment_coherence.py

Phase 13.7 — Cross-Segment Coherence Resolver tests.

Покрытие:
- _get_rightmost_deepest_node
- _get_orphan_roots
- _compute_confidence
- CrossSegmentCoherenceResolver.resolve() — основные сценарии
- CrossSegmentCoherenceResult.to_dict()
- CoherenceLink.to_dict()
"""

from __future__ import annotations

import pytest

from services.structure._models._crossref_graph import (
    CrossReferenceGraph,
    CrossReferenceStats,
)
from services.structure._models._nodes import FrozenHierarchyNode
from services.structure._models._tree import ClauseTree
from services.structure.models import STRUCTURE_CONFIDENCE_HIGH
from services.structure.coherence._resolver import (
    CrossSegmentCoherenceResolver,
    _compute_confidence,
    _get_orphan_roots,
    _get_rightmost_deepest_node,
)
from services.structure.coherence._types import (
    CoherenceLink,
    CrossSegmentCoherenceResult,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _empty_crossref_graph(document_id: str = "doc-1") -> CrossReferenceGraph:
    return CrossReferenceGraph(
        document_id=document_id,
        references=(),
        outgoing_index={},
        incoming_index={},
        stats=CrossReferenceStats(),
    )


def _node(
    *,
    scope: str,
    raw_uid: str,
    level: int | None = None,
    start_page: int = 1,
    end_page: int = 1,
    children: tuple[FrozenHierarchyNode, ...] = (),
    node_kind: str | None = None,
    diagnostics: dict | None = None,
) -> FrozenHierarchyNode:
    """
    Фабрика FrozenHierarchyNode для тестов.

    level вычисляется из raw_uid (количество точек + 1) если не передан явно.
    node_kind определяется автоматически по наличию children если не передан.
    start_page/end_page ДОЛЖНЫ совпадать с segment_page_range дерева — инвариант ClauseTree.
    """
    effective_uid = f"{scope}:{raw_uid}"
    inferred_level = level if level is not None else len(raw_uid.split("."))
    inferred_node_kind = node_kind if node_kind is not None else (
        "section" if children else "leaf"
    )
    return FrozenHierarchyNode(
        effective_uid=effective_uid,
        raw_uid=raw_uid,
        scope=scope,
        title=raw_uid,
        level=inferred_level,
        node_kind=inferred_node_kind,
        structural_hash=f"hash_{scope}_{raw_uid.replace('.', '_')}",
        own_element_ids=(f"el_{scope}_{raw_uid.replace('.', '_')}",),
        subtree_element_ids=(f"el_{scope}_{raw_uid.replace('.', '_')}",),
        start_page=start_page,
        end_page=end_page,
        children=children,
        diagnostics=diagnostics or {},
    )


def _orphan_node(
    *,
    scope: str,
    raw_uid: str,
    level: int | None = None,
    start_page: int = 1,
    end_page: int | None = None,
) -> FrozenHierarchyNode:
    """
    FrozenHierarchyNode с diagnostics["recovered_via_best_effort"] = True.
    end_page defaults to start_page если не задан явно.
    """
    return _node(
        scope=scope,
        raw_uid=raw_uid,
        level=level,
        start_page=start_page,
        end_page=end_page if end_page is not None else start_page,
        diagnostics={"recovered_via_best_effort": True},
    )


def _make_tree(
    *,
    document_id: str = "doc-1",
    segment_id: str,
    segment_order: int = 0,
    root: list[FrozenHierarchyNode],
    segment_page_range: tuple[int, int] = (1, 5),
) -> ClauseTree:
    """
    Минимальный ClauseTree для тестов.
    Все nodes в root ДОЛЖНЫ иметь start_page/end_page в пределах segment_page_range.
    """
    return ClauseTree(
        document_id=document_id,
        root=root,
        cross_reference_graph=_empty_crossref_graph(document_id),
        structure_confidence=STRUCTURE_CONFIDENCE_HIGH,
        segment_id=segment_id,
        segment_order=segment_order,
        segment_page_range=segment_page_range,
        is_primary_segment=(segment_order == 0),
    )


# ─── Unit: _get_rightmost_deepest_node ───────────────────────────────────────


def test_rightmost_deepest_empty_list():
    assert _get_rightmost_deepest_node([]) is None


def test_rightmost_deepest_single_leaf():
    node = _node(scope="main_contract", raw_uid="1")
    assert _get_rightmost_deepest_node([node]) is node


def test_rightmost_deepest_flat_list_returns_last():
    """Плоский список без children — возвращает последний node."""
    n1 = _node(scope="main_contract", raw_uid="1")
    n2 = _node(scope="main_contract", raw_uid="2")
    n3 = _node(scope="main_contract", raw_uid="3")
    assert _get_rightmost_deepest_node([n1, n2, n3]) is n3


def test_rightmost_deepest_with_children():
    """Если последний node имеет children — идём вглубь рекурсивно."""
    child1 = _node(scope="main_contract", raw_uid="3.1", start_page=3, end_page=4)
    child2 = _node(scope="main_contract", raw_uid="3.2", start_page=4, end_page=5)
    parent = _node(
        scope="main_contract", raw_uid="3",
        start_page=3, end_page=5,
        children=(child1, child2), node_kind="section",
    )
    n1 = _node(scope="main_contract", raw_uid="1")
    assert _get_rightmost_deepest_node([n1, parent]) is child2


def test_rightmost_deepest_nested_three_levels():
    """Рекурсия до третьего уровня."""
    leaf = _node(scope="main_contract", raw_uid="1.1.1", level=3)
    mid = _node(
        scope="main_contract", raw_uid="1.1", level=2,
        children=(leaf,), node_kind="section",
    )
    top = _node(
        scope="main_contract", raw_uid="1", level=1,
        children=(mid,), node_kind="section",
    )
    assert _get_rightmost_deepest_node([top]) is leaf


# ─── Unit: _get_orphan_roots ─────────────────────────────────────────────────


def test_orphan_roots_empty_list():
    assert _get_orphan_roots([]) == []


def test_orphan_roots_no_diagnostics():
    n1 = _node(scope="main_contract", raw_uid="1")
    n2 = _node(scope="main_contract", raw_uid="2")
    assert _get_orphan_roots([n1, n2]) == []


def test_orphan_roots_with_best_effort_flag():
    normal = _node(scope="main_contract", raw_uid="1")
    orphan = _orphan_node(scope="appendix_a", raw_uid="A.1")
    result = _get_orphan_roots([normal, orphan])
    assert result == [orphan]


def test_orphan_roots_multiple():
    o1 = _orphan_node(scope="appendix_a", raw_uid="A.1")
    o2 = _orphan_node(scope="appendix_a", raw_uid="A.2")
    normal = _node(scope="main_contract", raw_uid="1")
    result = _get_orphan_roots([normal, o1, o2])
    assert len(result) == 2
    assert o1 in result and o2 in result


def test_orphan_roots_false_flag_not_included():
    n = _node(
        scope="main_contract", raw_uid="5",
        diagnostics={"recovered_via_best_effort": False},
    )
    assert _get_orphan_roots([n]) == []


# ─── Unit: _compute_confidence ───────────────────────────────────────────────


def test_confidence_perfect():
    assert _compute_confidence(level_delta=1, page_distance=0) == 1.0


def test_confidence_decreases_with_page_distance():
    c0 = _compute_confidence(level_delta=1, page_distance=0)
    c1 = _compute_confidence(level_delta=1, page_distance=1)
    c3 = _compute_confidence(level_delta=1, page_distance=3)
    assert c0 > c1 > c3


def test_confidence_penalty_for_level_delta_2():
    c1 = _compute_confidence(level_delta=1, page_distance=0)
    c2 = _compute_confidence(level_delta=2, page_distance=0)
    assert c1 - c2 == pytest.approx(0.10, abs=0.001)


def test_confidence_minimum_floor():
    assert _compute_confidence(level_delta=2, page_distance=100) == pytest.approx(0.10, abs=0.001)


def test_confidence_max_is_one():
    assert _compute_confidence(level_delta=1, page_distance=0) <= 1.0


# ─── Integration: CrossSegmentCoherenceResolver ──────────────────────────────


@pytest.fixture
def resolver() -> CrossSegmentCoherenceResolver:
    return CrossSegmentCoherenceResolver()


def test_single_segment_returns_empty_result(resolver):
    tree = _make_tree(
        segment_id="seg-1",
        root=[_node(scope="main_contract", raw_uid="1")],
    )
    result = resolver.resolve([tree])
    assert result.links_found == 0
    assert result.links == []
    assert result.segments_analyzed == 1
    assert result.resolver_error is None


def test_two_segments_no_orphans_no_links(resolver):
    """Два сегмента, нет orphan roots → нет links."""
    tree1 = _make_tree(
        segment_id="seg-1", segment_order=0,
        root=[_node(scope="main_contract", raw_uid="1", start_page=1, end_page=5)],
        segment_page_range=(1, 5),
    )
    tree2 = _make_tree(
        segment_id="seg-2", segment_order=1,
        root=[_node(scope="appendix_a", raw_uid="A.1", start_page=6, end_page=10)],
        segment_page_range=(6, 10),
    )
    result = resolver.resolve([tree1, tree2])
    assert result.links_found == 0
    assert result.segments_analyzed == 2


def test_orphan_root_linked_to_prev_heading(resolver):
    """Основной сценарий: orphan root линкуется к последнему heading предыдущего сегмента."""
    last_node = _node(scope="main_contract", raw_uid="3", level=1, start_page=4, end_page=5)
    tree1 = _make_tree(
        segment_id="seg-1", segment_order=0,
        root=[
            _node(scope="main_contract", raw_uid="1", level=1, start_page=1, end_page=2),
            _node(scope="main_contract", raw_uid="2", level=1, start_page=2, end_page=3),
            last_node,
        ],
        segment_page_range=(1, 5),
    )
    orphan = _orphan_node(scope="appendix_a", raw_uid="3.1", level=2, start_page=6, end_page=7)
    tree2 = _make_tree(
        segment_id="seg-2", segment_order=1,
        root=[orphan],
        segment_page_range=(6, 10),
    )
    result = resolver.resolve([tree1, tree2])
    assert result.links_found == 1
    link = result.links[0]
    assert link.source_segment_id == "seg-1"
    assert link.target_segment_id == "seg-2"
    assert link.source_node_uid == last_node.effective_uid
    assert link.target_node_uid == orphan.effective_uid
    assert link.source_level == 1
    assert link.target_level == 2
    assert 0.0 < link.confidence <= 1.0


def test_level_delta_zero_skipped(resolver):
    """level_delta = 0: orphan на том же уровне что source → нет link."""
    last_node = _node(scope="main_contract", raw_uid="3", level=2, start_page=1, end_page=5)
    tree1 = _make_tree(segment_id="seg-1", root=[last_node], segment_page_range=(1, 5))
    orphan = _orphan_node(scope="appendix_a", raw_uid="A.1", level=2, start_page=6, end_page=6)
    tree2 = _make_tree(segment_id="seg-2", root=[orphan], segment_page_range=(6, 10))
    assert resolver.resolve([tree1, tree2]).links_found == 0


def test_level_delta_negative_skipped(resolver):
    """Orphan выше по иерархии чем source (level_delta < 0) → нет link."""
    last_node = _node(scope="main_contract", raw_uid="3.1", level=2, start_page=1, end_page=5)
    tree1 = _make_tree(segment_id="seg-1", root=[last_node], segment_page_range=(1, 5))
    orphan = _orphan_node(scope="appendix_a", raw_uid="A", level=1, start_page=6, end_page=6)
    tree2 = _make_tree(segment_id="seg-2", root=[orphan], segment_page_range=(6, 10))
    assert resolver.resolve([tree1, tree2]).links_found == 0


def test_level_delta_too_large_skipped(resolver):
    """level_delta=3 при max_level_delta=2 → нет link."""
    last_node = _node(scope="main_contract", raw_uid="1", level=1, start_page=1, end_page=5)
    tree1 = _make_tree(segment_id="seg-1", root=[last_node], segment_page_range=(1, 5))
    orphan = _orphan_node(scope="appendix_a", raw_uid="A.1.1.1", level=4, start_page=6, end_page=6)
    tree2 = _make_tree(segment_id="seg-2", root=[orphan], segment_page_range=(6, 10))
    assert resolver.resolve([tree1, tree2], max_level_delta=2).links_found == 0


def test_page_distance_too_large_skipped(resolver):
    """page_distance=15 при max_page_distance=5 → нет link."""
    last_node = _node(scope="main_contract", raw_uid="1", level=1, start_page=1, end_page=5)
    tree1 = _make_tree(segment_id="seg-1", root=[last_node], segment_page_range=(1, 5))
    # segment_page_range=(20, 30) → page_distance = |20 - 5| = 15 > 5
    orphan = _orphan_node(scope="appendix_a", raw_uid="A.1", level=2, start_page=20, end_page=20)
    tree2 = _make_tree(segment_id="seg-2", root=[orphan], segment_page_range=(20, 30))
    assert resolver.resolve([tree1, tree2], max_page_distance=5).links_found == 0


def test_normal_top_level_node_not_linked(resolver):
    """Обычный top-level node без best_effort flag не линкуется."""
    last_node = _node(scope="main_contract", raw_uid="3", level=1, start_page=1, end_page=5)
    tree1 = _make_tree(segment_id="seg-1", root=[last_node], segment_page_range=(1, 5))
    normal = _node(scope="appendix_a", raw_uid="A.1", level=2, start_page=6, end_page=10)
    tree2 = _make_tree(segment_id="seg-2", root=[normal], segment_page_range=(6, 10))
    assert resolver.resolve([tree1, tree2]).links_found == 0


def test_prev_tree_empty_root_no_links(resolver):
    """Предыдущий сегмент с пустым root → нет source node → нет links."""
    tree1 = _make_tree(segment_id="seg-1", root=[], segment_page_range=(1, 5))
    orphan = _orphan_node(scope="appendix_a", raw_uid="A.1", level=2, start_page=6, end_page=6)
    tree2 = _make_tree(segment_id="seg-2", root=[orphan], segment_page_range=(6, 10))
    assert resolver.resolve([tree1, tree2]).links_found == 0


def test_three_segments_links_across_pairs(resolver):
    """Links строятся независимо для каждой смежной пары."""
    n1 = _node(scope="main_contract", raw_uid="1", level=1, start_page=1, end_page=3)
    tree1 = _make_tree(
        segment_id="seg-1", segment_order=0,
        root=[n1], segment_page_range=(1, 3),
    )
    o1 = _orphan_node(scope="appendix_a", raw_uid="A.1", level=2, start_page=4, end_page=5)
    n2 = _node(scope="appendix_a", raw_uid="A.2", level=2, start_page=6, end_page=8)
    tree2 = _make_tree(
        segment_id="seg-2", segment_order=1,
        root=[o1, n2], segment_page_range=(4, 8),
    )
    o2 = _orphan_node(scope="appendix_b", raw_uid="B.1", level=3, start_page=9, end_page=10)
    tree3 = _make_tree(
        segment_id="seg-3", segment_order=2,
        root=[o2], segment_page_range=(9, 10),
    )
    result = resolver.resolve([tree1, tree2, tree3])
    assert result.segments_analyzed == 3
    assert result.links_found == 2
    source_uids = {link.source_node_uid for link in result.links}
    assert n1.effective_uid in source_uids
    assert n2.effective_uid in source_uids


def test_resolver_failure_isolated(resolver, monkeypatch):
    """Исключение внутри анализа → resolver_error заполнен, не бросает."""
    monkeypatch.setattr(
        "services.structure.coherence._resolver._get_rightmost_deepest_node",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated internal failure")),
    )
    tree1 = _make_tree(
        segment_id="seg-1",
        root=[_node(scope="main_contract", raw_uid="1", start_page=1, end_page=5)],
        segment_page_range=(1, 5),
    )
    tree2 = _make_tree(
        segment_id="seg-2",
        root=[_orphan_node(scope="appendix_a", raw_uid="A.1", level=2, start_page=6, end_page=6)],
        segment_page_range=(6, 10),
    )
    result = resolver.resolve([tree1, tree2])
    assert result.resolver_error is not None
    assert "simulated internal failure" in result.resolver_error
    assert result.links_found == 0


# ─── Serialization ───────────────────────────────────────────────────────────


def test_coherence_link_to_dict():
    link = CoherenceLink(
        source_segment_id="seg-1",
        target_segment_id="seg-2",
        source_node_uid="main_contract:3",
        target_node_uid="appendix_a:A.1",
        source_level=1,
        target_level=2,
        page_distance=1,
        confidence=0.95,
    )
    d = link.to_dict()
    assert d["source_segment_id"] == "seg-1"
    assert d["target_segment_id"] == "seg-2"
    assert d["source_node_uid"] == "main_contract:3"
    assert d["target_node_uid"] == "appendix_a:A.1"
    assert d["source_level"] == 1
    assert d["target_level"] == 2
    assert d["page_distance"] == 1
    assert d["confidence"] == 0.95


def test_coherence_result_to_dict_empty():
    d = CrossSegmentCoherenceResult().to_dict()
    assert d["segments_analyzed"] == 0
    assert d["links_found"] == 0
    assert d["links"] == []
    assert d["resolver_error"] is None


def test_coherence_result_to_dict_with_links():
    link = CoherenceLink(
        source_segment_id="seg-1",
        target_segment_id="seg-2",
        source_node_uid="main_contract:3",
        target_node_uid="appendix_a:A.1",
        source_level=1,
        target_level=2,
        page_distance=0,
        confidence=1.0,
    )
    result = CrossSegmentCoherenceResult(links=[link], segments_analyzed=2, links_found=1)
    d = result.to_dict()
    assert d["links_found"] == 1
    assert len(d["links"]) == 1
    assert d["links"][0]["source_segment_id"] == "seg-1"

    