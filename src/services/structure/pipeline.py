# src/services/structure/pipeline.py

"""
Структурный пайплайн: elements -> ClauseTree / FileStructureResult.

Публичный фасад.
Вся реализация вынесена во внутренний пакет services.structure.pipeline.*.

API:
- build_structure()                     — legacy wrapper
- build_file_structure()                — Phase 1-7 (текущий основной)
- build_file_structure_with_analysis()  — Phase 1-9 (Phase 8 + 9 postbuild)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logging import get_logger
from services.structure.chunk_planner import plan_chunking
from services.structure.coherence import CrossSegmentCoherenceResolver
from services.structure.element_classifier import classify_elements
from services.structure.file_graph_builder import build_file_graph
from services.structure.models import FileStructureResult
from services.structure._models._analysis import (
    FileStructureAnalysisResult,
    QualityThresholds,
)

from ._pipeline._core_builder import build_single_segment_tree
from ._pipeline._element_validation import (
    clean_elements,
    ensure_element_segment_metadata,
)
from ._pipeline._postbuild_analysis import analyze_file_structure
from ._pipeline._segment_utils import (
    make_single_segment_list,
    segment_document,
)

if TYPE_CHECKING:
    from services.telemetry._collector import TelemetryCollector


_COHERENCE_RESOLVER = CrossSegmentCoherenceResolver()

logger = get_logger(__name__)


def _classify_elements_safe(
    document_id: str,
    elements: list[dict],
) -> list[dict]:
    """
    Failure-isolated wrapper around element classification.

    Classifier must run BEFORE segmentation and structure building because:
    - segmenter uses element_type in boundary heuristics;
    - TOC suppression reads classified TOC/body/artifact labels;
    - heading builder allows/rejects candidates based on element_type.

    If classification fails for any reason, pipeline falls back to the cleaned
    elements list without crashing.
    """
    if not elements:
        return elements

    try:
        return classify_elements(
            elements,
            document_id=document_id,
        )
    except Exception:
        logger.exception(
            "STRUCTURE classify_elements_failed_falling_back_to_clean_elements",
            extra={
                "document_id": document_id,
                "elements_count": len(elements),
            },
        )
        return elements


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
    collector: TelemetryCollector | None = None,
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
            collector=collector,
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

    # A1: classification MUST happen before segment_document() and before
    # heading / hierarchy building. Otherwise segmenter and structure path
    # operate on under-classified elements.
    classified = _classify_elements_safe(document_id, clean)

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
            collector=collector,
        )

        segment_trees.append(tree)

    coherence_result = (
        _COHERENCE_RESOLVER.resolve(
            segment_trees,
            collector=collector,
            document_id=document_id,
        )
        if len(segment_trees) > 1
        else None
    )

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
        coherence_result=coherence_result,
    )


def build_file_structure_with_analysis(
    document_id: str,
    elements: list[dict] | None,
    *,
    document_version_id: str | None = None,
    quality_thresholds: QualityThresholds | None = None,
    sliding_window: int = 5,
    crossref_neighborhood: int = 2,
    collector: TelemetryCollector | None = None,
) -> FileStructureAnalysisResult:
    """
    Phase 1-9: elements → structure → cohesion → quality evaluation.

    Не ломает старый build_file_structure().
    Используется downstream слоями (Phase 10 Chunk Planner).

    Параметры:
    - quality_thresholds: кастомные пороги Phase 9 (None → дефолты)
    - sliding_window: размер окна Phase 8 cohesion (default=5)
    - crossref_neighborhood: locality Phase 8 crossref edges (default=2)

    Возвращает FileStructureAnalysisResult:
    - file_structure: оригинальный FileStructureResult
    - segment_artifacts: Phase 8 + Phase 9 артефакты по сегментам
    """
    base_result = build_file_structure(
        document_id=document_id,
        elements=elements,
        document_version_id=document_version_id,
        collector=collector,
    )

    return analyze_file_structure(
        base_result,
        thresholds=quality_thresholds,
        sliding_window=sliding_window,
        crossref_neighborhood=crossref_neighborhood,
        collector=collector,
    )


def build_file_structure_with_chunk_plan(
    document_id: str,
    elements: list[dict] | None,
    *,
    document_version_id: str | None = None,
    quality_thresholds: QualityThresholds | None = None,
    collector: TelemetryCollector | None = None,
):
    analysis = build_file_structure_with_analysis(
        document_id=document_id,
        elements=elements,
        document_version_id=document_version_id,
        quality_thresholds=quality_thresholds,
        collector=collector,
    )
    plan = plan_chunking(analysis)
    return analysis, plan


