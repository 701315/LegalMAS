# src/services/structure/pipeline/_degraded_fallback.py

"""
Degraded fallback builder.

Строит технический ClauseTree из равномерных чанков,
если структура документа невалидна или качество недостаточно.
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from core.logging import get_logger
from services.structure.models import (
    ClauseNode,
    ClauseTree,
    STRUCTURE_CONFIDENCE_LOW,
    make_effective_uid,
)

from ._utils import stable_element_id

logger = get_logger(__name__)


def degraded_tree(
    document_id: str,
    elements: list[dict],
    coverage: float = 0.0,
    *,
    structure_confidence: str = STRUCTURE_CONFIDENCE_LOW,
    diagnostics: dict[str, Any] | None = None,
    scope_name: str = "main_contract",
    segment_id: str | None = None,
    segment_type: str | None = None,
    segment_title: str | None = None,
    segment_page_range: tuple[int, int] | None = None,
    segment_order: int | None = None,
    is_primary_segment: bool = False,
) -> ClauseTree:
    """
    Строит fallback ClauseTree.
    """
    chunks: list[ClauseNode] = []

    current_ids: list[str] = []
    current_text_parts: list[str] = []
    current_tokens = 0
    chunk_idx = 1

    max_tokens = settings.STRUCTURE_DEGRADED_CHUNK_TOKENS
    current_start_page: int | None = None
    last_page: int = elements[0].get("page", 1) if elements else 1

    def flush_chunk():
        nonlocal chunk_idx, current_ids, current_text_parts, current_tokens, current_start_page

        if not current_ids:
            return

        start_page = current_start_page or last_page
        end_page = last_page
        own_text = " ".join(current_text_parts) if current_text_parts else None

        raw_uid = str(chunk_idx)
        effective_uid = make_effective_uid(scope_name, raw_uid)

        node = ClauseNode(
            effective_uid=effective_uid,
            raw_uid=raw_uid,
            scope=scope_name,
            title=f"Chunk {chunk_idx}",
            level=1,
            node_kind="leaf",
            own_element_ids=list(current_ids),
            subtree_element_ids=list(current_ids),
            own_text=own_text,
            subtree_text=own_text,
            start_page=start_page,
            end_page=end_page,
            children=[],
            range_end_reason="segment_end",
            diagnostics={"degraded_chunk": True},
        )

        chunks.append(node)

        chunk_idx += 1
        current_ids = []
        current_text_parts = []
        current_tokens = 0
        current_start_page = None

    for idx, el in enumerate(elements):
        text = el.get("text", "")
        tokens = len(str(text or "").split())
        page = el.get("page", 1)

        if current_tokens + tokens > max_tokens and current_ids:
            flush_chunk()

        current_ids.append(stable_element_id(el, idx))
        if str(text or "").strip():
            current_text_parts.append(str(text).strip())

        current_tokens += tokens
        if current_start_page is None:
            current_start_page = page
        last_page = page

    flush_chunk()

    diagnostics = dict(diagnostics or {})
    diagnostics.setdefault("quality_gates", {})
    diagnostics["quality_gates"].update(
        {
            "section_chunking_allowed": False,
            "technical_fallback_only": True,
            "structure_confidence": structure_confidence,
        }
    )

    return ClauseTree(
        document_id=document_id,
        root=chunks,
        references_index=[],
        structure_confidence=structure_confidence,
        degraded=True,
        nodes_index={node.effective_uid: node for node in chunks},
        structure_diagnostics=diagnostics,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        segment_page_range=segment_page_range,
        segment_order=segment_order,
        scope_name=scope_name,
        is_primary_segment=is_primary_segment,
        schema_version="3.0",
    )

