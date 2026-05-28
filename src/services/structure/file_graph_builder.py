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
    SEGMENT_TYPE_CONTRACT,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
    ClauseTree,
    CrossDocumentLink,
    FileGraph,
    SegmentDocument,
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

    validation = _validate_graph_inputs(
        document_id=document_id,
        segments=safe_segments,
        trees=safe_trees,
    )

    primary_segment_id = _pick_primary_segment(safe_segments)
    _sync_primary_flags(safe_segments, primary_segment_id)

    cross_links = _extract_cross_links(safe_segments, safe_trees)
    degraded = bool(validation["has_errors"]) or any(
        bool(getattr(t, "degraded", False)) for t in safe_trees
    )
    structural_confidence = _derive_file_confidence(
        trees=safe_trees,
        primary_segment_id=primary_segment_id,
        validation_has_errors=bool(validation["has_errors"]),
    )
    diagnostics = _build_file_graph_diagnostics(
        segments=safe_segments,
        trees=safe_trees,
        cross_links=cross_links,
        primary_segment_id=primary_segment_id,
        validation=validation,
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
        schema_version="3.0",
    )

    logger.info(
        "STRUCTURE file_graph built",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "segments_count": len(safe_segments),
            "trees_count": len(safe_trees),
            "cross_links_count": len(cross_links),
            "primary_segment_id": primary_segment_id,
            "degraded": degraded,
            "structural_confidence": structural_confidence,
            "validation_errors_count": len(validation["errors"]),
        },
    )

    return graph


