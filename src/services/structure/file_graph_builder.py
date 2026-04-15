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

Сейчас v1-логика очень консервативная:
- primary_segment_id выбирается детерминированно;
- cross_links строятся только по простым title mentions;
- если сигналов нет, cross_links = [].
"""

from __future__ import annotations

from core.logging import get_logger
from services.structure.models import (
    ClauseTree,
    CrossDocumentLink,
    FileGraph,
    SegmentDocument,
    SEGMENT_TYPE_CONTRACT,
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
    cross_links = _extract_cross_links(safe_segments, safe_trees)
    degraded = any(bool(t.degraded) for t in safe_trees)

    graph = FileGraph(
        document_id=document_id,
        document_version_id=document_version_id,
        segments=safe_segments,
        cross_links=cross_links,
        primary_segment_id=primary_segment_id,
        degraded=degraded,
        schema_version="1.0",
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
        },
    )

    return graph


def _pick_primary_segment(segments: list[SegmentDocument]) -> str | None:
    """
    Picks primary segment deterministically.

    Правило:
    1. contract с confidence=HIGH
    2. любой contract
    3. первый по segment_order
    """
    if not segments:
        return None

    ordered_segments = sorted(segments, key=lambda s: (s.segment_order, s.segment_id))

    high_conf_contracts = [
        s for s in ordered_segments
        if s.segment_type == SEGMENT_TYPE_CONTRACT and str(s.confidence).upper() == "HIGH"
    ]
    if high_conf_contracts:
        return high_conf_contracts[0].segment_id

    any_contracts = [
        s for s in ordered_segments
        if s.segment_type == SEGMENT_TYPE_CONTRACT
    ]
    if any_contracts:
        return any_contracts[0].segment_id

    return ordered_segments[0].segment_id


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

        source_segment = seg_by_id.get(source_segment_id)
        if not source_segment:
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

