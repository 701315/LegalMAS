# src/services/structure/_models/_structural_hash.py

"""
Вычисление structural_hash для узлов иерархии.

structural_hash — content-independent идентификатор узла:
 - стабилен при OCR-вариациях текста заголовка
 - не зависит от raw text, embeddings, semantic metadata
 - детерминирован: одинаковый input → одинаковый hash
 - версионирован через STRUCTURAL_HASH_VERSION

Поля hash:
 - normalized_path  — полный структурный путь от корня ("1.2.3")
 - stable_level     — уровень вложенности (int)
 - sibling_index    — порядковый номер среди siblings (0-based)
 - scope_id         — canonical scope name

НЕ входит в hash:
 - raw text
 - OCR wording
 - embeddings
 - semantic metadata
"""

from __future__ import annotations

import hashlib
import json
import re

from ._constants import STRUCTURAL_HASH_VERSION

_STRUCTURAL_HASH_PREFIX = "v"
_STRUCTURAL_HASH_DIGEST_LENGTH = 64
_STRUCTURAL_HASH_RE = re.compile(r"^v(?P<version>\d+):(?P<digest>[0-9a-f]{64})$")


def _normalize_non_empty_str(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str, got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _normalize_positive_int(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{field_name} must be >= 1, got {value}")
    return value


def _normalize_non_negative_int(value: int, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value}")
    return value


def compute_structural_hash(
    *,
    normalized_path: str,
    stable_level: int,
    sibling_index: int,
    scope_id: str,
) -> str:
    """
    Вычислить structural_hash узла.

    Returns:
        "v{STRUCTURAL_HASH_VERSION}:{sha256hex}"

    Raises:
        ValueError: если параметры невалидны.
    """
    normalized_path = _normalize_non_empty_str(normalized_path, "normalized_path")
    stable_level = _normalize_positive_int(stable_level, "stable_level")
    sibling_index = _normalize_non_negative_int(sibling_index, "sibling_index")
    scope_id = _normalize_non_empty_str(scope_id, "scope_id")

    payload = json.dumps(
        {
            "v": STRUCTURAL_HASH_VERSION,
            "path": normalized_path,
            "level": stable_level,
            "sibling": sibling_index,
            "scope": scope_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    digest = hashlib.sha256(payload).hexdigest()
    return f"{_STRUCTURAL_HASH_PREFIX}{STRUCTURAL_HASH_VERSION}:{digest}"


def parse_structural_hash(hash_str: str) -> tuple[int, str]:
    """
    Разобрать structural_hash на (version, digest).

    Raises:
        ValueError: если строка не соответствует canonical structural_hash format.
    """
    normalized = _normalize_non_empty_str(hash_str, "hash_str")
    match = _STRUCTURAL_HASH_RE.fullmatch(normalized)
    if not match:
        raise ValueError(f"Invalid structural_hash format: {hash_str!r}")

    version = int(match.group("version"))
    digest = match.group("digest")

    if len(digest) != _STRUCTURAL_HASH_DIGEST_LENGTH:
        raise ValueError(
            f"Invalid structural_hash digest length: {len(digest)} "
            f"(expected {_STRUCTURAL_HASH_DIGEST_LENGTH})"
        )

    return version, digest


def structural_hash_version(hash_str: str) -> int:
    """
    Извлечь версию из structural_hash строки.

    Raises:
        ValueError: если строка не соответствует формату.
    """
    version, _digest = parse_structural_hash(hash_str)
    return version


def is_structural_hash(hash_str: str) -> bool:
    """
    Проверить, является ли строка корректным structural_hash.
    """
    try:
        parse_structural_hash(hash_str)
        return True
    except Exception:
        return False
    
    
    