# src/engine/content/chunk_ids.py

"""
Canonical chunk ID generation for Sprint 3.

ВАЖНО:
- Chunk ID строится только от effective_uid.
- Нет fallback на raw_uid или любые другие альтернативные identity.
- Если effective_uid отсутствует, это structural anomaly, а не нормальный путь.

Canonical contract:
- effective_uid имеет формат "scope:raw_uid";
- scope должен быть валидным ASCII snake-case / a-z0-9;
- raw_uid должен быть непустым;
- generated IDs должны быть детерминированными и стабильными.

Этот модуль специально держим маленьким и чистым:
- только нормализация identity;
- только deterministic builders;
- без БД, без storage, без побочных эффектов.
"""

from __future__ import annotations

import re
import uuid
from typing import Final


_SCOPE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]+$")
_SECTION_RAW_UID_PREFIX: Final[str] = "section::"


def _normalize_str(value: object) -> str:
    """
    Нормализовать произвольное значение в trimmed string.

    Для непрофессионального программиста:
    - None превращается в пустую строку;
    - всё остальное приводится к str и trim().
    """
    return str(value or "").strip()


def _normalize_doc_id(doc_id: uuid.UUID | str) -> str:
    """
    Нормализовать document id в строку UUID.

    Принимаем как uuid.UUID, так и строку, чтобы модуль был удобен
    в чистых helper'ах и тестах.
    """
    if isinstance(doc_id, uuid.UUID):
        return str(doc_id)

    raw = _normalize_str(doc_id)
    if not raw:
        raise ValueError("doc_id must be non-empty")

    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"doc_id must be a valid UUID, got {raw!r}") from exc


def _validate_scope_name(scope: str) -> str:
    """
    Проверить scope name по canonical contract.

    Формат должен совпадать с моделью структуры:
    - только [a-z0-9_]
    - непустая строка
    """
    normalized = _normalize_str(scope)
    if not normalized:
        raise ValueError("scope must be non-empty")
    if not _SCOPE_RE.fullmatch(normalized):
        raise ValueError(
            f"Invalid scope {normalized!r}. Expected ASCII snake-case matching [a-z0-9_]+"
        )
    return normalized


def _normalize_raw_uid(raw_uid: object) -> str:
    """
    Нормализовать raw_uid и проверить, что он непустой.
    """
    normalized = _normalize_str(raw_uid)
    if not normalized:
        raise ValueError("raw_uid must be non-empty")
    return normalized


def split_effective_uid(effective_uid: str) -> tuple[str, str]:
    """
    Разобрать canonical effective_uid на (scope, raw_uid).

    Canonical format:
        "scope:raw_uid"

    ВАЖНО:
    - делим только по первому двоеточию;
    - raw_uid может содержать дополнительные ':' внутри synthetic identity;
    - это совместимо с section raw uid вида "section::title-slug".
    """
    normalized = _normalize_str(effective_uid)
    if not normalized:
        raise ValueError("effective_uid must be non-empty")

    if ":" not in normalized:
        raise ValueError(
            f"Invalid effective_uid {normalized!r}. Expected canonical 'scope:raw_uid' format"
        )

    scope, raw_uid = normalized.split(":", 1)
    scope = _validate_scope_name(scope)
    raw_uid = _normalize_raw_uid(raw_uid)
    return scope, raw_uid


def validate_effective_uid(effective_uid: str) -> str:
    """
    Провалидировать canonical effective_uid и вернуть его в нормализованном виде.

    Если строка не соответствует contract, возбуждаем ValueError.
    """
    scope, raw_uid = split_effective_uid(effective_uid)
    return f"{scope}:{raw_uid}"


def make_effective_uid(scope: str, raw_uid: str) -> str:
    """
    Собрать canonical effective_uid из scope и raw_uid.

    Формат:
        "scope:raw_uid"
    """
    normalized_scope = _validate_scope_name(scope)
    normalized_raw_uid = _normalize_raw_uid(raw_uid)
    return f"{normalized_scope}:{normalized_raw_uid}"


