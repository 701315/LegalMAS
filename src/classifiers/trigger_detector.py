# src/classifiers/trigger_detector.py

"""
TriggerDetector — определение активных триггеров по тексту документа.

Назначение:
- Прочитать из YAML-конфигураций блок trigger_definitions для типа документа.
- По содержимому текста понять, какие триггеры «сработали».
- Вернуть список строковых идентификаторов триггеров (например, "residential_property"),
  без жёсткой привязки к Python Enum.

Где используется:
- При известном типе документа (doctype) — для выбора условных проверок
  (например, включать ли проверки для сельхозземель, ипотеки, маткапитала и т.п.).
- При неизвестном типе — можно пробежать по всем типам и понять,
  какие триггеры потенциально актуальны (detect_all_triggers).

Формат trigger_definitions в YAML:
- Для каждого триггера задаётся словарь с ключом any_keywords:
    trigger_definitions:
      residential_property:
        any_keywords:
          - "квартира"
          - "жилой дом"
          - "комната"
      land_plot_sale:
        any_keywords:
          - "земельный участок"
          - "категория земель"

- Значения в any_keywords могут быть:
    * простыми подстроками (поиск через "in"),
    * либо полноценными regex-выражениями (тогда используется re.search).

Принцип работы:
- Если хотя бы одно ключевое слово/паттерн из any_keywords нашлось в тексте,
  триггер считается активным.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .registry_loader import get_doc_type_config


def _is_trigger_active(trigger_cfg: dict, text_lower: str) -> bool:
    """
    Проверить, сработал ли один конкретный триггер на данном тексте.

    Параметры:
    - trigger_cfg: словарь конфигурации триггера из YAML (ожидается ключ any_keywords).
    - text_lower : текст документа в нижнем регистре.

    Возвращает:
    - True, если хоть одно ключевое слово/паттерн совпало с текстом.
    - False, если конфигурация некорректна или совпадений нет.
    """
    if not isinstance(trigger_cfg, dict):
        return False

    keywords = trigger_cfg.get("any_keywords", [])
    if not isinstance(keywords, list):
        return False

    # Проверяем каждое ключевое слово/паттерн
    for kw in keywords:
        if not isinstance(kw, str):
            continue

        kw_lower = kw.lower()

        # Если в строке есть спецсимволы регулярки (., +, *, ?, ^, $, (), [], {}, |),
        # пытаемся трактовать её как регулярное выражение.
        if any(c in kw_lower for c in ".+*?^$()[]{}|"):
            try:
                if re.search(kw_lower, text_lower):
                    return True
            except re.error:
                # Если regex некорректен, делаем простой подстрочный поиск, чтобы не терять сигнал.
                if kw_lower in text_lower:
                    return True
        else:
            # Обычный, быстрый поиск подстроки
            if kw_lower in text_lower:
                return True

    return False


def detect_triggers(
    registry: dict,
    text: str,
    doctype: str,
) -> List[str]:
    """
    Определить, какие триггеры активны для конкретного типа документа.

    Параметры:
    - registry: результат загрузки реестра (load_registry).
    - text    : полный текст документа (или репрезентативный фрагмент).
    - doctype : код типа документа (например, "contract_1.6_real_estate").

    Возвращает:
    - список имён триггеров (строки), которые сработали для данного текста и типа.
    - пустой список, если:
        * тип не найден в реестре,
        * у типа нет trigger_definitions,
        * или ни один триггер не сработал.
    """
    cfg = get_doc_type_config(registry, doctype)
    if not cfg:
        return []

    trigger_defs = cfg.get("trigger_definitions", {})
    if not trigger_defs or not isinstance(trigger_defs, dict):
        return []

    text_lower = (text or "").lower()
    triggered: List[str] = []

    for trigger_name, trigger_cfg in trigger_defs.items():
        if _is_trigger_active(trigger_cfg, text_lower):
            triggered.append(trigger_name)

    return triggered


def detect_all_triggers(
    registry: dict,
    text: str,
) -> Dict[str, List[str]]:
    """
    Определить активные триггеры сразу для ВСЕХ типов документов.

    Полезно, когда:
    - doctype ещё не определён (UNKNOWN),
    - но нужно понять, какие правовые сюжеты потенциально затронуты
      (например, ипотека, маткапитал, наследство, сельхозземли).

    Параметры:
    - registry: результат загрузки реестра (load_registry).
    - text    : полный текст документа (или репрезентативный фрагмент).

    Возвращает:
    - словарь вида:
        {
          "<doctype_1>": ["trigger_a", "trigger_b"],
          "<doctype_2>": ["trigger_c"],
          ...
        }
      Только те типы, у которых реально нашли активные триггеры.
    """
    result: Dict[str, List[str]] = {}
    text_lower = (text or "").lower()  # Оптимизация: приводим к нижнему регистру один раз

    for cfg in registry.get("document_types", []):
        doctype = cfg.get("type", "")
        if not doctype:
            continue

        trigger_defs = cfg.get("trigger_definitions", {})
        if not trigger_defs or not isinstance(trigger_defs, dict):
            continue

        triggered: List[str] = []
        for trigger_name, trigger_cfg in trigger_defs.items():
            if _is_trigger_active(trigger_cfg, text_lower):
                triggered.append(trigger_name)

        if triggered:
            result[doctype] = triggered

    return result
