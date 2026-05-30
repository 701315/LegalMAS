# src/services/structure/models/_identity.py

"""
Доменные helper-функции для работы с идентификаторами и scope.

Здесь фиксируются canonical contracts для:
- effective_uid: "{scope}:{raw_uid}"
- scope naming
- deterministic segment_id generation

Важно:
- raw_uid в canonical effective_uid не должен содержать ":".
- функции этого модуля должны быть deterministic и side-effect free.
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

_EFFECTIVE_UID_DELIMITER = ":"
_SEGMENT_ID_NAMESPACE = uuid.NAMESPACE_URL


def _normalize_raw_uid(raw_uid: str) -> str:
    normalized_raw_uid = _norm_str(raw_uid)
    if not normalized_raw_uid:
        raise ValueError("raw_uid must be non-empty")
    if _EFFECTIVE_UID_DELIMITER in normalized_raw_uid:
        raise ValueError(
            f"raw_uid must not contain {_EFFECTIVE_UID_DELIMITER!r}: {raw_uid!r}"
        )
    return normalized_raw_uid


def make_effective_uid(scope: str, raw_uid: str) -> str:
    """Построить canonical effective_uid вида 'scope:raw_uid'."""
    normalized_scope = _validate_scope_name(scope)
    normalized_raw_uid = _normalize_raw_uid(raw_uid)
    return f"{normalized_scope}{_EFFECTIVE_UID_DELIMITER}{normalized_raw_uid}"


def split_effective_uid(effective_uid: str) -> tuple[str, str]:
    """Разобрать canonical effective_uid на (scope, raw_uid)."""
    normalized = _norm_str(effective_uid)
    if not normalized:
        raise ValueError("effective_uid must be non-empty")

    if _EFFECTIVE_UID_DELIMITER not in normalized:
        raise ValueError(
            f"Invalid effective_uid={normalized!r}. "
            f"Expected canonical 'scope{_EFFECTIVE_UID_DELIMITER}raw_uid' format"
        )

    scope, raw_uid = normalized.split(_EFFECTIVE_UID_DELIMITER, 1)
    scope = _validate_scope_name(scope)
    raw_uid = _normalize_raw_uid(raw_uid)
    return scope, raw_uid


def normalize_effective_uid(effective_uid: str) -> str:
    """
    Нормализовать existing effective_uid в canonical representation.

    Полезно для safe roundtrip:
        normalize_effective_uid(x) == make_effective_uid(*split_effective_uid(x))
    """
    scope, raw_uid = split_effective_uid(effective_uid)
    return make_effective_uid(scope, raw_uid)


def is_effective_uid(value: str) -> bool:
    """Проверить, является ли строка корректным canonical effective_uid."""
    try:
        normalize_effective_uid(value)
        return True
    except Exception:
        return False


def generate_scope_name(segment_type: str, segment_order: int) -> str:
    """
    Сгенерировать каноническое имя scope для сегмента.

    Правило:
    - "main_contract" для первого contract segment;
    - иначе "{segment_type}_{segment_order + 1}".
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
            _SEGMENT_ID_NAMESPACE,
            f"{normalized_document_id}::segment::{normalized_order}",
        )
    )