def _slugify_section_title(section_title: str) -> str:
    """
    Стабильно нормализовать title раздела для synthetic raw_uid.

    Принципы:
    - lower();
    - '/' превращаем в пробел, чтобы не лепить path-like identity;
    - оставляем латиницу, кириллицу, цифры, '_', '-', пробел;
    - сжимаем пробелы в '-';
    - если title пустой после нормализации — используем 'untitled-section'.
    """
    title = _normalize_str(section_title).lower()
    if not title:
        raise ValueError("section_title must be non-empty")

    title = title.replace("/", " ")
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"[^a-zа-я0-9\-\s_]", "", title)
    title = re.sub(r"\s+", "-", title)
    title = title.strip("-_ ")

    return title or "untitled-section"


def build_section_raw_uid(section_title: str) -> str:
    """
    Построить synthetic raw_uid для section node/chunk.

    Пример:
        "section::price-terms"
    """
    slug = _slugify_section_title(section_title)
    return f"{_SECTION_RAW_UID_PREFIX}{slug}"


def build_section_effective_uid(scope: str, section_title: str) -> str:
    """
    Построить canonical effective_uid для synthetic section chunk.

    Пример:
        "maincontract:section::price-terms"
    """
    raw_uid = build_section_raw_uid(section_title)
    return make_effective_uid(scope=scope, raw_uid=raw_uid)


def _build_chunk_id(
    *,
    doc_id: uuid.UUID | str,
    effective_uid: str,
    kind: str,
    suffix: str | None = None,
) -> str:
    """
    Общий deterministic builder для canonical chunk IDs.

    Формат:
        leaf:      <doc_id>:clause:<effective_uid>
        section:   <doc_id>:section:<effective_uid>
        subclause: <doc_id>:subclause:<effective_uid>:<subchunk_index>

    Почему добавляем kind:
    - leaf/section раньше могли совпасть по doc_id + effective_uid;
    - явный kind делает id namespace-safe и понятнее в логах/отладке;
    - id остаётся детерминированным.

    suffix используется только там, где нужно адресовать дочерний под-чанк.
    """
    normalized_doc_id = _normalize_doc_id(doc_id)
    normalized_effective_uid = validate_effective_uid(effective_uid)

    normalized_kind = _normalize_str(kind).lower()
    if not normalized_kind:
        raise ValueError("kind must be non-empty")

    base = f"{normalized_doc_id}:{normalized_kind}:{normalized_effective_uid}"
    if suffix is None:
        return base

    normalized_suffix = _normalize_str(suffix)
    if not normalized_suffix:
        raise ValueError("suffix must be non-empty when provided")

    return f"{base}:{normalized_suffix}"


def build_leaf_chunk_id(doc_id: uuid.UUID | str, effective_uid: str) -> str:
    """
    Построить canonical chunk ID для leaf clause chunk.

    Args:
        doc_id: Document UUID
        effective_uid: Canonical node identity ("scope:raw_uid")

    Returns:
        Deterministic chunk ID
    """
    return _build_chunk_id(
        doc_id=doc_id,
        effective_uid=effective_uid,
        kind="clause",
    )


def build_section_chunk_id(doc_id: uuid.UUID | str, effective_uid: str) -> str:
    """
    Построить canonical chunk ID для section chunk.

    Args:
        doc_id: Document UUID
        effective_uid: Canonical node identity ("scope:raw_uid")

    Returns:
        Deterministic chunk ID
    """
    return _build_chunk_id(
        doc_id=doc_id,
        effective_uid=effective_uid,
        kind="section",
    )


def build_subclause_chunk_id(
    doc_id: uuid.UUID | str,
    effective_uid: str,
    subchunk_index: int,
) -> str:
    """
    Построить canonical chunk ID для subclause chunk.

    Args:
        doc_id: Document UUID
        effective_uid: Canonical node identity ("scope:raw_uid")
        subchunk_index: Index of subchunk within parent clause

    Returns:
        Deterministic chunk ID
    """
    if not isinstance(subchunk_index, int):
        raise ValueError("subchunk_index must be int")
    if subchunk_index < 0:
        raise ValueError("subchunk_index must be >= 0")

    return _build_chunk_id(
        doc_id=doc_id,
        effective_uid=effective_uid,
        kind="subclause",
        suffix=str(subchunk_index),
    )

