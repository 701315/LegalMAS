# tests/services/structure/test_file_graph_builder.py
"""
Тесты для file_graph_builder.

Используют актуальный публичный API ClauseTree / FrozenHierarchyNode.
"""

import pytest

from services.structure.file_graph_builder import (
    _pick_primary_segment,
    _sync_primary_flags,
    _derive_file_confidence,
)
from services.structure.models import (
    ClauseTree,
    FrozenHierarchyNode,
    SegmentDocument,
    CrossReferenceGraph,
    CrossReferenceStats,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_CONFIDENCE_MEDIUM,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
)

def _empty_cross_reference_graph(document_id: str = "doc_1") -> CrossReferenceGraph:
    """Строит пустой валидный CrossReferenceGraph по текущему контракту."""
    return CrossReferenceGraph.from_references(
        document_id=document_id,
        references=(),
        stats=CrossReferenceStats(
            references_count=0,
            unique_sources_count=0,
            unique_targets_count=0,
        ),
    )

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_segment(
    segment_id: str,
    segment_type: str,
    *,
    order: int = 0,
    page_start: int = 1,
    page_end: int = 5,
    confidence: str = SEGMENT_CONFIDENCE_HIGH,
    is_primary: bool = False,
) -> SegmentDocument:
    return SegmentDocument(
        segment_id=segment_id,
        document_id="doc_1",
        segment_order=order,
        segment_type=segment_type,
        page_start=page_start,
        page_end=page_end,
        element_start=0,
        element_end=10,
        confidence=confidence,
        is_primary=is_primary,
    )


def _make_empty_tree(
    segment_id: str,
    *,
    confidence: str = STRUCTURE_CONFIDENCE_FAILED,
    degraded: bool = True,
    is_primary: bool = False,
) -> ClauseTree:
    """ClauseTree без узлов (деградированное дерево)."""
    graph = _empty_cross_reference_graph("doc_1")
    return ClauseTree(
        document_id="doc_1",
        root=[],
        cross_reference_graph=graph,
        structure_confidence=confidence,
        degraded=degraded,
        segment_id=segment_id,
        is_primary_segment=is_primary,
    )


def _make_leaf_node(
    effective_uid: str,
    *,
    start_page: int = 1,
    end_page: int = 2,
) -> FrozenHierarchyNode:
    """Минимальный frozen leaf node для тестов."""
    scope, raw_uid = effective_uid.split(":", 1)
    return FrozenHierarchyNode(
        effective_uid=effective_uid,
        title="Test Clause",
        level=1,
        raw_uid=raw_uid,
        scope=scope,
        node_kind="leaf",
        structural_hash="abc123def456",
        own_element_ids=("e1",),
        subtree_element_ids=("e1",),
        own_text="Test text.",
        subtree_text="Test text.",
        start_page=start_page,
        end_page=end_page,
    )


def _make_tree_with_node(
    segment_id: str,
    effective_uid: str,
    *,
    confidence: str = STRUCTURE_CONFIDENCE_HIGH,
    degraded: bool = False,
    is_primary: bool = False,
    page_start: int = 1,
    page_end: int = 2,
) -> ClauseTree:
    """ClauseTree с одним leaf-узлом."""
    node = _make_leaf_node(effective_uid, start_page=page_start, end_page=page_end)
    graph = _empty_cross_reference_graph("doc_1")
    scope = effective_uid.split(":", 1)[0]
    return ClauseTree(
        document_id="doc_1",
        root=[node],
        cross_reference_graph=graph,
        structure_confidence=confidence,
        degraded=degraded,
        segment_id=segment_id,
        is_primary_segment=is_primary,
        scope_name=scope,
        segment_page_range=(page_start, page_end),
    )


# ── Тесты _pick_primary_segment ───────────────────────────────────────────────

def test_pick_primary_marked() -> None:
    """Если ровно один segment помечен is_primary=True, он становится primary."""
    seg1 = _make_segment("seg_1", SEGMENT_TYPE_CONTRACT, order=0, is_primary=False)
    seg2 = _make_segment("seg_2", SEGMENT_TYPE_APPENDIX, order=1, is_primary=True)

    primary_id = _pick_primary_segment([seg1, seg2])
    assert primary_id == "seg_2"


def test_pick_primary_contract_high() -> None:
    """Если нет marked primary, выбирается contract с HIGH confidence."""
    seg1 = _make_segment(
        "seg_1",
        SEGMENT_TYPE_APPENDIX,
        order=0,
        confidence=SEGMENT_CONFIDENCE_MEDIUM,
    )
    seg2 = _make_segment(
        "seg_2",
        SEGMENT_TYPE_CONTRACT,
        order=1,
        confidence=SEGMENT_CONFIDENCE_HIGH,
    )

    primary_id = _pick_primary_segment([seg1, seg2])
    assert primary_id == "seg_2"


# ── Тесты _derive_file_confidence ─────────────────────────────────────────────

def test_file_confidence_primary_failed() -> None:
    """Если primary tree FAILED, file-level confidence тоже FAILED."""
    tree1 = _make_empty_tree("seg_1", confidence=STRUCTURE_CONFIDENCE_FAILED, degraded=True)

    file_conf = _derive_file_confidence(trees=[tree1], primary_segment_id="seg_1")
    assert file_conf == STRUCTURE_CONFIDENCE_FAILED


def test_file_confidence_primary_high_secondary_failed() -> None:
    """Если primary HIGH, но secondary FAILED — file-level остаётся HIGH."""
    tree1 = _make_tree_with_node(
        "seg_1",
        "maincontract:1",
        confidence=STRUCTURE_CONFIDENCE_HIGH,
        degraded=False,
        is_primary=True,
    )
    tree2 = _make_empty_tree("seg_2", confidence=STRUCTURE_CONFIDENCE_FAILED, degraded=True)

    file_conf = _derive_file_confidence(trees=[tree1, tree2], primary_segment_id="seg_1")
    assert file_conf == STRUCTURE_CONFIDENCE_HIGH


# ── Тесты _sync_primary_flags ─────────────────────────────────────────────────

def test_sync_primary_flags() -> None:
    """_sync_primary_flags проставляет is_primary только для выбранного segment."""
    seg1 = _make_segment("seg_1", SEGMENT_TYPE_CONTRACT, order=0, is_primary=False)
    seg2 = _make_segment("seg_2", SEGMENT_TYPE_APPENDIX, order=1, is_primary=False)

    _sync_primary_flags([seg1, seg2], "seg_1")

    assert seg1.is_primary is True
    assert seg2.is_primary is False
    