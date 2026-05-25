"""
Общие helper-функции для TOC-to-heading matching.

Роль модуля:
- хранить shared normalization policy для TOC/title lookup;
- предоставлять единый lookup helper для scorer и builder;
- исключить дублирование логики между heading_scoring.py и heading_builder.py.

Важно:
- модуль не занимается fuzzy matching;
- модуль не считает score;
- модуль не принимает решений accepted / rejected / ambiguous;
- модуль только нормализует ключи и извлекает payload из toc_match_index.

Главный принцип:
builder и scorer должны использовать один и тот же deterministic lookup contract.
"""

from __future__ import annotations

import re
from typing import Any

from services.structure.heading_patterns import normalize_spaces


def normalize_toc_match_title(text: str) -> str:
    """
    Нормализует heading title для lookup в TOC match index.

    Политика нормализации должна быть максимально совместима с matcher-level key:
    - collapse spaces;
    - casefold;
    - удаление punctuation noise;
    - trim.

    Возвращает стабильную строку, пригодную для deterministic dict lookup.
    """
    normalized = normalize_spaces(str(text or "")).casefold()
    normalized = re.sub(r"[^\w\s]+", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def toc_match_payload(
    *,
    raw_uid: str | None,
    title: str | None,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """
    Возвращает payload из toc_match_index для heading candidate.

    Lookup выполняется по ключу:
    - normalized raw_uid
    - normalized title

    Если toc_match_index отсутствует или точного ключа нет, возвращает None.

    Args:
        raw_uid: Исходный heading uid.
        title: Heading title.
        toc_match_index: Индекс, построенный из ParsedTOC после matching.

    Returns:
        dict[str, Any] | None: Payload для scorer/builder diagnostics.
    """
    if not toc_match_index:
        return None

    key = (
        normalize_spaces(raw_uid or ""),
        normalize_toc_match_title(title or ""),
    )
    return toc_match_index.get(key)


