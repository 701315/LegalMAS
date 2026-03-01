"""
Trigger Detector.

Detects applicable triggers from YAML trigger_definitions.

Использование:
  - Stage 2.5 / 6: HybridClassifier после L1/L? классификации
    берёт winner doctype, получает его YAML-конфиг (DocumentTypeConfig)
    и передаёт сюда для детекции триггеров.
  - Stage 8: список applicable_triggers сохраняется в Document.applicable_triggers
    и используется Runner'ом для выбора conditional checks.

trigger_definitions schema (в YAML типа документа):

  trigger_definitions:
    change_of_control:
      any_keywords: ["смена контроля", "change of control"]
    legal_entity_party:
      any_keywords: ["ООО", "АО", "LLC"]

Output:
  list[str] — список ID триггеров, сработавших в тексте документа.
"""

import re
from typing import List

from src.classifiers.yaml_registry import DocumentTypeConfig
from src.core.logging import get_logger

logger = get_logger(__name__)


def _matches_trigger(trigger_cfg: dict, text_lower: str) -> bool:
    """
    Проверка одного триггера по его конфигу.

    Поддерживает:
      - any_keywords: список ключевых слов/паттернов.
        Если элемент выглядит как regex (с метасимволами), используем re.search,
        иначе — простое вхождение подстроки.
    """
    if not isinstance(trigger_cfg, dict):
        return False

    keywords = trigger_cfg.get("any_keywords", [])
    if not isinstance(keywords, list):
        return False

    for kw in keywords:
        kw_lower = str(kw).lower()
        # Признаки regex — любые спецсимволы регулярки
        if any(c in kw_lower for c in ".+*?^$()[]{}|"):
            try:
                if re.search(kw_lower, text_lower):
                    return True
            except re.error:
                # Если паттерн некорректный, fallback на подстроку
                if kw_lower in text_lower:
                    return True
        elif kw_lower in text_lower:
            return True

    return False


class TriggerDetector:
    """
    Detects applicable triggers for a classified document type.

    Usage:
        detector = TriggerDetector()
        triggers = detector.detect(text, winner_config)
    """

    def detect(self, text: str, cfg: DocumentTypeConfig | None) -> List[str]:
        """
        Detect triggered conditions from document text.

        Args:
            text: Полный текст документа.
            cfg:  DocumentTypeConfig победившего типа (из YAMLRegistry).

        Returns:
            Список ID триггеров, например: ['change_of_control'].
        """
        if not cfg or not getattr(cfg, "trigger_definitions", None):
            return []

        text_lower = text.lower()
        matched_ids: List[str] = []

        for trigger_id, trigger_cfg in cfg.trigger_definitions.items():
            if _matches_trigger(trigger_cfg, text_lower):
                matched_ids.append(trigger_id)
                logger.debug(
                    "Trigger matched",
                    trigger_id=trigger_id,
                    type_code=cfg.type_code,
                )

        return matched_ids
