# src/services/structure/_models/_syntax.py

"""
Phase 2 — Syntax & Heading Detection contracts.

SyntaxHeadingCandidate — единый output слоя обнаружения заголовков.
HierarchyTokenType     — тип нумерации/маркера.

ВАЖНО:
- Этот модуль содержит ТОЛЬКО data contracts.
- Никакой логики парсинга/scoring здесь нет.
- Логика парсинга — heading_patterns.py (оставлен как есть).
- Логика scoring  — _heading_scoring/ (оставлен как есть).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HierarchyTokenType(str, Enum):
    """
    Тип нумерации/маркера заголовка.

    Используется FSM (Phase 3) для выбора grammar-правил
    при построении hierarchy tree.

    NUMERIC  — 1 / 1.1 / 1.1.1
    ROMAN    — I / II / IV / IX
    ALPHA    — (a) / (b) / a. / b.
    KEYWORD  — Section 4 / Article II / Annex A / Exhibit B
    BULLET   — • / – / — / ∙
    UNKNOWN  — не удалось определить
    """

    NUMERIC = "numeric"
    ROMAN = "roman"
    ALPHA = "alpha"
    KEYWORD = "keyword"
    BULLET = "bullet"
    UNKNOWN = "unknown"


# Порог heading_confidence ниже которого кандидат
# НЕ участвует в hierarchy и сохраняется как body text.
HEADING_CONFIDENCE_THRESHOLD: float = 0.5


@dataclass(slots=True)
class SyntaxHeadingCandidate:
    """
    Единый output слоя Syntax & Heading Detection (Phase 2).

    После этого слоя кандидат либо:
    - участвует в FSM (heading_confidence >= 0.5);
    - остаётся body text (heading_confidence < 0.5).

    Поля:
        element_index     — индекс элемента в исходном списке
        element_id        — стабильный id элемента
        raw_text          — исходный текст (после normalize_spaces)
        raw_uid           — uid распарсенный из текста
        title             — заголовок после cleanup
        page              — номер страницы
        token_type        — тип нумерации (HierarchyTokenType)
        heading_confidence — score 0.0..1.0
                             < 0.5  → body text, не участвует в hierarchy
                             >= 0.5 → кандидат для FSM
        scope             — logical scope (main_contract / appendix_* / ...)

    Опциональные поля (из PDF extraction — Phase 2):
        font_size         — размер шрифта (если доступен из PyMuPDF)
        is_bold           — жирный шрифт
        indent            — отступ (pts)
        spacing_before    — отступ перед строкой (pts)

    Диагностика:
        confidence_reasons — объяснение откуда взялся score
    """

    element_index: int
    element_id: str
    raw_text: str
    raw_uid: str
    title: str
    page: int
    token_type: HierarchyTokenType
    heading_confidence: float
    scope: str = "main_contract"

    # PDF visual features (опционально, заполняются в Phase 2 при наличии)
    font_size: float | None = None
    is_bold: bool | None = None
    indent: float | None = None
    spacing_before: float | None = None

    # Explainability
    confidence_reasons: list[str] = field(default_factory=list)

    # Passthrough metadata из existing pipeline (для совместимости)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.heading_confidence <= 1.0):
            raise ValueError(
                f"heading_confidence must be in [0.0, 1.0], got {self.heading_confidence}"
            )

    @property
    def participates_in_hierarchy(self) -> bool:
        """
        True если кандидат участвует в FSM hierarchy building.
        False → сохраняется как body text.
        """
        return self.heading_confidence >= HEADING_CONFIDENCE_THRESHOLD

    @property
    def uid(self) -> str:
        """Backward-compatible alias."""
        return self.raw_uid

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_index": self.element_index,
            "element_id": self.element_id,
            "raw_text": self.raw_text,
            "raw_uid": self.raw_uid,
            "title": self.title,
            "page": self.page,
            "token_type": self.token_type.value,
            "heading_confidence": self.heading_confidence,
            "scope": self.scope,
            "participates_in_hierarchy": self.participates_in_hierarchy,
            "font_size": self.font_size,
            "is_bold": self.is_bold,
            "indent": self.indent,
            "spacing_before": self.spacing_before,
            "confidence_reasons": list(self.confidence_reasons),
        }
    

