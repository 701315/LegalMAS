# src/classifiers/stage8/l1_filename.py

"""
L1: Filename classifier с YAMLRegistry (Stage 8).

Назначение:
- Быстрый, «дешёвый» уровень классификации по имени файла и папки.
- Использует регулярные выражения из YAML-конфигов типов документов.
- Даёт hint для очевидных случаев, но не должен доминировать над
  более специфичными текстовыми сигналами из L2/L3.

Источники правил:
- YAMLRegistry загружает:
  - classification_runtime_v1.rules.filename_patterns
  - classification_runtime_v1.rules.folder_patterns
  - либо legacy rules.filename_patterns / rules.folder_patterns

Поддерживаемые форматы правил:
- legacy: list[str]
- extended: list[dict], где каждый dict может содержать:
  {
    "pattern": "...regex...",
    "kind": "generic_form" | "specific_subject" | "context",
    "weight": 1.0,
  }

Роль в каскаде:
- L1 НЕ принимает финальное решение самостоятельно.
- В HybridClassifier (Stage 8) L1 даёт подсказки (hint), которые
  учитываются при взвешенном голосовании вместе с L2 и L3.

Ключевая идея:
- generic form markers (например, "SPA") должны быть слабым сигналом;
- specific subject markers ("real_estate", "factoring", "договор поставки")
  должны быть сильнее generic;
- если есть specific сигнал, generic не должен конкурировать с ним на равных.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ..yaml_registry import YAMLRegistry
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class L1FilenameClassifier:
    """
    L1: классификатор по имени файла и пути к папке.

    Важно:
    - Этот уровень даёт только «подсказки» для каскада.
    - Ошибочное совпадение на L1 не фатально: его скорректируют L2 и L3.
    - Generic filename-аббревиатуры сами по себе не должны давать
      production-уровневую уверенность.
    """

    def __init__(self, registry: YAMLRegistry | None = None) -> None:
        self._registry = registry or YAMLRegistry.get_instance()

    @staticmethod
    def _extract_rule_parts(rule: Any) -> tuple[re.Pattern | None, str, float, str]:
        """
        Нормализует правило из YAMLRegistry в единый runtime-вид.

        Поддержка backward compatibility:
        - legacy compiled regex: re.Pattern
        - extended object: ожидается объект с .pattern / .kind / .weight / .raw_pattern

        Возвращает:
        - compiled_pattern
        - rule_kind
        - rule_weight
        - raw_pattern_text
        """
        if hasattr(rule, "pattern") and isinstance(getattr(rule, "pattern"), re.Pattern):
            compiled = getattr(rule, "pattern")
            rule_kind = str(getattr(rule, "kind", "generic_form") or "generic_form")
            rule_weight = float(getattr(rule, "weight", 1.0) or 1.0)
            raw_pattern = str(getattr(rule, "raw_pattern", compiled.pattern))
            return compiled, rule_kind, rule_weight, raw_pattern

        if isinstance(rule, re.Pattern):
            return rule, "generic_form", 1.0, rule.pattern

        return None, "generic_form", 1.0, str(rule)

    def classify(self, filename: str | None, folder: str | None) -> List[Dict[str, Any]]:
        """
        Вернуть список кандидатов {type_code, confidence, level, method, details}.

        Параметры:
        - filename: строка с именем файла (может включать расширение).
        - folder  : строка с путём к папке (может быть пустой или None).

        Поведение:
        - Если ни один паттерн не сработал, возвращаем пустой список.
        - Если совпадения есть, каждый тип добавляется один раз.
        - confidence зависит не только от числа совпадений, но и от
          типа сигнала: specific_subject > generic_form > context.
        """
        filename = (filename or "").strip()
        folder = (folder or "").strip()

        candidates: List[Dict[str, Any]] = []

        if not filename and not folder:
            return candidates

        base_conf = float(getattr(settings, "CLASSIFICATION_L1_ACCEPT", 0.7))

        for cfg in self._registry.get_all_configs():
            type_code: str = cfg.type_code

            filename_patterns = getattr(cfg, "filename_patterns", []) or []
            folder_patterns = getattr(cfg, "folder_patterns", []) or []

            if not filename_patterns and not folder_patterns:
                continue

            filename_hits = 0
            folder_hits = 0
            patterns_used: list[str] = []

            generic_hits = 0
            generic_weight = 0.0
            specific_hits = 0
            specific_weight = 0.0
            context_hits = 0
            context_weight = 0.0

            def _accumulate(rule_kind: str, rule_weight: float) -> None:
                nonlocal generic_hits, generic_weight
                nonlocal specific_hits, specific_weight
                nonlocal context_hits, context_weight

                if rule_kind == "specific_subject":
                    specific_hits += 1
                    specific_weight += rule_weight
                elif rule_kind == "context":
                    context_hits += 1
                    context_weight += rule_weight
                else:
                    generic_hits += 1
                    generic_weight += rule_weight

            for rule in filename_patterns:
                compiled, rule_kind, rule_weight, raw_pattern = self._extract_rule_parts(rule)
                if compiled is None:
                    continue

                try:
                    if filename and compiled.search(filename):
                        filename_hits += 1
                        patterns_used.append(raw_pattern)
                        _accumulate(rule_kind, rule_weight)
                except Exception as e:
                    logger.warning(
                        "Invalid filename pattern in YAMLRegistry",
                        extra={
                            "pattern": raw_pattern,
                            "type_code": type_code,
                            "error": str(e),
                        },
                    )

            for rule in folder_patterns:
                compiled, rule_kind, rule_weight, raw_pattern = self._extract_rule_parts(rule)
                if compiled is None:
                    continue

                try:
                    if folder and compiled.search(folder):
                        folder_hits += 1
                        patterns_used.append(raw_pattern)
                        _accumulate(rule_kind, rule_weight * 0.75)
                except Exception as e:
                    logger.warning(
                        "Invalid folder pattern in YAMLRegistry",
                        extra={
                            "pattern": raw_pattern,
                            "type_code": type_code,
                            "error": str(e),
                        },
                    )

            if filename_hits == 0 and folder_hits == 0:
                continue

            confidence = base_conf

            if specific_hits > 0:
                confidence = max(confidence, base_conf + 0.10)
                confidence += min(specific_weight, 1.0) * 0.20
                if generic_hits > 0:
                    confidence += min(generic_weight, 0.5) * 0.05
                if context_hits > 0:
                    confidence += min(context_weight, 0.5) * 0.03
                signal_kind = "specific_subject"

            elif generic_hits > 0:
                confidence = min(max(confidence, 0.50 + min(generic_weight, 1.0) * 0.10), 0.65)
                if context_hits > 0:
                    confidence += min(context_weight, 0.5) * 0.02
                signal_kind = "generic_form"

            else:
                confidence = min(confidence, 0.50)
                if context_hits > 0:
                    confidence += min(context_weight, 0.5) * 0.02
                signal_kind = "context"

            confidence = max(0.0, min(1.0, confidence))

            candidates.append(
                {
                    "type_code": type_code,
                    "confidence": confidence,
                    "level": "L1",
                    "method": "filename",
                    "details": {
                        "filename_matched": filename_hits > 0,
                        "folder_matched": folder_hits > 0,
                        "filename_hits": filename_hits,
                        "folder_hits": folder_hits,
                        "patterns_used": patterns_used,
                        "signal_kind": signal_kind,
                        "generic_hits": generic_hits,
                        "specific_hits": specific_hits,
                        "context_hits": context_hits,
                        "generic_weight": round(generic_weight, 4),
                        "specific_weight": round(specific_weight, 4),
                        "context_weight": round(context_weight, 4),
                    },
                }
            )

        if not candidates:
            return candidates

        max_specific_conf = max(
            (
                c["confidence"]
                for c in candidates
                if c.get("details", {}).get("signal_kind") == "specific_subject"
            ),
            default=None,
        )

        if max_specific_conf is not None:
            for c in candidates:
                if c.get("details", {}).get("signal_kind") == "generic_form":
                    c["confidence"] = min(c["confidence"], max_specific_conf - 0.10)
                    c["confidence"] = max(0.0, c["confidence"])

        return sorted(candidates, key=lambda x: x["confidence"], reverse=True)
    

    
