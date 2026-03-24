# src/classifiers/__init__.py

"""
Пакет classifiers.

Назначение:
- Содержит реализацию каскада классификации документов (L1–L4).
- YAMLRegistry предоставляет доступ к YAML-конфигам типов документов.

Рекомендация:
- Импортируй конкретные классы напрямую из их модулей, например:
    from classifiers.yaml_registry import YAMLRegistry
    from classifiers.stage8.hybrid_classifier import HybridClassifier
    from classifiers.stage8.l1_filename import L1FilenameClassifier
    from classifiers.stage8.l2_header import L2HeaderClassifier
    from classifiers.stage8.l3_semantic import L3SemanticClassifier
"""

from .yaml_registry import YAMLRegistry

__all__ = [
    "YAMLRegistry",
]
