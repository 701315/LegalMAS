"""
Тесты для prompt construction (Phase 12 / 12.1).

Тестируем:
- Prompt строится без ошибок.
- Prompt содержит ключевые поля из unit.
- Prompt содержит evidence_quotes инструкцию.
- Prompt содержит heading_path.
- Prompt на русском языке (для русскоязычного корпуса).
"""

from __future__ import annotations

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
)
from services.structure.semantic_enrichment import build_semantic_enrichment_prompt


def _make_unit(
    *,
    unit_id: str = "u-main",
    raw_uid: str = "7.2",
    title: str = "Порядок оплаты",
    text: str = (
        "Покупатель обязан уплатить покупную цену в размере 1 000 000 руб. "
        "в течение пяти рабочих дней с момента получения счёта "
        "и всех подтверждающих документов."
    ),
    unit_type: LegalUnitType = LegalUnitType.UNKNOWN,
    clause_function: ClauseFunction = ClauseFunction.UNKNOWN,
    topic_tags: list[str] | None = None,
) -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid=raw_uid,
        scope="main_contract",
        title=title,
        level=2,
        unit_type=unit_type,
        clause_function=clause_function,
        segment_id="seg-1",
        segment_type="contract",
        page_start=5,
        page_end=5,
        own_text=text,
        subtree_text=text,
        own_element_ids=[],
        topic_tags=list(topic_tags or []),
        cross_refs=[],
        citability=CitabilityMetrics(
            citability_score=0.9,
            citability_band="high",
            has_own_text=True,
            has_subtree_text=True,
        ),
        node_kind="leaf",
        diagnostics={},
    )


def test_build_semantic_enrichment_prompt_contains_required_context() -> None:
    prev_unit = _make_unit(
        unit_id="u-prev",
        raw_uid="7.1",
        title="Определения",
        text="Определения, используемые в настоящем Договоре.",
        unit_type=LegalUnitType.DEFINITION,
        clause_function=ClauseFunction.DEFINITIONS,
        topic_tags=["definitions"],
    )
    unit = _make_unit()
    next_unit = _make_unit(
        unit_id="u-next",
        raw_uid="7.3",
        title="Уведомления",
        text="Все уведомления направляются в письменной форме.",
        unit_type=LegalUnitType.NOTICE,
        clause_function=ClauseFunction.BOILERPLATE,
        topic_tags=["notices"],
    )

    all_units = [
        _make_unit(unit_id="u-7", raw_uid="7", title="Платежи"),
        prev_unit,
        unit,
        next_unit,
    ]

    prompt = build_semantic_enrichment_prompt(
        unit=unit,
        previous_unit=prev_unit,
        next_unit=next_unit,
        all_units=all_units,
    )

    assert "u-main" in prompt
    assert "Порядок оплаты" in prompt or "\\u041f" in prompt
    assert "suggested_unit_type" in prompt
    assert "suggested_clause_function" in prompt
    assert "suggested_topics" in prompt
    assert "confidence" in prompt
    assert "evidence_quotes" in prompt
    assert "heading_path" in prompt


def test_prompt_is_russian_language() -> None:
    unit = _make_unit()

    prompt = build_semantic_enrichment_prompt(unit=unit)

    assert "русском языке" in prompt
    assert "Верни только JSON" in prompt


def test_prompt_contains_heading_path_when_all_units_provided() -> None:
    units = [
        _make_unit(unit_id="u-7", raw_uid="7", title="Платежи"),
        _make_unit(unit_id="u-7.2", raw_uid="7.2", title="Порядок оплаты"),
    ]

    prompt = build_semantic_enrichment_prompt(
        unit=units[1],
        all_units=units,
    )

    assert "heading_path" in prompt

    