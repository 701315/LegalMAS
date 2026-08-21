"""
Конфигурация Document Layout Pipeline v2.

Все пороги, маппинги и паттерны вынесены сюда для:
- лёгкой настройки per-tenant / per-environment;
- тестирования с разными конфигурациями;
- отсутствия magic numbers в бизнес-логике.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class DocumentLayoutConfig(BaseSettings):
    """Настройки пайплайна. Читаются из env с префиксом DOCUMENT_LAYOUT_."""

    min_absolute_letter_count: int = Field(default=3)
    dominant_script_ratio: float = Field(default=0.85)
    min_substantive_letter_count: int = Field(default=5)

    script_to_language: dict[str, str] = Field(
        default={
            "Cyrillic": "ru",
            "Latin": "en",
            "Han": "zh",
            "Arabic": "ar",
            "Devanagari": "hi",
            "Hangul": "ko",
            "Hiragana": "ja",
            "Katakana": "ja",
        },
    )

    # КРИТИЧНО: section_header и title → "heading" (+0.45 в classifier)
    label_to_raw_type: dict[str, str] = Field(
        default={
            "list_item": "list_item",
            "section_header": "heading",
            "paragraph": "text",
            "table": "table",
            "title": "heading",
            "page_header": "page_artifact",
            "page_footer": "page_artifact",
            "footnote": "text",
            "caption": "text",
            "formula": "text",
            "picture": "page_artifact",
            "document_index": "text",
            "code": "text",
            "checkbox_selected": "list_item",
            "checkbox_unselected": "list_item",
        },
    )

    safe_split_patterns: list[dict[str, str]] = Field(
        default=[
            {"separator": " / ", "strategy": "left_right"},
            {"separator": " — ", "strategy": "left_right"},
            {"separator": "\n", "strategy": "line_by_line_language"},
        ],
    )

    min_target_language_ratio: float = Field(default=0.05)
    max_atom_count_drop_ratio: float = Field(default=0.80)
    document_layout_v2_enabled: bool = Field(default=False)

    model_config = {"env_prefix": "DOCUMENT_LAYOUT_", "case_sensitive": False}


layout_config = DocumentLayoutConfig()
