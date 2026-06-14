# src/engine/content/_document_content_layout.py

"""
Внутренние helper-функции для извлечения текста из layout.

Модуль содержит только чистые функции, которые используются фасадом
DocumentContentService. Здесь нет работы с БД, storage, репозиториями
или логированием.
"""

from __future__ import annotations

import re
from typing import Any


def get_layout_total_pages(layout: dict[str, Any]) -> int | None:
    """
    Вернуть общее число страниц из metadata layout, если оно доступно.
    """
    layout_meta = layout.get("metadata") or {}
    total_pages: int | None = None

    for key in ("page_count", "pages", "num_pages", "total_pages"):
        value = layout_meta.get(key)
        if isinstance(value, int) and value > 0:
            total_pages = value
            break

    return total_pages


def extract_title_and_preamble_from_layout(
    layout: dict[str, Any],
    *,
    max_pages: int = 2,
    max_length: int = 1500,
) -> str | None:
    """
    Извлечь шапку документа напрямую из layout.
    """
    elements = layout.get("elements") or []
    if not elements:
        return None

    total_pages = get_layout_total_pages(layout)

    effective_max_pages = max_pages
    if total_pages is not None:
        effective_max_pages = 2 if total_pages <= 4 else 3

    header_elements: list[dict[str, Any]] = []

    for el in elements:
        page = el.get("page")
        if not isinstance(page, int) or page > effective_max_pages:
            continue

        text = (el.get("text") or "").strip()
        if not text:
            continue

        upper = text.upper()

        if "TABLE OF CONTENTS" in upper or "СОДЕРЖАНИЕ" in upper:
            break

        if re.match(r"^\d{1,2}(\.\d{1,2})*\.\s+.+", text):
            break

        header_elements.append(el)

    if not header_elements:
        return None

    parts: list[str] = []
    for el in header_elements:
        text = (el.get("text") or "").strip()
        if text:
            parts.append(text)

    full = "\n".join(parts).strip()
    if not full:
        return None

    if len(full) > max_length:
        full = full[:max_length]

    return full or None


def extract_snippet_from_layout(
    layout: dict[str, Any],
    *,
    skip_pages: int = 2,
    max_length: int = 1500,
    min_element_len: int = 40,
) -> tuple[str | None, int | None, int]:
    """
    Извлечь сниппет тела документа из layout и вернуть диагностические данные.

    Возвращает кортеж:
    - snippet;
    - total_pages;
    - effective_skip_pages.
    """
    elements = layout.get("elements") or []
    if not elements:
        return None, None, skip_pages

    total_pages = get_layout_total_pages(layout)

    if total_pages is not None:
        effective_skip_pages = 1 if total_pages <= 4 else 3
        effective_skip_pages = min(effective_skip_pages, max(0, total_pages - 1))
    else:
        effective_skip_pages = skip_pages

    parts: list[str] = []
    total_len = 0

    for el in elements:
        page = el.get("page")
        if isinstance(page, int) and page <= effective_skip_pages:
            continue

        text = (el.get("text") or "").strip()
        if len(text) < min_element_len:
            continue

        parts.append(text)
        total_len += len(text)

        if total_len >= max_length:
            break

    if not parts:
        return None, total_pages, effective_skip_pages

    snippet = "\n\n".join(parts).strip()
    if len(snippet) > max_length:
        snippet = snippet[:max_length]

    return snippet or None, total_pages, effective_skip_pages


