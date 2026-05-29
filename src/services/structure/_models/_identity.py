# src/services/structure/models/_identity.py

"""
Доменные helper-функции для работы с идентификаторами и scope.
"""

from __future__ import annotations

import uuid

from ._constants import DEFAULT_SCOPE, SEGMENT_TYPE_CONTRACT
from ._normalization import (
    _norm_str,
    _normalize_non_negative_int,
    _normalize_segment_type,
    _validate_scope_name,
)


def make_effective_uid(scope: str, raw_uid: str) -> str:
    """Построить canonical effective_uid вида 'scope:raw_uid'."""
    normalized_scope = _validate_scope_name(scope)
    normalized_raw_uid = _norm_str(raw_uid)
    if not normalized_raw_uid:
        raise ValueError("raw_uid must be non-empty to build effective_uid")
    return f"{normalized_scope}:{normalized_raw_uid}"


def split_effective_uid(effective_uid: str) -> tuple[str, str]:
    """Разобрать canonical effective_uid на (scope, raw_uid)."""
    normalized = _norm_str(effective_uid)
    if not normalized:
        raise ValueError("effective_uid must be non-empty")
    if ":" not in normalized:
        raise ValueError(
            f"Invalid effective_uid={normalized!r}. "
            "Expected canonical 'scope:raw_uid' format"
        )
    scope, raw_uid = normalized.split(":", 1)
    scope = _validate_scope_name(scope)
    raw_uid = _norm_str(raw_uid)
    if not raw_uid:
        raise ValueError("effective_uid must contain non-empty raw uid")
    return scope, raw_uid


def generate_scope_name(segment_type: str, segment_order: int) -> str:
    """
    Сгенерировать каноническое имя scope для сегмента.

    "main_contract" для первого contract, иначе "{type}_{order+1}".
    """
    normalized_type = _normalize_segment_type(segment_type)
    normalized_order = _normalize_non_negative_int(segment_order, "segment_order")
    if normalized_type == SEGMENT_TYPE_CONTRACT and normalized_order == 0:
        return DEFAULT_SCOPE
    return f"{normalized_type}_{normalized_order + 1}"


def make_segment_id(document_id: str, segment_order: int) -> str:
    """
    Построить стабильный segment_id — UUID v5, детерминированный для одинакового input.
    """
    normalized_document_id = _norm_str(document_id)
    if not normalized_document_id:
        raise ValueError("document_id must be non-empty to build segment_id")
    normalized_order = _normalize_non_negative_int(segment_order, "segment_order")
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{normalized_document_id}::segment::{normalized_order}",
        )
    )


