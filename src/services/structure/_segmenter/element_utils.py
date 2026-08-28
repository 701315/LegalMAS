# src/services/structure/_segmenter/element_utils.py

"""
Safe-accessors и element-type предикаты для элементов layout.

Предоставляет безопасные обёртки для чтения полей элементов
и предикаты классификации, используемые во всех модулях сегментации.
"""

from __future__ import annotations

from typing import Any


def safe_page(element: dict[str, Any]) -> int:
    """Безопасно извлекает номер страницы элемента."""
    page = element.get("page", 1)
    try:
        return int(page or 1)
    except Exception:
        return 1


def element_type(element: dict[str, Any]) -> str:
    """Возвращает нормализованный element_type."""
    return str(element.get("element_type") or "").strip().lower()


def is_non_boundary_element_type(element: dict[str, Any]) -> bool:
    """Элемент с таким типом не может быть границей сегмента.
    
    Исключение: PDF-парсер явно распознал элемент как заголовок (raw_type/raw_label).
    
    Это защищает заголовки разделов/приложений от ложной блокировки,
    когда классификатор присвоил им неверный element_type.
    
    Сигнал от PDF-парсера (raw_type='heading') имеет приоритет над эвристикой классификатора.
    """
    from core.logging import get_logger
    
    et = element_type(element)
    
    # Проверяем raw_type/raw_label от PDF-парсера — это наиболее доверенный сигнал
    # Работает для любого element_type (table_content, body_text, etc.)
    raw_type = str(element.get("type") or "").strip().lower()
    raw_label = str(element.get("label") or "").strip().lower()
    
    if raw_type in ("heading", "title") or raw_label in ("section_header", "appendix_header"):
        text = str(element.get("text", "") or "").strip()
        logger = get_logger(__name__)
        logger.debug(
            "SEGMENTER non_boundary_override_by_raw_type",
            extra={
                "element_type": et,
                "element_text_preview": text[:80],
                "raw_type": raw_type,
                "raw_label": raw_label,
            },
        )
        return False
    
    return et in {
        "signature_block",
        "requisites_block",
        "toc_content",
        "toc_header",
        "toc_line",
        "possible_toc",
        "page_artifact",
        "table_content",
        "unknown_layout",
    }


def is_heading_candidate_element(element: dict[str, Any]) -> bool:
    """Элемент помечен как heading candidate."""
    return element_type(element) == "heading_candidate"


def is_list_item_element(element: dict[str, Any]) -> bool:
    """Элемент помечен как list item."""
    return element_type(element) == "list_item"


def page_offset(elements: list[dict[str, Any]], index: int) -> int:
    """Количество элементов на той же странице перед текущим элементом.

    Если ``page_offset == 0``, элемент — первый на своей странице.
    """
    current_page = safe_page(elements[index])
    offset = 0
    for i in range(index - 1, -1, -1):
        if safe_page(elements[i]) != current_page:
            break
        offset += 1
    return offset