def _validate_graph_inputs(
    *,
    document_id: str,
    segments: list[SegmentDocument],
    trees: list[ClauseTree],
) -> dict[str, Any]:
    """
    Проверяет согласованность segments и segment_trees до сборки FileGraph.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    segment_ids = [seg.segment_id for seg in segments if getattr(seg, "segment_id", None)]
    tree_ids = [tree.segment_id for tree in trees if getattr(tree, "segment_id", None)]

    duplicate_segment_ids = sorted(
        {seg_id for seg_id in segment_ids if segment_ids.count(seg_id) > 1}
    )
    duplicate_tree_ids = sorted({tree_id for tree_id in tree_ids if tree_ids.count(tree_id) > 1})

    if duplicate_segment_ids:
        errors.append(
            {
                "type": "duplicate_segment_ids",
                "segment_ids": duplicate_segment_ids,
            }
        )

    if duplicate_tree_ids:
        errors.append(
            {
                "type": "duplicate_tree_ids",
                "segment_ids": duplicate_tree_ids,
            }
        )

    segment_id_set = set(segment_ids)
    tree_id_set = set(tree_ids)

    missing_trees = sorted(segment_id_set - tree_id_set)
    extra_trees = sorted(tree_id_set - segment_id_set)

    if missing_trees:
        errors.append(
            {
                "type": "missing_trees_for_segments",
                "segment_ids": missing_trees,
            }
        )

    if extra_trees:
        errors.append(
            {
                "type": "trees_without_segments",
                "segment_ids": extra_trees,
            }
        )

    if len(segments) != len(trees):
        warnings.append(
            {
                "type": "count_mismatch",
                "segments_count": len(segments),
                "trees_count": len(trees),
            }
        )

    for seg in segments:
        if not seg.segment_id:
            errors.append({"type": "segment_missing_id", "segment_order": seg.segment_order})
        if not seg.scope_name:
            errors.append({"type": "segment_missing_scope", "segment_id": seg.segment_id})

    for tree in trees:
        if not getattr(tree, "segment_id", None):
            errors.append({"type": "tree_missing_segment_id"})
            continue

        matching_segment = next(
            (seg for seg in segments if seg.segment_id == tree.segment_id), None
        )
        if matching_segment is None:
            continue

        tree_scope_name = getattr(tree, "scope_name", None)
        if (
            tree_scope_name
            and matching_segment.scope_name
            and tree_scope_name != matching_segment.scope_name
        ):
            errors.append(
                {
                    "type": "scope_mismatch",
                    "segment_id": tree.segment_id,
                    "segment_scope_name": matching_segment.scope_name,
                    "tree_scope_name": tree_scope_name,
                }
            )

    if errors or warnings:
        logger.warning(
            "STRUCTURE file_graph_input_validation",
            extra={
                "document_id": document_id,
                "errors_count": len(errors),
                "warnings_count": len(warnings),
                "errors_preview": errors[:10],
                "warnings_preview": warnings[:10],
            },
        )

    return {
        "has_errors": bool(errors),
        "errors": errors,
        "warnings": warnings,
    }


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

    any_contracts = [s for s in ordered_segments if s.segment_type == SEGMENT_TYPE_CONTRACT]
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
    validation_has_errors: bool,
) -> str:
    """
    Агрегирует structural_confidence на уровне файла.

    Консервативная логика:
    - validation errors -> FAILED
    - нет деревьев -> FAILED
    - primary FAILED -> FAILED
    - primary LOW -> LOW
    - primary degraded -> LOW
    - любой FAILED вне primary -> LOW
    - все degraded -> LOW
    - все HIGH и никто не degraded -> HIGH
    - primary HIGH + есть LOW/MEDIUM -> MEDIUM
    - иначе MEDIUM
    """
    if validation_has_errors:
        return STRUCTURE_CONFIDENCE_FAILED

    if not trees:
        return STRUCTURE_CONFIDENCE_FAILED

    tree_by_segment_id = {
        str(getattr(t, "segment_id", "") or ""): t for t in trees if getattr(t, "segment_id", None)
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

    confidence_set = {str(getattr(t, "structure_confidence", "") or "").upper() for t in trees}

    if primary_conf == STRUCTURE_CONFIDENCE_FAILED:
        return STRUCTURE_CONFIDENCE_FAILED

    if primary_conf == STRUCTURE_CONFIDENCE_LOW:
        return STRUCTURE_CONFIDENCE_LOW

    if primary_degraded or all_degraded:
        return STRUCTURE_CONFIDENCE_LOW

    if STRUCTURE_CONFIDENCE_FAILED in confidence_set:
        return STRUCTURE_CONFIDENCE_LOW

    if confidence_set == {STRUCTURE_CONFIDENCE_HIGH} and not any(
        bool(getattr(t, "degraded", False)) for t in trees
    ):
        return STRUCTURE_CONFIDENCE_HIGH

    if primary_conf == STRUCTURE_CONFIDENCE_HIGH:
        return STRUCTURE_CONFIDENCE_MEDIUM

    return STRUCTURE_CONFIDENCE_MEDIUM


def _build_file_graph_diagnostics(
    *,
    segments: list[SegmentDocument],
    trees: list[ClauseTree],
    cross_links: list[CrossDocumentLink],
    primary_segment_id: str | None,
    validation: dict[str, Any],
) -> dict[str, Any]:
    """
    File-level diagnostics для отладки и rollout.
    """
    tree_by_segment_id = {
        str(getattr(t, "segment_id", "") or ""): t for t in trees if getattr(t, "segment_id", None)
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
                "tree_schema_version": getattr(tree, "schema_version", None) if tree else None,
            }
        )

    return {
        "schema_version": "3.0",
        "segments_count": len(segments),
        "trees_count": len(trees),
        "segment_types": [s.segment_type for s in segments],
        "segment_scopes": [s.scope_name for s in segments],
        "primary_segment_id": primary_segment_id,
        "primary_candidates_marked": [s.segment_id for s in segments if s.is_primary],
        "degraded_segments_count": len(degraded_segment_ids),
        "degraded_segment_ids": degraded_segment_ids,
        "cross_links_count": len(cross_links),
        "cross_link_types": sorted({lnk.link_type for lnk in cross_links}),
        "validation": validation,
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
    """
    if not segments or not trees:
        return []

    seg_by_id = {seg.segment_id: seg for seg in segments if seg.segment_id}

    links: list[CrossDocumentLink] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for tree in trees:
        source_segment_id = getattr(tree, "segment_id", None)
        if not source_segment_id:
            continue

        source_segment = seg_by_id.get(source_segment_id)
        if source_segment is None:
            logger.warning(
                "STRUCTURE file_graph_crosslink_tree_without_segment",
                extra={"source_segment_id": source_segment_id},
            )
            continue

        nodes_index = getattr(tree, "nodes_index", {}) or {}
        if not isinstance(nodes_index, dict):
            continue

        for node in nodes_index.values():
            node_text = getattr(node, "subtree_text", None) or getattr(node, "own_text", None) or ""
            if not node_text:
                continue

            text_lower = node_text.lower()

            for target_segment in segments:
                if not target_segment.segment_id:
                    continue
                if target_segment.segment_id == source_segment_id:
                    continue

                target_title = (target_segment.segment_title or "").strip()
                if not target_title or len(target_title) < 3:
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
