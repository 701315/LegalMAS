"""
Тесты загрузки внешнего prompt template для Phase 12 semantic enrichment.

Проверяем:
- prompt template существует в prompts/classification/
- PromptLoader может его загрузить
- template содержит ключевые placeholders
"""

from __future__ import annotations

from engine.prompts.loader import get_promptloader
from services.structure.semantic_enrichment._prompting import PROMPT_TEMPLATE_NAME


def test_semantic_enrichment_prompt_template_exists() -> None:
    loader = get_promptloader()

    assert loader.exists(PROMPT_TEMPLATE_NAME) is True


def test_semantic_enrichment_prompt_template_loads_raw() -> None:
    loader = get_promptloader()

    raw = loader.load_raw(PROMPT_TEMPLATE_NAME)

    assert raw
    assert len(raw) > 100


def test_semantic_enrichment_prompt_template_has_required_placeholders() -> None:
    loader = get_promptloader()

    raw = loader.load_raw(PROMPT_TEMPLATE_NAME)

    assert "{allowed_unit_types}" in raw
    assert "{allowed_clause_functions}" in raw
    assert "{allowed_topics}" in raw
    assert "{unit_id}" in raw
    assert "{full_excerpt}" in raw
    assert "{heading_path}" in raw
    assert "{current_unit_type}" in raw
    assert "{evidence_quotes}" in raw or "evidence_quotes" in raw


def test_semantic_enrichment_prompt_template_is_russian() -> None:
    loader = get_promptloader()

    raw = loader.load_raw(PROMPT_TEMPLATE_NAME)

    assert "Верни только JSON" in raw
    assert "русском языке" in raw


    