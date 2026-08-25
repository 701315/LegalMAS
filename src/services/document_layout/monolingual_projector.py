# src/services/document_layout/monolingual_projector.py

"""
Monolingual Projector Module (Phase 4 / Layer 8 v3.2 Final).

Формирует одноязычную проекцию из составных структурных узлов:
- Фильтрация по target_language + shared;
- Исключение узлов противоположного языка при наличии целевого узла;
- Перенос маркеров от выровненных узлов противоположного языка (v3.2);
- Safe-split для mixed-узлов;
- Гарантия наличия маркера в начале текста элемента (v3.2);
- 100% трассируемость маркеров.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.parallel_alignment import AlignmentResult
from services.document_layout.schemas import (
    MarkerTrace,
    ProjectedElement,
    StructuralNodeCandidate,
    UnresolvedMixedAtom,
)
from services.document_layout.span_splitter import SpanSplitter
from services.document_layout.marker_recovery import _extract_marker_from_text

logger = get_logger(__name__)


@dataclass(slots=True)
class ProjectionResult:
    elements: list[ProjectedElement] = field(default_factory=list)
    unresolved_mixed_atoms: list[UnresolvedMixedAtom] = field(default_factory=list)
    marker_trace: MarkerTrace = field(default_factory=MarkerTrace)
    source_atom_count: int = 0
    projected_atom_count: int = 0
    projected_marker_only_atom_count: int = 0
    shared_atoms_included: int = 0
    mixed_atoms_resolved: int = 0
    mixed_atoms_unresolved: int = 0


def _ensure_marker_in_text(text: str, marker: str | None) -> str:
    """
    Гарантирует, что маркер физически присутствует в начале текста элемента.
    Если маркер есть, а текст начинается со слов — приклеивает его.
    """
    if not marker:
        return text

    stripped_text = text.strip()
    stripped_marker = marker.strip()

    if not stripped_text:
        return stripped_marker

    # Если текст уже начинается с этого маркера — ничего не делаем
    if stripped_text.startswith(stripped_marker):
        return text

    # Если маркер числовой (например "5.8") или буквенный ("(a)")
    # и текст начинается с другой цифры/буквы — приклеиваем
    return f"{stripped_marker} {text}"


class MonolingualProjector:
    def __init__(self, splitter: SpanSplitter | None = None):
        self.splitter = splitter or SpanSplitter()

    def project_nodes(
        self,
        nodes: list[StructuralNodeCandidate],
        target_language: str,
        alignment_result: AlignmentResult | None = None,
    ) -> ProjectionResult:
        target_lang = target_language.lower().strip()
        result = ProjectionResult(source_atom_count=len(nodes))

        if not nodes:
            return result

        logger.info(
            "Starting monolingual node projection",
            target_language=target_lang,
            total_nodes=len(nodes),
        )

        aligned_opp_node_ids = (
            alignment_result.aligned_opposite_node_ids if alignment_result else set()
        )

        # v3.2: Строим карту переноса маркеров от выровненных узлов
        # противоположного языка к целевым узлам (Marker Propagation)
        marker_transfer: dict[str, str] = {}
        if alignment_result:
            for pair in alignment_result.aligned_pairs:
                if pair.marker:
                    existing = marker_transfer.get(pair.target_node_id)
                    if not existing:
                        marker_transfer[pair.target_node_id] = pair.marker

        projected_elements: list[ProjectedElement] = []
        unresolved_mixed: list[UnresolvedMixedAtom] = []

        for idx, node in enumerate(nodes):
            raw_type = layout_config.label_to_raw_type.get(node.label, "text")
            if node.marker and raw_type == "text":
                raw_type = "list_item"

            # Универсальное извлечение маркера из текста если нет в node.marker
            if not node.marker and node.text:
                extracted_marker = _extract_marker_from_text(node.text)
                if extracted_marker:
                    node.marker = extracted_marker

            # 1. Нативный узел целевого языка
            if node.language == target_lang:
                effective_marker = node.marker
                if not effective_marker and node.node_id in marker_transfer:
                    effective_marker = marker_transfer[node.node_id]

                # Гарантируем наличие маркера в начале текста для качественного RAG и LLM-детекции
                projected_text = _ensure_marker_in_text(node.text, effective_marker)

                el_id = f"{target_lang}:{node.node_id}"
                projected_el = ProjectedElement(
                    element_id=el_id,
                    source_element_ids=node.source_atom_ids,
                    text=projected_text,
                    page=node.page,
                    reading_order=idx,
                    reading_order_source="structural_nodes",
                    layout_order_confidence="validated",
                    type=raw_type,
                    label=node.label if node.label else "paragraph",
                    marker=effective_marker,
                    is_marker_only=False,
                    bbox=node.bbox,
                    parent_ref=node.region_id,
                    language=target_lang,
                    needs_review=False,
                    projection_method="native_language_node",
                    projection_confidence=node.confidence,
                    font_size=node.font_size,
                    bold=node.bold,
                    style=node.style,
                    region_id=node.region_id,
                    hierarchy_path=node.hierarchy_path,
                    metadata=dict(getattr(node, "metadata", {}) or {}),
                )
                projected_elements.append(projected_el)
                if effective_marker:
                    result.marker_trace.projected += 1

            # 2. Shared узел (формулы, чистые цифры, нейтральный контент)
            elif node.language == "shared":
                effective_marker = node.marker
                if not effective_marker and node.node_id in marker_transfer:
                    effective_marker = marker_transfer[node.node_id]

                projected_text = _ensure_marker_in_text(node.text, effective_marker)

                el_id = f"{target_lang}:shared:{node.node_id}"
                projected_el = ProjectedElement(
                    element_id=el_id,
                    source_element_ids=node.source_atom_ids,
                    text=projected_text,
                    page=node.page,
                    reading_order=idx,
                    reading_order_source="structural_nodes",
                    layout_order_confidence="validated",
                    type=raw_type,
                    label="paragraph" if raw_type == "text" else "list_item",
                    marker=effective_marker,
                    is_marker_only=False,
                    bbox=node.bbox,
                    parent_ref=node.region_id,
                    language="shared",
                    needs_review=False,
                    projection_method="shared_node",
                    projection_confidence=1.0,
                    font_size=node.font_size,
                    bold=node.bold,
                    style=node.style,
                    region_id=node.region_id,
                    hierarchy_path=node.hierarchy_path,
                    metadata=dict(getattr(node, "metadata", {}) or {}),
                )
                projected_elements.append(projected_el)
                result.shared_atoms_included += 1
                if effective_marker:
                    result.marker_trace.projected += 1

            # 3. Mixed узел (двуязычная строка)
            elif node.language == "mixed":
                split_res = self.splitter.split_span(node.text, target_lang)

                if split_res.is_split_successful and split_res.target_text:
                    effective_marker = node.marker
                    projected_text = _ensure_marker_in_text(split_res.target_text, effective_marker)

                    el_id = f"{target_lang}:split:{node.node_id}"
                    projected_el = ProjectedElement(
                        element_id=el_id,
                        source_element_ids=node.source_atom_ids,
                        text=projected_text,
                        page=node.page,
                        reading_order=idx,
                        reading_order_source="structural_nodes",
                        layout_order_confidence="validated",
                        type=raw_type,
                        label="paragraph" if raw_type == "text" else "list_item",
                        marker=effective_marker,
                        is_marker_only=False,
                        bbox=node.bbox,
                        parent_ref=node.region_id,
                        language=target_lang,
                        needs_review=False,
                        projection_method=split_res.split_method,
                        projection_confidence=split_res.confidence,
                        font_size=node.font_size,
                        bold=node.bold,
                        style=node.style,
                        region_id=node.region_id,
                        hierarchy_path=node.hierarchy_path,
                        metadata=dict(getattr(node, "metadata", {}) or {}),
                    )
                    projected_elements.append(projected_el)
                    result.mixed_atoms_resolved += 1
                    if effective_marker:
                        result.marker_trace.projected += 1
                else:
                    el_id = f"{target_lang}:mixed:{node.node_id}"
                    projected_el = ProjectedElement(
                        element_id=el_id,
                        source_element_ids=node.source_atom_ids,
                        text=node.text,
                        page=node.page,
                        reading_order=idx,
                        reading_order_source="structural_nodes",
                        layout_order_confidence="validated",
                        type=raw_type,
                        label="paragraph" if raw_type == "text" else "list_item",
                        marker=node.marker,
                        is_marker_only=False,
                        bbox=node.bbox,
                        parent_ref=node.region_id,
                        language="mixed",
                        needs_review=True,
                        projection_method="unresolved_mixed",
                        projection_confidence=0.50,
                        font_size=node.font_size,
                        bold=node.bold,
                        style=node.style,
                        region_id=node.region_id,
                        hierarchy_path=node.hierarchy_path,
                        metadata=dict(getattr(node, "metadata", {}) or {}),
                    )
                    projected_elements.append(projected_el)
                    result.mixed_atoms_unresolved += 1
                    unresolved_mixed.append(
                        UnresolvedMixedAtom(
                            element_id=node.node_id,
                            text=node.text,
                            language="mixed",
                            reason="low_split_confidence",
                        )
                    )

            # 4. Узел противоположного языка
            else:
                if node.node_id in aligned_opp_node_ids:
                    result.marker_trace.excluded_with_reason += 1
                else:
                    if node.marker:
                        marker_el_id = f"{target_lang}:marker:{node.node_id}"
                        marker_el = ProjectedElement(
                            element_id=marker_el_id,
                            source_element_ids=node.source_atom_ids,
                            text="",
                            page=node.page,
                            reading_order=idx,
                            reading_order_source="structural_nodes",
                            layout_order_confidence="validated",
                            type="list_item",
                            label="list_item",
                            marker=node.marker,
                            is_marker_only=True,
                            bbox=node.bbox,
                            parent_ref=node.region_id,
                            language="shared",
                            needs_review=True,
                            projection_method="preserved_marker_without_target_text",
                            projection_confidence=1.0,
                            font_size=node.font_size,
                            bold=node.bold,
                            style=node.style,
                            region_id=node.region_id,
                            hierarchy_path=node.hierarchy_path,
                            metadata=dict(getattr(node, "metadata", {}) or {}),
                        )
                        projected_elements.append(marker_el)
                        result.marker_trace.projected += 1
                        result.projected_marker_only_atom_count += 1
                    else:
                        result.marker_trace.excluded_with_reason += 1

        projected_elements.sort(key=lambda el: (el.page, el.reading_order))

        result.elements = projected_elements
        result.unresolved_mixed_atoms = unresolved_mixed
        result.projected_atom_count = len(projected_elements)

        logger.info(
            "Monolingual node projection completed (Dual-Hypothesis v3.2)",
            target_language=target_lang,
            projected_elements=result.projected_atom_count,
            marker_only_elements=result.projected_marker_only_atom_count,
            markers_transferred=len(marker_transfer),
        )

        return result


