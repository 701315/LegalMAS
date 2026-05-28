# src/services/structure/pipeline/_element_validation.py

"""
Валидация и нормализация элементов pipeline.

Содержит:
- очистку входных элементов
- проверку обязательного контракта
- нормализацию segment metadata
- защиту от битых сегментных диапазонов
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces
from services.structure.models import SegmentDocument

logger = get_logger(__name__)

_REQUIRED_ELEMENT_FIELDS = (
    "scope",
    "segment_id",
    "segment_type",
    "segment_order",
    "element_type",
)


def clean_elements(document_id: str, elements: list[dict] | None) -> list[dict]:
    """
    Оставляет только dict-элементы.
    """
    if elements is None or not isinstance(elements, list):
        logger.error(
            "STRUCTURE invalid elements input",
            extra={
                "document_id": document_id,
                "elements_is_none": elements is None,
                "elements_type": None if elements is None else type(elements).__name__,
            },
        )
        return []

    clean: list[dict] = []
    for i, el in enumerate(elements):
        if isinstance(el, dict):
            clean.append(el)
        else:
            logger.warning(
                "STRUCTURE non_dict_element_skipped",
                extra={
                    "document_id": document_id,
                    "element_index": i,
                    "element_type": type(el).__name__,
                },
            )
    return clean


def segment_slice_is_valid(seg: SegmentDocument, elements_count: int) -> bool:
    """
    Проверяет валидность диапазона segment.element_start/element_end.
    """
    return 0 <= seg.element_start <= seg.element_end <= elements_count


def validate_element_contract(
    *,
    document_id: str,
    segment_id: str | None,
    elements: list[dict],
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Проверяет обязательный контракт элемента.
    """
    violations: list[dict[str, Any]] = []

    for idx, el in enumerate(elements):
        missing = [field for field in _REQUIRED_ELEMENT_FIELDS if el.get(field) is None]
        if missing:
            violations.append(
                {
                    "elem_i": idx,
                    "page": el.get("page"),
                    "missing_fields": missing,
                    "text_sample": normalize_spaces(str(el.get("text") or ""))[:120],
                }
            )

    if violations:
        logger.error(
            "STRUCTURE element_contract_validation_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "violations_count": len(violations),
                "violations_preview": violations[:10],
            },
        )
        return False, violations

    return True, []


def ensure_element_segment_metadata(
    *,
    elements: list[dict],
    segment: SegmentDocument,
) -> list[dict]:
    """
    Гарантирует наличие segment metadata у каждого элемента.
    """
    prepared: list[dict] = []
    filled_count = 0

    for el in elements:
        normalized = dict(el)

        if not normalized.get("segment_id"):
            filled_count += 1
        normalized["segment_id"] = normalized.get("segment_id") or segment.segment_id

        normalized["segment_type"] = normalized.get("segment_type") or segment.segment_type
        normalized["segment_order"] = (
            normalized.get("segment_order")
            if normalized.get("segment_order") is not None
            else segment.segment_order
        )

        normalized["scope"] = normalized.get("scope") or segment.scope_name
        normalized["element_type"] = normalized.get("element_type") or "body_text"

        prepared.append(normalized)

    if filled_count:
        logger.warning(
            "STRUCTURE element_metadata_normalization_fallback",
            extra={
                "segment_id": segment.segment_id,
                "elements_count": len(elements),
                "filled_count": filled_count,
            },
        )

    return prepared
