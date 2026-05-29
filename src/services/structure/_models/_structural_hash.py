# src/services/structure/_models/_structural_hash.py

"""
Вычисление structural_hash для узлов иерархии.

structural_hash — content-independent идентификатор узла:
  - стабилен при OCR-вариациях текста заголовка
  - не зависит от raw text, embeddings, semantic metadata
  - детерминирован: одинаковый input → одинаковый hash
  - версионирован через STRUCTURAL_HASH_VERSION

Поля hash (зафиксированы в STRUCTURAL_HASH_FIELDS):
  normalized_path  — полный структурный путь от корня ("1.2.3")
  stable_level     — уровень вложенности (int)
  sibling_index    — порядковый номер среди siblings (0-based)
  scope_id         — canonical scope name

НЕ входит в hash: raw text, OCR wording, embeddings, semantic metadata.
"""

from __future__ import annotations

import hashlib
import json

from ._constants import STRUCTURAL_HASH_VERSION


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
        "v{STRUCTURAL_HASH_VERSION}:{sha256hex}" — строка длиной 67 символов.

    Raises:
        ValueError: если параметры невалидны.
    """
    if not normalized_path or not normalized_path.strip():
        raise ValueError("normalized_path must be non-empty")
    if stable_level < 1:
        raise ValueError(f"stable_level must be >= 1, got {stable_level}")
    if sibling_index < 0:
        raise ValueError(f"sibling_index must be >= 0, got {sibling_index}")
    if not scope_id or not scope_id.strip():
        raise ValueError("scope_id must be non-empty")

    payload = json.dumps(
        {
            "v": STRUCTURAL_HASH_VERSION,
            "path": normalized_path.strip(),
            "level": stable_level,
            "sibling": sibling_index,
            "scope": scope_id.strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    digest = hashlib.sha256(payload).hexdigest()
    return f"v{STRUCTURAL_HASH_VERSION}:{digest}"


def structural_hash_version(hash_str: str) -> int:
    """
    Извлечь версию из structural_hash строки.

    Raises:
        ValueError: если строка не соответствует формату.
    """
    if not hash_str or ":" not in hash_str:
        raise ValueError(f"Invalid structural_hash format: {hash_str!r}")
    prefix, _ = hash_str.split(":", 1)
    if not prefix.startswith("v"):
        raise ValueError(f"Invalid structural_hash prefix: {prefix!r}")
    try:
        return int(prefix[1:])
    except ValueError:
        raise ValueError(f"Invalid structural_hash version: {prefix!r}")
    
    