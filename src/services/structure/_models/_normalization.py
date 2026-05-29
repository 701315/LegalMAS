# src/services/structure/models/_normalization.py

"""
Приватные helper-функции для нормализации и валидации примитивных типов.

Используются внутри dataclass __post_init__. Не являются частью публичного API.
"""

from __future__ import annotations

from typing import Any

from ._constants import (
    DEFAULT_SCOPE,
    NODE_KIND_LEAF,
    PARSE_QUALITY_OK,
    SCOPE_NAME_RE,
    SEGMENT_CONFIDENCE_MEDIUM,
    SEGMENT_TYPE_UNKNOWN,
    STRUCTURE_CONFIDENCE_MEDIUM,
    TOC_CONFIDENCE_NONE,
    VALID_NODE_KINDS,
    VALID_PARSE_QUALITY_STATUS,
    VALID_RANGE_END_REASONS,
    VALID_SEGMENT_CONFIDENCE,
    VALID_SEGMENT_TYPES,
    VALID_STRUCTURE_CONFIDENCE,
    VALID_TOC_CONFIDENCE_BANDS,
)


def _norm_str(value: Any) -> str:
    return str(value or "").strip()


def _norm_opt_str(value: Any) -> str | None:
    normalized = _norm_str(value)
    return normalized or None


def _norm_bool(value: Any) -> bool:
    return bool(value)


def _norm_scope(value: Any) -> str:
    scope = _norm_opt_str(value)
    return scope or DEFAULT_SCOPE


def _normalize_structure_confidence(value: Any) -> str:
    confidence = _norm_str(value).upper() or STRUCTURE_CONFIDENCE_MEDIUM
    if confidence not in VALID_STRUCTURE_CONFIDENCE:
        raise ValueError(
            f"Invalid structure_confidence={confidence!r}. "
            f"Expected one of {sorted(VALID_STRUCTURE_CONFIDENCE)}"
        )
    return confidence


def _normalize_segment_confidence(value: Any) -> str:
    confidence = _norm_str(value).upper() or SEGMENT_CONFIDENCE_MEDIUM
    if confidence not in VALID_SEGMENT_CONFIDENCE:
        raise ValueError(
            f"Invalid segment confidence={confidence!r}. "
            f"Expected one of {sorted(VALID_SEGMENT_CONFIDENCE)}"
        )
    return confidence


def _normalize_segment_type(value: Any) -> str:
    segment_type = _norm_str(value).lower() or SEGMENT_TYPE_UNKNOWN
    if segment_type not in VALID_SEGMENT_TYPES:
        raise ValueError(
            f"Invalid segment_type={segment_type!r}. "
            f"Expected one of {sorted(VALID_SEGMENT_TYPES)}"
        )
    return segment_type


def _validate_scope_name(scope_name: str) -> str:
    normalized = _norm_scope(scope_name)
    if not SCOPE_NAME_RE.fullmatch(normalized):
        raise ValueError(
            f"Invalid scope_name={normalized!r}. "
            f"Expected ASCII snake_case matching [a-z0-9_]+"
        )
    return normalized


def _normalize_range_end_reason(value: Any) -> str | None:
    reason = _norm_opt_str(value)
    if reason is None:
        return None
    if reason not in VALID_RANGE_END_REASONS:
        raise ValueError(
            f"Invalid range_end_reason={reason!r}. "
            f"Expected one of {sorted(VALID_RANGE_END_REASONS)}"
        )
    return reason


def _normalize_node_kind(value: Any) -> str:
    node_kind = _norm_str(value).lower() or NODE_KIND_LEAF
    if node_kind not in VALID_NODE_KINDS:
        raise ValueError(
            f"Invalid node_kind={node_kind!r}. "
            f"Expected one of {sorted(VALID_NODE_KINDS)}"
        )
    return node_kind


def _normalize_toc_confidence_band(value: Any) -> str:
    band = _norm_str(value).lower() or TOC_CONFIDENCE_NONE
    if band not in VALID_TOC_CONFIDENCE_BANDS:
        raise ValueError(
            f"Invalid toc confidence band={band!r}. "
            f"Expected one of {sorted(VALID_TOC_CONFIDENCE_BANDS)}"
        )
    return band


def _normalize_parse_quality_status(value: Any) -> str:
    status = _norm_str(value).lower() or PARSE_QUALITY_OK
    if status not in VALID_PARSE_QUALITY_STATUS:
        raise ValueError(
            f"Invalid parse quality status={status!r}. "
            f"Expected one of {sorted(VALID_PARSE_QUALITY_STATUS)}"
        )
    return status


def _normalize_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be int-like, bool is not allowed")
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return normalized


def _normalize_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be int-like, bool is not allowed")
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return normalized


def _normalize_probability(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric, bool is not allowed")
    normalized = float(value)
    if not (0.0 <= normalized <= 1.0):
        raise ValueError(f"{field_name} must be in [0.0, 1.0]")
    return normalized


def _normalize_string_list(values: Any, field_name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    normalized: list[str] = []
    for idx, value in enumerate(values):
        item = _norm_str(value)
        if not item:
            raise ValueError(f"{field_name}[{idx}] must be non-empty")
        normalized.append(item)
    return normalized


def _normalize_unique_string_list(values: Any, field_name: str) -> list[str]:
    normalized = _normalize_string_list(values, field_name)
    seen: set[str] = set()
    unique: list[str] = []
    for item in normalized:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _normalize_string_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field_name} must be a list|tuple of strings")
    normalized: list[str] = []
    for idx, value in enumerate(values):
        item = _norm_str(value)
        if not item:
            raise ValueError(f"{field_name}[{idx}] must be non-empty")
        normalized.append(item)
    return tuple(normalized)


def _normalize_unique_string_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    normalized = _normalize_string_tuple(values, field_name)
    seen: set[str] = set()
    unique: list[str] = []
    for item in normalized:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return tuple(unique)


def _normalize_string_tuple_mapping(values: Any, field_name: str) -> dict[str, tuple[str, ...]]:
    raw = _ensure_dict(values, field_name)
    normalized: dict[str, tuple[str, ...]] = {}
    for key, val in raw.items():
        norm_key = _norm_str(key)
        if not norm_key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        normalized[norm_key] = _normalize_unique_string_tuple(
            val,
            f"{field_name}[{norm_key!r}]",
        )
    return normalized


def _ensure_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return dict(value)

