# src/classifiers/registry_loader.py

"""
Загрузчик реестра типов документов (registry_loader).

Назначение:
- Поднять в память реестр всех типов документов из YAML-инструкций.
- Объединить два уровня описания:
  1) registry.yaml — индекс типов (type, name, category, group).
  2) <type>.yaml  — детальные инструкции по каждому типу.

Форматы YAML:
- Поддерживаются два варианта разметки правил классификации:
  1) Плоский формат:
       rules: ...
       filename_patterns: ...
       trigger_definitions: ...
  2) Вложенный формат:
       classification_runtime_v1:
         rules: ...
         filename_patterns: ...
         trigger_definitions: ...

Результат:
- На выходе получаем единый словарь:
    {
      "document_types": [
        {
          "type": "...",
          "name": "...",
          "rules": {...},                # нормализованные правила
          "filename_patterns": [...],
          "folder_patterns": [...],
          "trigger_definitions": {...},
          "weights": {...},
          "party_roles": [...],
          "essential_terms": [...],
          "section_markers": [...],
          "aliases": [...],
          "classification_runtime_v1": {...},   # исходные блоки не теряются
          "validation_engine_v3_2": {...},
          ...
        },
        ...
      ]
    }

Кеширование:
- Функция load_registry использует lru_cache(maxsize=1) — реестр грузится один раз
  и переиспользуется всеми потребителями (LLM-классификатор, валидация, отчёты).
- В тестах можно вызвать load_registry.cache_clear(), чтобы принудительно
  перезагрузить реестр после изменения YAML.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import yaml

from core.logging import get_logger

logger = get_logger(__name__)


def _extract_classification_fields(detail: Dict[str, Any]) -> Dict[str, Any]:
    """
    Вытащить из YAML-файла только поля, связанные с классификацией.

    Поддерживает оба варианта схемы:
      - плоский (rules/filename_patterns/trigger_definitions на верхнем уровне),
      - вложенный (внутри блока classification_runtime_v1).

    На выходе возвращает словарь с унифицированными ключами:
      - rules              : словарь с keywords/phrases/exclusions и др.
      - filename_patterns  : список паттернов для имени файла
      - folder_patterns    : список паттернов для пути к папке
      - trigger_definitions: словарь триггеров по типу документа
      - weights            : веса правил (если заданы)
      - party_roles        : роли сторон (из validation_engine)
      - essential_terms    : ключевые элементы договора
      - section_markers    : маркеры структурных разделов
      - aliases            : синонимы/альтернативные названия
    """
    runtime = detail.get("classification_runtime_v1", {}) or {}

    # --- rules (keywords, phrases, exclusions) ---
    # Если есть runtime.rules — используем его, иначе берём detail.rules.
    rules = detail.get("rules") or runtime.get("rules", {}) or {}

    # --- filename/folder patterns (могут лежать в rules или на верхнем уровне) ---
    filename_patterns = (
        detail.get("filename_patterns")
        or runtime.get("filename_patterns")
        or rules.get("filename_patterns", [])
    )
    folder_patterns = (
        detail.get("folder_patterns")
        or runtime.get("folder_patterns")
        or rules.get("folder_patterns", [])
    )

    # Эти поля не считаем частью "keywords", поэтому вырежем их из rules.
    clean_rules = {
        k: v for k, v in rules.items() if k not in ("filename_patterns", "folder_patterns")
    }

    # --- trigger_definitions ---
    trigger_definitions = detail.get("trigger_definitions") or runtime.get(
        "trigger_definitions", {}
    )

    # --- weights (если используются) ---
    weights = detail.get("weights") or runtime.get("weights", {})

    # --- поля из validation_engine (для прототипов и будущих расширений) ---
    engine = detail.get("validation_engine_v3_2", {}) or {}
    engine_rules = engine.get("rules_enhanced", {}) or {}

    party_roles = detail.get("party_roles") or engine_rules.get("party_roles", [])
    essential_terms = detail.get("essential_terms") or engine_rules.get("essential_terms", [])
    section_markers = detail.get("section_markers") or engine_rules.get("section_markers", [])
    aliases = detail.get("aliases") or engine_rules.get("aliases", [])

    # --- phrases: если нет в rules, но есть в validation_engine, подмешиваем ---
    if "phrases" not in clean_rules and "phrases" in engine_rules:
        clean_rules["phrases"] = engine_rules["phrases"]

    return {
        "rules": clean_rules,
        "filename_patterns": filename_patterns,
        "folder_patterns": folder_patterns,
        "trigger_definitions": trigger_definitions,
        "weights": weights,
        "party_roles": party_roles,
        "essential_terms": essential_terms,
        "section_markers": section_markers,
        "aliases": aliases,
    }


@lru_cache(maxsize=1)
def load_registry(registry_path: str) -> Dict[str, Any]:
    """
    Загрузить и закешировать полный реестр типов документов.

    Алгоритм:
    1) Определяем путь к registry.yaml:
       - если registry_path — директория, ищем там registry.yaml;
       - если registry_path — файл, считаем его самим реестром.
    2) Читаем registry.yaml, берём оттуда список document_types.
    3) Для каждого type:
       - пытаемся загрузить <type>.yaml с детальными инструкциями;
       - объединяем запись из registry.yaml и детализацию;
       - нормализуем поля, связанные с классификацией, в единый вид.

    Возвращает:
        {
          "document_types": [
            { ... merged_config_1 ... },
            { ... merged_config_2 ... },
            ...
          ]
        }

    Примечание:
    - Для тестов можно вызвать load_registry.cache_clear(), чтобы сбросить кеш.
    """
    if os.path.isdir(registry_path):
        registry_dir = registry_path
        registry_file = os.path.join(registry_path, "registry.yaml")
    else:
        registry_dir = os.path.dirname(registry_path)
        registry_file = registry_path

    if not os.path.exists(registry_file):
        logger.warning("Registry file not found", path=registry_file)
        return {"document_types": []}

    with open(registry_file, encoding="utf-8") as f:
        index = yaml.safe_load(f) or {}

    merged_types: list[Dict[str, Any]] = []
    types_list = index.get("document_types", []) or []

    for entry in types_list:
        doc_type = entry.get("type", "")
        if not doc_type:
            continue

        # Пытаемся загрузить детализированный YAML для конкретного типа.
        detail_file = os.path.join(registry_dir, f"{doc_type}.yaml")
        detail: Dict[str, Any] = {}
        if os.path.exists(detail_file):
            with open(detail_file, encoding="utf-8") as f:
                detail = yaml.safe_load(f) or {}
            logger.debug(
                "Loaded type instructions",
                doc_type=doc_type,
                file=detail_file,
            )

        # Начинаем с записи из registry.yaml (index).
        merged: Dict[str, Any] = dict(entry)

        # Сохраняем исходные крупные блоки из <type>.yaml (не только rules),
        # чтобы они были доступны другим подсистемам (checks, triggers и т.д.).
        for key in (
            "description",
            "metadata",
            "version",
            "engine_expectations",
            "classification_runtime_v1",
            "validation_engine_v3_2",
        ):
            if key in detail:
                merged[key] = detail[key]

        # Если есть детализация, дополнительно вытаскиваем нормализованные поля классификации.
        if detail:
            classification_fields = _extract_classification_fields(detail)
            merged.update(classification_fields)

        merged["type"] = doc_type
        merged_types.append(merged)

    logger.info(
        "Registry loaded",
        path=registry_file,
        total_types=len(merged_types),
        with_instructions=sum(1 for t in merged_types if t.get("rules")),
    )

    return {"document_types": merged_types}


def get_doc_type_config(registry: Dict[str, Any], doctype: str) -> Dict[str, Any] | None:
    """
    Найти конфиг конкретного типа документа в уже загруженном реестре.

    Параметры:
    - registry: словарь, возвращённый load_registry().
    - doctype : строка с кодом типа (например, "contract_1.6_real_estate").

    Возвращает:
    - словарь с конфигурацией типа, если найден;
    - None, если такого type нет в реестре.
    """
    for cfg in registry.get("document_types", []):
        if cfg.get("type") == doctype:
            return cfg
    return None


def get_all_trigger_names(registry: Dict[str, Any]) -> set[str]:
    """
    Собрать множество всех уникальных имён триггеров по всем типам документов.

    Полезно для:
    - проверки корректности YAML (нет ли опечаток в trigger_definitions),
    - отчётов и аналитики по используемым триггерам.

    Параметры:
    - registry: словарь, возвращённый load_registry().

    Возвращает:
    - set со строками-идентификаторами триггеров.
    """
    triggers: set[str] = set()
    for cfg in registry.get("document_types", []):
        trigger_defs = cfg.get("trigger_definitions", {})
        if isinstance(trigger_defs, dict):
            triggers.update(trigger_defs.keys())
    return triggers
