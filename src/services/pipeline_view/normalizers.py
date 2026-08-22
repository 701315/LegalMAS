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
    Возвращает канонический текст узла clause tree для STRUCTURE view.

    Приоритет задаёт contract hierarchy v3/v4:
    1. subtree_text — полный текст узла, включая дочерние секции;
    2. own_text — текст, непосредственно принадлежащий самому узлу;
    3. legacy-поля — обратная совместимость со старыми tree artifacts.

    Функция не зависит от CHUNKS и не должна создавать/обогащать текст:
    она только безопасно проецирует текст, уже сохранённый в clause tree.
    """
    if not isinstance(node, dict):
        return ""

    candidates = (
        # Canonical FrozenHierarchyNode.to_dict() contract.
        node.get("subtree_text"),
        node.get("own_text"),

        # Legacy / compatibility tree contracts.
        node.get("structure_text"),
        node.get("text"),
        node.get("content"),
        node.get("body"),
        node.get("clauseText"),
        node.get("normalized_text"),
        node.get("raw_text"),
    )

    for value in candidates:
        if value is None:
            continue

        text = value.strip() if isinstance(value, str) else str(value).strip()
        if text:
            return text

    return ""
