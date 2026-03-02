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
- Для каждого типа документа берём список filename_patterns (и при необходимости folder_patterns).
- Пробегаем по всем типам, матчим регулярные выражения против:
  - имени файла (filename),
  - пути к папке/каталогу (folder).
- При первом совпадении по типу добавляем кандидата:
  {
    "type_code": <код типа из YAML>,
    "confidence": settings.CLASSIFICATION_L1_ACCEPT,
    "level": "L1",
    "method": "filename",
  }
- Возвращаем список всех кандидатов, отсортированный по confidence по убыванию.

Роль в каскаде:
- L1 НЕ обязан принимать финальное решение.
- В новом HybridClassifier L1 либо даёт «очевидный» финальный тип,
  либо просто добавляет кандидатов, которые дальше подтверждаются L2/L3.
"""

from src.classifiers.yaml_registry import YAMLRegistry
from src.core.config import settings


class L1FilenameClassifier:
    def __init__(self):
        # используем singleton, который сам знает про registry_path из настроек
        self.registry = YAMLRegistry.get_instance()

    def classify(self, filename: str, folder: str) -> list[dict]:
        """Вернуть список кандидатов {type_code, confidence, method}"""
        candidates = []
        all_types = self.registry.list_types()

        for type_code in all_types:
            rules = self.registry.get_classification_rules(type_code)
            patterns = rules.get("filename_patterns", [])

            for pattern in patterns:
                if pattern.match(filename) or pattern.match(folder):
                    confidence = settings.CLASSIFICATION_L1_ACCEPT
                    candidates.append(
                        {
                            "type_code": type_code,
                            "confidence": confidence,
                            "level": "L1",
                            "method": "filename",
                        }
                    )
                    break

        return sorted(candidates, key=lambda x: x["confidence"], reverse=True)
