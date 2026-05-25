# src/services/structure/file_graph_builder.py

"""
FileGraph builder for multi-document STRUCTURE mode.

Для непрофессионального программиста:
Этот модуль собирает "мета-объект" всего файла — FileGraph.

Важно понимать разницу:
- ClauseTree = дерево одного логического документа / сегмента;
- FileGraph = контейнер над всеми сегментами файла.

Пример:
один PDF содержит:
1) договор,
2) приложение №1,
3) акт.

Тогда:
- будет 3 отдельных ClauseTree;
- и 1 FileGraph, который знает:
  - какие есть сегменты,
  - какой из них primary,
  - какие между ними есть связи (cross_links).

Сейчас логика остаётся консервативной:
- primary_segment_id выбирается детерминированно;
- cross_links строятся только по простым title mentions;
- structural_confidence агрегируется на уровне файла;
- diagnostics собирают file-level summary для дебага и rollout.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.structure.models import (
    ClauseTree,
    CrossDocumentLink,
    FileGraph,
    SegmentDocument,
    SEGMENT_TYPE_CONTRACT,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
)

logger = get_logger(__name__)


def build_file_graph(
    *,
    document_id: str,
    document_version_id: str | None,
    segments: list[SegmentDocument],
    segment_trees: list[ClauseTree],
) -> FileGraph:
    """
    Builds FileGraph from segment metadata and already-built segment trees.

    Для непрофессионального программиста:
    Эта функция не строит сами деревья.
    Она только собирает "общую картину файла" из уже готовых сегментов.

    На входе:
    - segments: список SegmentDocument, т.е. метаданные сегментов;
    - segment_trees: список ClauseTree для этих сегментов.

    На выходе:
    - FileGraph, который можно сохранить как file_graph.json.
    """
    safe_segments = [s for s in (segments or []) if s is not None]
    safe_trees = [t for t in (segment_trees or []) if t is not None]

    if not safe_segments:
        logger.warning(
            "STRUCTURE file_graph_builder: empty segments list",
            extra={"document_id": document_id},
        )

    primary_segment_id = _pick_primary_segment(safe_segments)
    _sync_primary_flags(safe_segments, primary_segment_id)

    cross_links = _extract_cross_links(safe_segments, safe_trees)
    degraded = any(bool(getattr(t, "degraded", False)) for t in safe_trees)
    structural_confidence = _derive_file_confidence(
        trees=safe_trees,
        primary_segment_id=primary_segment_id,
    )
    diagnostics = _build_file_graph_diagnostics(
        segments=safe_segments,
        trees=safe_trees,
        cross_links=cross_links,
        primary_segment_id=primary_segment_id,
    )

    graph = FileGraph(
        document_id=document_id,
        document_version_id=document_version_id,
        segments=safe_segments,
        cross_links=cross_links,
        primary_segment_id=primary_segment_id,
        degraded=degraded,
        structural_confidence=structural_confidence,
        diagnostics=diagnostics,
        schema_version="2.0",
    )

    logger.info(
        "STRUCTURE file_graph built",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "segments_count": len(safe_segments),
            "cross_links_count": len(cross_links),
            "primary_segment_id": primary_segment_id,
            "degraded": degraded,
            "structural_confidence": structural_confidence,
        },
    )

    return graph


def _pick_primary_segment(segments: list[SegmentDocument]) -> str | None:
    """
    Picks primary segment deterministically.

    Правило:
    0. если уже ровно один segment помечен is_primary=True — используем его
    1. contract с confidence=HIGH
    2. любой contract
    3. первый по segment_order
    """
    if not segments:
        return None

    marked_primary = [s for s in segments if s.is_primary]
    if len(marked_primary) == 1:
        return marked_primary[0].segment_id

    ordered_segments = sorted(segments, key=lambda s: (s.segment_order, s.segment_id))

    high_conf_contracts = [
        s
        for s in ordered_segments
        if s.segment_type == SEGMENT_TYPE_CONTRACT and str(s.confidence).upper() == "HIGH"
    ]
    if high_conf_contracts:
        return high_conf_contracts[0].segment_id

    any_contracts = [
        s
        for s in ordered_segments
        if s.segment_type == SEGMENT_TYPE_CONTRACT
    ]
    if any_contracts:
        return any_contracts[0].segment_id

    return ordered_segments[0].segment_id


def _sync_primary_flags(
    segments: list[SegmentDocument],
    primary_segment_id: str | None,
) -> None:
    """
    Делает SegmentDocument.is_primary согласованным с выбранным primary_segment_id.
    """
    for seg in segments:
        seg.is_primary = bool(primary_segment_id) and seg.segment_id == primary_segment_id


def _derive_file_confidence(
    *,
    trees: list[ClauseTree],
    primary_segment_id: str | None,
) -> str:
    """
    Агрегирует structural_confidence на уровне файла.

    Консервативная логика:
    - нет деревьев -> FAILED
    - primary FAILED -> FAILED
    - primary LOW -> LOW
    - primary degraded -> LOW
    - все degraded -> LOW
    - все HIGH и никто не degraded -> HIGH
    - primary HIGH -> HIGH
    - если среди trees есть FAILED, но primary не FAILED -> LOW
    - иначе MEDIUM
    """
    if not trees:
        return STRUCTURE_CONFIDENCE_FAILED

    tree_by_segment_id = {
        str(getattr(t, "segment_id", "") or ""): t
        for t in trees
        if getattr(t, "segment_id", None)
    }

    primary_tree = tree_by_segment_id.get(primary_segment_id or "")
    if primary_tree is None:
        primary_tree = next(
            (t for t in trees if bool(getattr(t, "is_primary_segment", False))),
            trees[0],
        )

    primary_conf = str(getattr(primary_tree, "structure_confidence", "") or "").upper()
    primary_degraded = bool(getattr(primary_tree, "degraded", False))
    all_degraded = all(bool(getattr(t, "degraded", False)) for t in trees)

    confidence_set = {
        str(getattr(t, "structure_confidence", "") or "").upper()
        for t in trees
    }

    if primary_conf == STRUCTURE_CONFIDENCE_FAILED:
        return STRUCTURE_CONFIDENCE_FAILED

    if primary_conf == STRUCTURE_CONFIDENCE_LOW:
        return STRUCTURE_CONFIDENCE_LOW

    if primary_degraded or all_degraded:
        return STRUCTURE_CONFIDENCE_LOW

    if confidence_set == {STRUCTURE_CONFIDENCE_HIGH}:
        return STRUCTURE_CONFIDENCE_HIGH

    if primary_conf == STRUCTURE_CONFIDENCE_HIGH:
        return STRUCTURE_CONFIDENCE_HIGH

    if STRUCTURE_CONFIDENCE_FAILED in confidence_set:
        return STRUCTURE_CONFIDENCE_LOW

    return STRUCTURE_CONFIDENCE_MEDIUM


def _build_file_graph_diagnostics(
    *,
    segments: list[SegmentDocument],
    trees: list[ClauseTree],
    cross_links: list[CrossDocumentLink],
    primary_segment_id: str | None,
) -> dict[str, Any]:
    """
    File-level diagnostics для отладки и rollout.
    """
    tree_by_segment_id = {
        str(getattr(t, "segment_id", "") or ""): t
        for t in trees
        if getattr(t, "segment_id", None)
    }

    degraded_segment_ids = [
        str(getattr(t, "segment_id", "") or "")
        for t in trees
        if bool(getattr(t, "degraded", False))
    ]

    segment_summaries: list[dict[str, Any]] = []
    for seg in segments:
        tree = tree_by_segment_id.get(seg.segment_id)
        segment_summaries.append(
            {
                "segment_id": seg.segment_id,
                "segment_order": seg.segment_order,
                "segment_type": seg.segment_type,
                "scope_name": seg.scope_name,
                "segment_confidence": seg.confidence,
                "segmentation_confidence_score": seg.segmentation_confidence_score,
                "segmentation_reasons": list(seg.segmentation_reasons or []),
                "is_primary": seg.is_primary,
                "tree_confidence": getattr(tree, "structure_confidence", None) if tree else None,
                "tree_degraded": bool(getattr(tree, "degraded", False)) if tree else None,
                "tree_scope_name": getattr(tree, "scope_name", None) if tree else None,
            }
        )

    return {
        "schema_version": "2.0",
        "segments_count": len(segments),
        "segment_types": [s.segment_type for s in segments],
        "segment_scopes": [s.scope_name for s in segments],
        "primary_segment_id": primary_segment_id,
        "primary_candidates_marked": [s.segment_id for s in segments if s.is_primary],
        "degraded_segments_count": len(degraded_segment_ids),
        "degraded_segment_ids": degraded_segment_ids,
        "cross_links_count": len(cross_links),
        "cross_link_types": sorted({lnk.link_type for lnk in cross_links}),
        "segment_summaries": segment_summaries,
    }


def _extract_cross_links(
    segments: list[SegmentDocument],
    trees: list[ClauseTree],
) -> list[CrossDocumentLink]:
    """
    v1 cross-link extraction.

    Для непрофессионального программиста:
    Сейчас это очень простая логика:
    если в тексте одного сегмента явно встречается title другого сегмента,
    считаем, что между ними есть слабая связь title_mention.

    Это НЕ полноценный semantic graph.
    Это просто первый безопасный слой, который можно улучшать позже.
    """
    if not segments or not trees:
        return []

    seg_by_id = {
        seg.segment_id: seg
        for seg in segments
        if seg.segment_id
    }

    links: list[CrossDocumentLink] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for tree in trees:
        source_segment_id = getattr(tree, "segment_id", None)
        if not source_segment_id:
            continue

        if source_segment_id not in seg_by_id:
            continue

        nodes_index = getattr(tree, "nodes_index", {}) or {}
        if not isinstance(nodes_index, dict):
            continue

        for node in nodes_index.values():
            node_text = (
                getattr(node, "subtree_text", None)
                or getattr(node, "own_text", None)
                or ""
            )
            if not node_text:
                continue

            text_lower = node_text.lower()

            for target_segment in segments:
                if not target_segment.segment_id:
                    continue
                if target_segment.segment_id == source_segment_id:
                    continue

                target_title = (target_segment.segment_title or "").strip()
                if not target_title:
                    continue
                if len(target_title) < 3:
                    continue

                if target_title.lower() not in text_lower:
                    continue

                dedup_key = (
                    source_segment_id,
                    target_segment.segment_id,
                    "title_mention",
                )
                if dedup_key in seen_keys:
                    continue

                links.append(
                    CrossDocumentLink(
                        source_segment_id=source_segment_id,
                        target_segment_id=target_segment.segment_id,
                        link_type="title_mention",
                        reference_text=target_title,
                        confidence=0.6,
                    )
                )
                seen_keys.add(dedup_key)

    return links

