# tests/services/structure/test_file_graph_builder.py

import pytest
from services.structure.file_graph_builder import (
    build_file_graph,
    _pick_primary_segment,
    _sync_primary_flags,
    _derive_file_confidence,
)
from services.structure.models import (
    ClauseTree,
    ClauseNode,
    SegmentDocument,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_CONFIDENCE_MEDIUM,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
)


def test_pick_primary_marked():
    """Если ровно один segment помечен is_primary=True, он и становится primary."""
    seg1 = SegmentDocument(
        segment_id="seg_1",
        document_id="doc_1",
        segment_order=0,
        segment_type=SEGMENT_TYPE_CONTRACT,
        page_start=1,
        page_end=5,
        element_start=0,
        element_end=10,
        is_primary=False,
    )
    seg2 = SegmentDocument(
        segment_id="seg_2",
        document_id="doc_1",
        segment_order=1,
        segment_type=SEGMENT_TYPE_APPENDIX,
        page_start=6,
        page_end=10,
        element_start=10,
        element_end=20,
        is_primary=True,
    )
    
    primary_id = _pick_primary_segment([seg1, seg2])
    assert primary_id == "seg_2"


def test_pick_primary_contract_high():
    """Если нет marked primary, выбираем contract с HIGH confidence."""
    seg1 = SegmentDocument(
        segment_id="seg_1",
        document_id="doc_1",
        segment_order=0,
        segment_type=SEGMENT_TYPE_APPENDIX,
        page_start=1,
        page_end=5,
        element_start=0,
        element_end=10,
        confidence=SEGMENT_CONFIDENCE_MEDIUM,
    )
    seg2 = SegmentDocument(
        segment_id="seg_2",
        document_id="doc_1",
        segment_order=1,
        segment_type=SEGMENT_TYPE_CONTRACT,
        page_start=6,
        page_end=15,
        element_start=10,
        element_end=30,
        confidence=SEGMENT_CONFIDENCE_HIGH,
    )
    
    primary_id = _pick_primary_segment([seg1, seg2])
    assert primary_id == "seg_2"


def test_file_confidence_primary_failed():
    """Если primary tree FAILED, file-level confidence тоже FAILED."""
    tree1 = ClauseTree(
        document_id="doc_1",
        root=[],
        references_index=[],
        structure_confidence=STRUCTURE_CONFIDENCE_FAILED,
        degraded=True,
        segment_id="seg_1",
    )
    
    file_conf = _derive_file_confidence(
        trees=[tree1],
        primary_segment_id="seg_1",
    )
    assert file_conf == STRUCTURE_CONFIDENCE_FAILED


def test_file_confidence_primary_high_secondary_failed():
    """Если primary HIGH, но secondary FAILED, file-level всё равно HIGH."""
    tree1 = ClauseTree(
        document_id="doc_1",
        root=[ClauseNode(
            effective_uid="1",
            raw_uid="1",
            scope="main_contract",
            clause_uid="1",
            title="Clause 1",
            level=1,
            node_kind="leaf",
        )],
        references_index=[],
        structure_confidence=STRUCTURE_CONFIDENCE_HIGH,
        degraded=False,
        segment_id="seg_1",
        is_primary_segment=True,
    )
    tree2 = ClauseTree(
        document_id="doc_1",
        root=[],
        references_index=[],
        structure_confidence=STRUCTURE_CONFIDENCE_FAILED,
        degraded=True,
        segment_id="seg_2",
    )
    
    file_conf = _derive_file_confidence(
        trees=[tree1, tree2],
        primary_segment_id="seg_1",
    )
    assert file_conf == STRUCTURE_CONFIDENCE_HIGH


def test_sync_primary_flags():
    """_sync_primary_flags проставляет is_primary только для выбранного segment."""
    seg1 = SegmentDocument(
        segment_id="seg_1",
        document_id="doc_1",
        segment_order=0,
        segment_type=SEGMENT_TYPE_CONTRACT,
        page_start=1,
        page_end=5,
        element_start=0,
        element_end=10,
        is_primary=False,
    )
    seg2 = SegmentDocument(
        segment_id="seg_2",
        document_id="doc_1",
        segment_order=1,
        segment_type=SEGMENT_TYPE_APPENDIX,
        page_start=6,
        page_end=10,
        element_start=10,
        element_end=20,
        is_primary=False,
    )
    
    _sync_primary_flags([seg1, seg2], "seg_1")
    
    assert seg1.is_primary is True
    assert seg2.is_primary is False

    