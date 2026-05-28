# src/services/structure/pipeline.py

"""
Структурный пайплайн: elements -> ClauseTree / FileStructureResult.

Публичный фасад.
Вся реализация вынесена во внутренний пакет services.structure.pipeline.*
"""

from __future__ import annotations

from core.logging import get_logger
from services.structure.file_graph_builder import build_file_graph
from services.structure.models import FileStructureResult

from ._pipeline._core_builder import build_single_segment_tree
from ._pipeline._element_validation import clean_elements, ensure_element_segment_metadata
from ._pipeline._segment_utils import (
    make_single_segment_list,
    segment_document,
)

logger = get_logger(__name__)


def build_structure(
    document_id: str,
    elements: list[dict] | None,
):
    """
    Legacy wrapper.
    """
    result = build_file_structure(
        document_id=document_id,
        elements=elements,
        document_version_id=None,
    )
    return result.primary_tree


def build_file_structure(
    document_id: str,
    elements: list[dict] | None,
    *,
    document_version_id: str | None = None,
) -> FileStructureResult:
    if not document_id:
        logger.warning("STRUCTURE build_file_structure: empty document_id")
        document_id = "<unknown>"

    clean = clean_elements(document_id, elements)

    if not clean:
        segments = make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=[],
        )

        seg = segments[0]

        tree = build_single_segment_tree(
            document_id=document_id,
            elements=[],
            segment_id=seg.segment_id,
            segment_type=seg.segment_type,
            segment_title=seg.segment_title,
            segment_page_range=(seg.page_start, seg.page_end),
            segment_order=seg.segment_order,
            scope_name=seg.scope_name,
            is_primary_segment=True,
        )

        file_graph = build_file_graph(
            document_id=document_id,
            document_version_id=document_version_id,
            segments=segments,
            segment_trees=[tree],
        )

        return FileStructureResult(
            primary_tree=tree,
            segment_trees=[tree],
            file_graph=file_graph,
        )

    classified = clean  # классификация уже вызывается выше по проекту
    segments = segment_document(
        document_id=document_id,
        document_version_id=document_version_id,
        elements=classified,
    )

    segment_trees = []

    for seg in segments:
        slice_ = classified[seg.element_start : seg.element_end]
        prepared = ensure_element_segment_metadata(
            elements=slice_,
            segment=seg,
        )

        tree = build_single_segment_tree(
            document_id=document_id,
            elements=prepared,
            segment_id=seg.segment_id,
            segment_type=seg.segment_type,
            segment_title=seg.segment_title,
            segment_page_range=(seg.page_start, seg.page_end),
            segment_order=seg.segment_order,
            scope_name=seg.scope_name,
            is_primary_segment=seg.is_primary,
        )

        segment_trees.append(tree)

    file_graph = build_file_graph(
        document_id=document_id,
        document_version_id=document_version_id,
        segments=segments,
        segment_trees=segment_trees,
    )

    primary_tree = segment_trees[0]

    return FileStructureResult(
        primary_tree=primary_tree,
        segment_trees=segment_trees,
        file_graph=file_graph,
    )
