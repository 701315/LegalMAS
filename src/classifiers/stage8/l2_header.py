"""
L2 Header Classifier — классификация по заголовку документа (Stage 8).

Назначение:
- Второй уровень каскада после L1.
- Анализирует заголовок / шапку документа (первые строки текста) и
  ищет характерные шаблоны для типов документов.

Источники правил:
- YAMLRegistry.get_all_configs() возвращает DocumentTypeConfig.raw для каждого типа.
- В этих конфигурациях ожидается секция classification.header_patterns
  (или аналогичные поля, которые наполняются при подготовке YAML).

Как работает:
- На вход подаётся уже извлечённый header_text (шапка или первые строки документа).
- Для каждого типа из реестра берём список header_patterns (регулярные выражения).
- Пробегаем по паттернам и ищем совпадения в header_text (re.search, IGNORECASE).
- При первом совпадении по типу:
  - считаем, что этот тип — кандидат,
  - присваиваем ему confidence = settings.CLASSIFICATION_L2_ACCEPT,
  - запоминаем совпавший паттерн.

Возвращаемое значение:
- Один объект ClassificationResult с полями:
  - doctype: код типа документа (или "UNKNOWN", если совпадений нет),
  - confidence: уверенность L2 (обычно равна порогу ACCEPT),
  - level: ClassificationLevel.L2_HEADER,
  - method: "header_pattern",
  - evidence: строка вида "Matched header pattern: <regex>" или None.

Роль в каскаде:
- L2 — более надёжный сигнал, чем L1:
  - если уверенность L2 >= CLASSIFICATION_L2_ACCEPT и не противоречит L1,
    новый HybridClassifier может принять раннее решение.
- Если L2 не даёт уверенного результата, каскад передаёт управление на L3 (эмбеддинги).
"""


from __future__ import annotations

import re
from typing import Optional
from src.core.config import settings

from src.classifiers.base import BaseClassifier, ClassificationResult
from src.classifiers.yaml_registry import YAMLRegistry
from src.core.constants import ClassificationLevel
from src.core.logging import get_logger


logger = get_logger(__name__)


class L2HeaderClassifier(BaseClassifier):
    """
    L2: Header/keyword classifier на базе YAMLRegistry.header_patterns.

    Ожидает, что DocumentTypeConfig формирует header_patterns из:
      - name
      - metadata.doc_types_supported
    """

    def __init__(self, registry: Optional[YAMLRegistry] = None) -> None:
        # Используем singleton по умолчанию, но даём возможность подменять в тестах
        self._registry = registry or YAMLRegistry.get_instance()

    @property
    def level(self) -> ClassificationLevel:
        # Используем существующий enum уровня L2
        return ClassificationLevel.L2_HEADER

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        """
        Классификация по заголовку/шапке.

        text — сюда должен приходить уже подготовленный header_text (или полный текст,
        из которого первые строки содержат заголовок).
        filename, folder_path, text_sanitized, metadata — сейчас не используются.
        """
        header_text = (text or "").strip()
        header_lower = header_text.lower()

        if not header_lower:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="header_pattern",
                evidence=None,
            )

        best_type = "UNKNOWN"
        best_conf = 0.0
        best_pattern: str | None = None

        # Перебираем все doc_types из реестра
        for cfg in self._registry.get_all_configs():
            patterns = getattr(cfg, "header_patterns", []) or []
            if not patterns:
                continue

            for p in patterns:
                try:
                    if re.search(p, header_lower, flags=re.IGNORECASE):
                        conf = settings.CLASSIFICATION_L2_ACCEPT
                        if conf > best_conf:
                            best_conf = conf
                            best_type = cfg.type_code
                            best_pattern = p
                        break
                except re.error:
                    logger.warning(
                        "Invalid header pattern in YAMLRegistry",
                        pattern=p,
                        type_code=cfg.type_code,
                    )


        return ClassificationResult(
            doctype=best_type,
            confidence=best_conf,
            level=self.level,
            method="header_pattern",
            evidence=f"Matched header pattern: {best_pattern}" if best_pattern else None,
        )
