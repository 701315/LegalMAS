"""
Trigger detector — loads trigger_definitions dynamically from YAML.

Each document type instruction file may contain a trigger_definitions section.
Triggers are string identifiers (e.g. "residential_property")
NOT hardcoded in Python Enums.
"""

import re

from .registry_loader import get_doc_type_config


def _is_trigger_active(trigger_cfg: dict, text_lower: str) -> bool:
    """Helper to check if a single trigger matches the text."""
    if not isinstance(trigger_cfg, dict):
        return False

    keywords = trigger_cfg.get("any_keywords", [])
    if not isinstance(keywords, list):
        return False

    # Проверяем каждое ключевое слово/паттерн
    for kw in keywords:
        kw_lower = kw.lower()
        # Если в ключевом слове есть спецсимволы регулярки (например, | или ( ),
        # используем re.search, иначе быстрый 'in'
        if any(c in kw_lower for c in ".+*?^$()[]{}|"):
            try:
                if re.search(kw_lower, text_lower):
                    return True
            except re.error:
                if kw_lower in text_lower:
                    return True
        elif kw_lower in text_lower:
            return True

    return False


def detect_triggers(
    registry: dict,
    text: str,
    doctype: str,
) -> list[str]:
    """
    Determines applicable conditional triggers for a specific doctype.
    """
    cfg = get_doc_type_config(registry, doctype)
    if not cfg:
        return []

    trigger_defs = cfg.get("trigger_definitions", {})
    if not trigger_defs:
        return []

    text_lower = text.lower()
    triggered: list[str] = []

    for trigger_name, trigger_cfg in trigger_defs.items():
        if _is_trigger_active(trigger_cfg, text_lower):
            triggered.append(trigger_name)

    return triggered


def detect_all_triggers(
    registry: dict,
    text: str,
) -> dict[str, list[str]]:
    """
    Detects triggers across ALL document types.
    Useful when doctype is UNKNOWN.
    """
    result: dict[str, list[str]] = {}
    text_lower = text.lower()  # Оптимизация: один раз для всего процесса

    for cfg in registry.get("document_types", []):
        doctype = cfg.get("type", "")
        trigger_defs = cfg.get("trigger_definitions", {})
        if not trigger_defs:
            continue

        triggered: list[str] = []
        for trigger_name, trigger_cfg in trigger_defs.items():
            if _is_trigger_active(trigger_cfg, text_lower):
                triggered.append(trigger_name)

        if triggered:
            result[doctype] = triggered

    return result
