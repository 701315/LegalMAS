# src/services/structure/element_classifier/_logging.py

"""Логирование результатов классификации элементов."""

from __future__ import annotations

from typing import Any

from core.logging import get_logger

from ._config import ELEMENT_TYPE_TOC_HEADER, ELEMENT_TYPE_TOC_LINE, ELEMENT_TYPE_POSSIBLE_TOC
from ._toc_context import _TocContext

# Импорт semantic констант для диагностики
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_SECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM,
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING,
)


logger = get_logger(__name__)


def _log_classification_summary(
    *,
    document_id: str | None,
    classified: list[dict[str, Any]],
    toc_ctx: _TocContext,
    toc_fp_count: int = 0,
) -> None:
    """Логирует сводку результатов классификации.

    Args:
        document_id: Идентификатор документа (для трассировки)
        classified: Список классифицированных элементов
        toc_ctx: TOC-контекст
        toc_fp_count: Количество локальных false positive TOC элементов
    """
    counts: dict[str, int] = {}
    semantic_counts: dict[str, int] = {}

    for el in classified:
        et = str(el.get("element_type") or "unknown_layout")
        counts[et] = counts.get(et, 0) + 1

        # Считаем также semantic_element_type для diagnostics
        meta = el.get("metadata") or {}
        sem = str(meta.get("semantic_element_type") or "unknown")
        semantic_counts[sem] = semantic_counts.get(sem, 0) + 1

    toc_detected = bool(toc_ctx.toc_block and toc_ctx.toc_block.detected)
    toc_entries = len(toc_ctx.parsed_toc.entries) if toc_ctx.parsed_toc else 0

    logger.info(
        "STRUCTURE element classification completed",
        extra={
            "document_id": document_id,
            "elements_count": len(classified),
            "counts": counts,
            "semantic_counts": semantic_counts,
            "toc_detected": toc_detected,
            "toc_entries_parsed": toc_entries,
            "toc_source_indexes_count": len(toc_ctx.toc_source_indexes),
            "toc_header_count": counts.get(ELEMENT_TYPE_TOC_HEADER, 0),
            "toc_line_count": counts.get(ELEMENT_TYPE_TOC_LINE, 0),
            "possible_toc_count": counts.get(ELEMENT_TYPE_POSSIBLE_TOC, 0),
            "toc_false_positive_local_count": toc_fp_count,
            "semantic_section_heading_count": semantic_counts.get(SEMANTIC_ELEMENT_TYPE_SECTION_HEADING, 0),
            "semantic_subsection_heading_count": semantic_counts.get(SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING, 0),
            "semantic_definition_item_count": semantic_counts.get(SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM, 0),
            "semantic_appendix_heading_count": semantic_counts.get(SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING, 0),
            "note": "authoritative_guard_applied_later_in_pipeline",
        },
    )


