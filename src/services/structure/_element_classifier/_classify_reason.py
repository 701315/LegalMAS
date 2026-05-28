# src/services/structure/element_classifier/_classify_reason.py

"""Dataclass'ы для представления результатов классификации элементов."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ClassificationReason:
    """Причина классификации элемента с весовым коэффициентом.

    Attributes:
        code: Код причины (например, "toc_header", "signature_keywords")
        weight: Вес/уверенность этого признака (0.0-1.0)
        note: Человекочитаемое пояснение на русском или английском
    """

    code: str
    weight: float
    note: str


@dataclass(slots=True)
class ClassificationResult:
    """Результат классификации одного элемента.

    Attributes:
        element_type: Тип элемента (константа из ELEMENT_TYPE_*)
        confidence: Общая уверенность классификации (0.0-1.0)
        reasons: Список причин, приведших к данному типу
        raw_type: Сырой тип из экстрактора (если есть)
        metadata: Дополнительные метаданные (например, toc_score)
    """

    element_type: str
    confidence: float
    reasons: list[ClassificationReason]
    raw_type: str | None = None
    metadata: dict[str, Any] | None = None
