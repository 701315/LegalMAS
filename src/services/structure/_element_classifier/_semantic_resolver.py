# src/services/structure/element_classifier/_semantic_resolver.py

"""Resolver для определения semantic_element_type и heading_confidence.

Преобразует базовую классификацию (element_type) в уточнённый семантический тип,
используемый downstream в heading_scoring и heading_builder.
"""

from __future__ import annotations

from services.structure.heading_patterns import parse_raw_heading
from services.structure.legal_heading_rules import (
    looks_like_appendix_heading,
    looks_like_definition_item,
    looks_like_requisites_heading,
    looks_like_signature_heading,
    numeric_uid_depth,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING as SEMANTIC_TYPE_APPENDIX_HEADING,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_BODY_TEXT as SEMANTIC_TYPE_BODY_TEXT,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM as SEMANTIC_TYPE_DEFINITION_ITEM,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_LIST_ITEM as SEMANTIC_TYPE_LIST_ITEM,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_SECTION_HEADING as SEMANTIC_TYPE_SECTION_HEADING,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK as SEMANTIC_TYPE_SIGNATURE_BLOCK,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING as SEMANTIC_TYPE_SUBSECTION_HEADING,
)


def _compute_semantic_element_type(
    *,
    text: str,
    element_type: str,
    raw_type: str | None,
) -> str:
    """Определяет уточнённый semantic_element_type для элемента.

    Args:
        text: Текст элемента (нормализованный)
        element_type: Базовый тип из классификации
        raw_type: Сырой тип из экстрактора

    Returns:
        Семантический тип элемента (константа из services.structure.models)
    """
    normalized_et = element_type.lower().strip()

    # TOC-related — не даём им semantic heading type
    if normalized_et in {
        "toc_header",
        "toc_line",
        "possible_toc",
        "toc_false_positive",
        "page_artifact",
        "unknown_layout",
    }:
        return SEMANTIC_TYPE_BODY_TEXT

    # Signature / requisites → негативные для heading pipeline
    if normalized_et in {"signature_block", "requisites_block"}:
        return SEMANTIC_TYPE_SIGNATURE_BLOCK

    # Table / list
    if normalized_et in {"table_content", "list_item"}:
        return SEMANTIC_TYPE_LIST_ITEM

    # Body text — явно назначен
    if normalized_et == "body_text":
        return SEMANTIC_TYPE_BODY_TEXT

    # Приоритет 1: Appendix heading
    if looks_like_appendix_heading(text):
        return SEMANTIC_TYPE_APPENDIX_HEADING

    # Приоритет 2: Definition item
    if looks_like_definition_item(text):
        return SEMANTIC_TYPE_DEFINITION_ITEM

    # Приоритет 3: Signature / requisites по тексту
    if looks_like_signature_heading(text) or looks_like_requisites_heading(text):
        return SEMANTIC_TYPE_SIGNATURE_BLOCK

    # Приоритет 4: Heading candidate — различаем section vs subsection по uid depth
    if normalized_et in {
        "heading_candidate",
        "section_heading",
        "subsection_heading",
        "appendix_heading",
        "enumerated_clause",
    }:
        # Пробуем распарсить uid из текста
        parsed = parse_raw_heading(text)
        if parsed is not None:
            raw_uid, _ = parsed
            if raw_uid:
                depth = numeric_uid_depth(raw_uid)
                if depth == 1:
                    return SEMANTIC_TYPE_SECTION_HEADING
                elif depth >= 2:
                    return SEMANTIC_TYPE_SUBSECTION_HEADING

        # Если uid не распарсился — для heading candidate ставим section_heading
        return SEMANTIC_TYPE_SECTION_HEADING

    # Fallback
    return SEMANTIC_TYPE_BODY_TEXT


def _compute_heading_confidence_from_classification(
    element_type: str,
    classification_confidence: float,
    semantic_type: str,
) -> float:
    """Вычисляет heading_confidence на основе element_type и semantic_type.

    Args:
        element_type: Базовый тип из классификации
        classification_confidence: Уверенность классификации (0.0-1.0)
        semantic_type: Семантический тип элемента

    Returns:
        Оценка уверенности, что элемент является заголовком (0.0-1.0)
    """
    normalized_et = element_type.lower().strip()

    # TOC / artifact / body — не heading
    if normalized_et in {
        "toc_header",
        "toc_line",
        "possible_toc",
        "toc_false_positive",
        "page_artifact",
        "unknown_layout",
        "body_text",
        "signature_block",
        "requisites_block",
        "table_content",
    }:
        return 0.0

    # Appendix — слабый heading signal
    if semantic_type == SEMANTIC_TYPE_APPENDIX_HEADING:
        return round(min(classification_confidence, 0.75), 3)

    # Definition item — не section heading
    if semantic_type == SEMANTIC_TYPE_DEFINITION_ITEM:
        return 0.0

    # Signature / requisites
    if semantic_type == SEMANTIC_TYPE_SIGNATURE_BLOCK:
        return 0.0

    # List item — очень слабый heading signal
    if normalized_et == "list_item":
        return round(min(classification_confidence * 0.5, 0.45), 3)

    # Section / subsection heading
    if semantic_type in {SEMANTIC_TYPE_SECTION_HEADING, SEMANTIC_TYPE_SUBSECTION_HEADING}:
        return round(min(classification_confidence, 0.95), 3)

    # Fallback
    return round(min(classification_confidence * 0.6, 0.60), 3)
