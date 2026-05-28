# src/services/structure/pipeline/_utils.py

"""
Базовые утилиты структурного pipeline.

Содержит:
- timing-логирование
- стабильный element_id
- вычисление page range
- numeric UID проверки
"""

from __future__ import annotations

import re
import time
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces

logger = get_logger(__name__)

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")


def log_timing(label: str, start: float, **extra: Any) -> None:
    """
    Логирует длительность выполнения этапа pipeline.
    """
    elapsed = time.perf_counter() - start
    logger.info(
        f"STRUCTURE timing: {label}",
        extra={"elapsed_sec": round(elapsed, 4), **extra},
    )


def stable_element_id(element: dict[str, Any], fallback_index: int) -> str:
    """
    Возвращает стабильный element_id.

    Если element_id присутствует — используется он.
    Иначе строится детерминированный fallback.
    """
    element_id = str(element.get("element_id") or "").strip()
    if element_id:
        return element_id

    page = element.get("page", 1)
    bbox = element.get("bbox") or [0, 0, 0, 0]
    text = normalize_spaces(element.get("text", ""))

    x0 = bbox[0] if len(bbox) > 0 else 0
    top = bbox[1] if len(bbox) > 1 else 0

    return f"fallback:{page}:{x0}:{top}:{fallback_index}:{text[:32]}"


def pages_for_elements(elements: list[dict]) -> tuple[int, int]:
    """
    Возвращает (page_start, page_end) для списка элементов.
    """
    pages = [el.get("page", 1) for el in elements if isinstance(el.get("page"), int)]
    if not pages:
        return 1, 1
    return min(pages), max(pages)


def is_numeric_uid(uid: str) -> bool:
    """
    Проверяет, соответствует ли UID формату 1.2.3
    """
    return bool(_NUMERIC_UID_RE.fullmatch(str(uid or "").strip()))
