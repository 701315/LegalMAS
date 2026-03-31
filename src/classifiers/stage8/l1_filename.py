# src/classifiers/stage8/l1_filename.py

"""
L1: Filename classifier с YAMLRegistry (Stage 8).


Назначение:
- Быстрый, «дешёвый» уровень классификации по имени файла и папки.
- Использует регулярные выражения из YAML-конфигов типов документов.
- Даёт сильный hint для очевидных случаев (например, 'SPA', 'SHA', 'Договор займа').


Источники правил:
- YAMLRegistry загружает:
  - classification_runtime_v1.rules.filename_patterns
  - classification_runtime_v1.rules.folder_patterns
  - либо legacy rules.filename_patterns / rules.folder_patterns


Как работает:
- Для каждого типа документа берём список filename_patterns и folder_patterns
  (это уже скомпилированные регулярные выражения re.Pattern).
- Пробегаем по всем типам, матчим регулярные выражения против:
  - полного имени файла (filename),
  - полного пути к папке/каталогу (folder).
- При наличии совпадений по типу добавляем кандидата:
  {
    "type_code": <код типа из YAML>,
    "confidence": <рассчитанное значение>,
    "level": "L1",
    "method": "filename",
    "details": {
      "filename_matched": bool,
      "folder_matched": bool,
      "filename_hits": int,
      "folder_hits": int,
      "patterns_used": [str, ...],
    },
  }
- Возвращаем список всех кандидатов, отсортированный по confidence по убыванию.


Роль в каскаде:
- L1 НЕ принимает финальное решение самостоятельно.
- В HybridClassifier (Stage 8) L1 даёт подсказки (hint), которые
  учитываются при взвешенном голосовании вместе с L2 и L3.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..yaml_registry import YAMLRegistry, DocumentTypeConfig
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class L1FilenameClassifier:
    """
    L1: классификатор по имени файла и пути к папке.

    Важно:
    - Этот уровень даёт только «подсказки» для каскада.
    - Ошибочное совпадение на L1 не фатально: его скорректируют L2 и L3.
    """

    def __init__(self, registry: YAMLRegistry | None = None) -> None:
        # Используем singleton по умолчанию, но даём возможность подменять в тестах.
        self._registry = registry or YAMLRegistry.get_instance()

    def classify(self, filename: str | None, folder: str | None) -> List[Dict[str, Any]]:
        """
        Вернуть список кандидатов {type_code, confidence, level, method, details}.

        Параметры:
        - filename: строка с именем файла (может включать расширение).
        - folder  : строка с путём к папке (может быть пустой или None).

        Поведение:
        - Если ни один паттерн не сработал, возвращаем пустой список.
        - Если совпадения есть, каждый тип добавляется один раз, но с
          учётом количества попаданий и того, где они произошли (filename/folder).
        """
        filename = (filename or "").strip()
        folder = (folder or "").strip()

        candidates: List[Dict[str, Any]] = []

        # Если вообще нет ни имени, ни папки — классифицировать нечего.
        if not filename and not folder:
            return candidates

        # Базовый уровень уверенности для L1 (можно регулировать в настройках)
        base_conf = float(getattr(settings, "CLASSIFICATION_L1_ACCEPT", 0.7))

        # Перебираем все типы документов из реестра.
        for cfg in self._registry.get_all_configs():
            # cfg: DocumentTypeConfig
            type_code: str = cfg.type_code

            filename_patterns = getattr(cfg, "filename_patterns", []) or []
            folder_patterns = getattr(cfg, "folder_patterns", []) or []

            # Если ни одного паттерна нет, этот тип по L1 не участвует.
            if not filename_patterns and not folder_patterns:
                continue

            filename_hits = 0
            folder_hits = 0
            patterns_used: list[str] = []

            # 1. Проверяем filename_patterns против имени файла.
            for p in filename_patterns:
                try:
                    if filename and p.search(filename):
                        filename_hits += 1
                        patterns_used.append(getattr(p, "pattern", str(p)))
                except Exception as e:
                    logger.warning(
                        "Invalid filename pattern in YAMLRegistry",
                        extra={
                            "pattern": getattr(p, "pattern", str(p)),
                            "type_code": type_code,
                            "error": str(e),
                        },
                    )

            # 2. Проверяем folder_patterns против пути к папке.
            for p in folder_patterns:
                try:
                    if folder and p.search(folder):
                        folder_hits += 1
                        patterns_used.append(getattr(p, "pattern", str(p)))
                except Exception as e:
                    logger.warning(
                        "Invalid folder pattern in YAMLRegistry",
                        extra={
                            "pattern": getattr(p, "pattern", str(p)),
                            "type_code": type_code,
                            "error": str(e),
                        },
                    )

            # Если не было ни одного попадания — переходим к следующему типу.
            if filename_hits == 0 and folder_hits == 0:
                continue

            # ---- Расчёт confidence для L1 ----
            confidence = base_conf

            # Матч по имени файла считаем более сильным, чем по папке.
            if filename_hits > 0:
                confidence += 0.1
            elif folder_hits > 0:
                # Если сработала только папка — лёгкий штраф.
                confidence -= 0.05

            # Дополнительный буст за несколько попаданий по паттернам.
            total_hits = filename_hits + folder_hits
            extra_hits = max(total_hits - 1, 0)
            if extra_hits > 0:
                # Максимум +0.15 за мульти-хит, чтобы не разгонять выше 1.0.
                confidence += 0.05 * min(extra_hits, 3)

            # Нормализация в диапазон [0.0, 1.0].
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
                    },
                }
            )

        # Сортируем по убыванию confidence.
        return sorted(candidates, key=lambda x: x["confidence"], reverse=True)
