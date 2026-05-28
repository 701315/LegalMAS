# src/services/pipeline_view/normalizers.py

"""
Вспомогательные функции нормализации для pipeline view.

Чистые функции без side-effects — используются всеми stage-билдерами.
"""

from __future__ import annotations

from typing import Any


def normalize_uid(value: Any) -> str | None:
    """Нормализует clause_uid: strip + пустая строка → None."""
    if value is None:
        return None
    uid = str(value).strip()
    return uid or None


def normalize_title(value: Any) -> str:
    """Нормализует заголовок секции: strip + fallback на 'Untitled section'."""
    if value is None:
        return "Untitled section"
    title = str(value).strip()
    return title or "Untitled section"


def normalize_int(value: Any) -> int | None:
    """Безопасно приводит к int или возвращает None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def chunk_sort_key(ch: dict[str, Any]) -> tuple[float, int, str]:
    """
    Ключ сортировки чанков: position_ratio → start_page → chunk_id.

    Используется для детерминированного порядка чанков внутри одного clause_uid.
    """
    meta = ch.get("metadata") or {}
    pos = meta.get("position_ratio")
    start_page = meta.get("start_page")
    chunk_id = str(ch.get("id") or "")
    return (
        float(pos) if isinstance(pos, int | float) else 1.0,
        int(start_page) if isinstance(start_page, int) else 10**9,
        chunk_id,
    )


def extract_clause_tree_text(node: dict[str, Any]) -> str:
    """
    Достаёт canonical текст секции из clause tree с поддержкой нескольких ключей.

    Это source of truth для canonical STRUCTURE-view;
    не зависит от CHUNKS; безопасен для разных форматов tree.to_dict().
    """
    candidates = [
        node.get("text"),
        node.get("content"),
        node.get("body"),
        node.get("clauseText"),
        node.get("normalized_text"),
        node.get("raw_text"),
    ]

    for value in candidates:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        elif value is not None:
            text = str(value).strip()
            if text:
                return text

    return ""
