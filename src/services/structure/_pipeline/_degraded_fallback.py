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
from services.structure.crossrefs import build_cross_reference_graph
from services.structure.models import (
    STRUCTURE_CONFIDENCE_LOW,
    ClauseTree,
    MutableHierarchyNode,
    freeze,
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
    chunks: list[MutableHierarchyNode] = []
    element_to_effective_uid: dict[str, str] = {}

    current_ids: list[str] = []
    current_text_parts: list[str] = []
    current_tokens = 0
    chunk_idx = 1

    max_tokens = settings.STRUCTURE_DEGRADED_CHUNK_TOKENS
    current_start_page: int | None = None
    last_page: int = elements[0].get("page", 1) if elements else 1

    diagnostics = dict(diagnostics or {})
    quality_gates = diagnostics.setdefault("quality_gates", {})
    fallback_info = diagnostics.setdefault("fallback", {})
    recovery_report = diagnostics.setdefault("recovery_report", {})

    fallback_reason = (
        str(quality_gates.get("fallback_reason") or "").strip()
        or str(fallback_info.get("reason") or "").strip()
        or "technical_fallback"
    )
    quality_gate_mode = str(quality_gates.get("quality_gate_mode") or "BLOCK_AND_FALLBACK").strip()
    source_mode = str(fallback_info.get("source_mode") or "pipeline_fallback").strip()

    def flush_chunk() -> None:
        nonlocal chunk_idx, current_ids, current_text_parts, current_tokens, current_start_page

        if not current_ids:
            return

        start_page = current_start_page or last_page
        end_page = last_page
        own_text = " ".join(current_text_parts) if current_text_parts else None

        raw_uid = str(chunk_idx)
        effective_uid = make_effective_uid(scope_name, raw_uid)

        node = MutableHierarchyNode(
            effective_uid=effective_uid,
            raw_uid=raw_uid,
            scope=scope_name,
            title=f"[TECHNICAL FALLBACK] Fragment {chunk_idx}",
            level=1,
            node_kind="leaf",
            node_origin="technical_fallback",
            content_mode="technical_fragment",
            citability="technical",
            own_element_ids=list(current_ids),
            subtree_element_ids=list(current_ids),
            own_text=own_text,
            subtree_text=own_text,
            start_page=start_page,
            end_page=end_page,
            children=[],
            range_end_reason="segment_end",
            diagnostics={
                "degraded_chunk": True,
                "fallback_reason": fallback_reason,
                "fallback_mode": "technical_fallback",
                "quality_gate_mode": quality_gate_mode,
                "source_mode": source_mode,
                "user_facing_semantic": False,
                "semantic_equivalent": False,
                "technical_fragment": True,
                "chunk_index": chunk_idx,
                "chunk_token_budget": max_tokens,
            },
        )
        node.compute_and_set_structural_hash(
            normalized_path=f"technical-fallback-{raw_uid}",
            sibling_index=chunk_idx - 1,
        )

        for element_id in current_ids:
            element_to_effective_uid[element_id] = effective_uid

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

        current_id = stable_element_id(el, idx)
        current_ids.append(current_id)

        if str(text or "").strip():
            current_text_parts.append(str(text).strip())

        current_tokens += tokens
        if current_start_page is None:
            current_start_page = page
        last_page = page

    flush_chunk()

    quality_gates.update(
        {
            "section_chunking_allowed": False,
            "technical_fallback_only": True,
            "structure_confidence": structure_confidence,
            "coverage": coverage,
            "fallback_mode": "technical_fallback",
            "fallback_chunk_count": len(chunks),
            "semantic_tree_preserved_despite_low_confidence": False,
        }
    )

    fallback_info.update(
        {
            "mode": "technical_fallback",
            "reason": fallback_reason,
            "chunk_count": len(chunks),
            "scope_name": scope_name,
            "semantic_tree_preserved": False,
            "user_facing_semantic": False,
            "technical_only": True,
            "quality_gate_mode": quality_gate_mode,
            "source_mode": source_mode,
        }
    )

    recovery_report.setdefault("mode", "technical_fallback")
    recovery_report.setdefault("reasons", [fallback_reason])
    recovery_report.setdefault("patched_nodes", 0)
    recovery_report.setdefault("fallback_nodes", len(chunks))

    diagnostics["technical_fallback_contract"] = {
        "fallback_nodes_are_semantic": False,
        "fallback_nodes_are_citable": False,
        "fallback_unit_kind": "technical_fragment",
        "user_facing_titles_are_technical": True,
        "crossref_resolution_scope": "best_effort_only",
    }

    frozen_chunks = [freeze(node) for node in chunks]
    nodes_index = {node.effective_uid: node for node in frozen_chunks}

    cross_reference_graph = build_cross_reference_graph(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes_index,
        document_id=document_id,
        stable_element_id_resolver=stable_element_id,
    )

    logger.info(
        "STRUCTURE degraded_fallback_built",
        extra={
            "document_id": document_id,
            "scope_name": scope_name,
            "segment_id": segment_id,
            "fallback_reason": fallback_reason,
            "quality_gate_mode": quality_gate_mode,
            "chunk_count": len(chunks),
            "coverage": round(float(coverage or 0.0), 4),
            "structure_confidence": structure_confidence,
        },
    )

    return ClauseTree(
        document_id=document_id,
        root=frozen_chunks,
        cross_reference_graph=cross_reference_graph,
        structure_confidence=structure_confidence,
        degraded=True,
        nodes_index=nodes_index,
        structure_diagnostics=diagnostics,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        segment_page_range=segment_page_range,
        segment_order=segment_order,
        scope_name=scope_name,
        is_primary_segment=is_primary_segment,
        schema_version="4.0",
    )



