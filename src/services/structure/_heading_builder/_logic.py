# src/services/structure/_heading_builder/_logic.py

"""Логика проверки контрактов и специфических политик типов."""

from __future__ import annotations
from typing import Any
from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces
from ._constants import _REQUIRED_ELEMENT_FIELDS, _EXCLUDED_ELEMENT_TYPES, _ALLOWED_ELEMENT_TYPES
from ._utils import _normalize_scope

logger = get_logger(__name__)

def _require_element_structure_contract(element: dict[str, Any], elem_i: int, document_id: str) -> None:
    """Валидация наличия обязательных полей в элементе."""
    missing = [f for f in _REQUIRED_ELEMENT_FIELDS if element.get(f) is None]
    if missing:
        logger.error("STRUCTURE heading_builder_element_contract_violation", extra={
            "document_id": document_id, "elem_i": elem_i, "missing_fields": missing,
            "page": element.get("page"), "text_sample": normalize_spaces(str(element.get("text") or ""))[:160],
        })
        raise ValueError(f"Heading builder requires scope/segment metadata. Missing for #{elem_i}: {missing}")

def _element_scope(element: dict[str, Any]) -> str:
    """Извлечение scope из элемента."""
    scope = element.get("scope") or (element.get("metadata") or {}).get("scope")
    if scope is not None:
        return _normalize_scope(scope)
    raise ValueError("Element is missing required field 'scope'")

def _is_candidate_element_type_allowed(element_type: str) -> bool:
    """Проверка, разрешен ли тип элемента для создания кандидата."""
    norm = normalize_spaces(element_type).lower()
    if not norm: return False
    if norm == "toc_content": 
        logger.warning("STRUCTURE legacy_element_type_detected", extra={"element_type": norm})
    if norm in _EXCLUDED_ELEMENT_TYPES: return False
    return norm in _ALLOWED_ELEMENT_TYPES

def _is_strong_structural_element_type(element_type: str) -> bool:
    return normalize_spaces(element_type).lower() in {
        "heading_candidate", "section_heading", "subsection_heading", "appendix_heading"
    }

def _is_weak_structural_element_type(element_type: str) -> bool:
    return normalize_spaces(element_type).lower() in {
        "enumerated_clause", "definition_item", "list_item"
    }

def _is_recoverable_toc_like_element_type(element_type: str) -> bool:
    return normalize_spaces(element_type).lower() == "toc_false_positive"


