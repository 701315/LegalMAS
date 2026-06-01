"""
tests/services/structure/test_phase13_8_prompting_clause_function_ontology.py

Phase 13.8 — Prompting tests for clause-function ontology guidance.

Покрытие:
- build_semantic_enrichment_prompt() passes clause_function_ontology to PromptLoader
- ontology payload inside variables has expected shape
- rendered prompt includes ontology guidance and priority rules
"""

from __future__ import annotations

import json

import services.structure.semantic_enrichment._prompting as prompting_module
from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
)
from services.structure.semantic_enrichment._prompting import (
    PROMPT_TEMPLATE_NAME,
    build_semantic_enrichment_prompt,
)


def _make_unit(
    *,
    unit_id: str = "u1",
    raw_uid: str = "7.2",
    title: str = "Termination Mechanics",
    unit_type: LegalUnitType = LegalUnitType.TERMINATION_PROVISION,
    clause_function: ClauseFunction = ClauseFunction.UNKNOWN,
    own_text: str = (
        "Either Party may terminate this Agreement by written notice "
        "within thirty (30) days after a material breach."
    ),
) -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid=raw_uid,
        scope="main",
        title=title,
        level=2,
        unit_type=unit_type,
        clause_function=clause_function,
        segment_id="seg-1",
        segment_type="main_contract",
        page_start=1,
        page_end=1,
        own_text=own_text,
        subtree_text=None,
        own_element_ids=[],
        topic_tags=[],
        cross_refs=[],
        citability=CitabilityMetrics(
            citability_score=0.9,
            citability_band="high",
            has_own_text=True,
            has_subtree_text=False,
            is_heading_only=False,
        ),
        node_kind="leaf",
        semantic_node_type=None,
        node_origin="deterministic",
        content_mode="full_text",
        recovered_via_best_effort=False,
        fallback_reason=None,
        diagnostics={},
    )


class _FakePromptLoader:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def load(self, template_name: str, variables: dict[str, str]) -> str:
        self.calls.append({
            "template_name": template_name,
            "variables": variables,
        })
        return "FAKE_PROMPT"


def test_build_semantic_enrichment_prompt_passes_clause_function_ontology(monkeypatch):
    fake_loader = _FakePromptLoader()
    monkeypatch.setattr(prompting_module, "get_promptloader", lambda: fake_loader)

    unit = _make_unit()

    result = build_semantic_enrichment_prompt(unit=unit)

    assert result == "FAKE_PROMPT"
    assert len(fake_loader.calls) == 1

    call = fake_loader.calls[0]
    assert call["template_name"] == PROMPT_TEMPLATE_NAME

    variables = call["variables"]
    assert "clause_function_ontology" in variables

    ontology = json.loads(variables["clause_function_ontology"])
    assert isinstance(ontology, list)
    assert ontology

    names = [item["name"] for item in ontology]
    assert "representations" in names
    assert "remedies" in names
    assert "procedures" in names
    assert "boilerplate" in names
    assert "unknown" not in names

    first = ontology[0]
    assert set(first.keys()) == {"name", "description", "decision_rules"}
    assert isinstance(first["description"], str) and first["description"]
    assert isinstance(first["decision_rules"], list) and first["decision_rules"]


def test_build_semantic_enrichment_prompt_real_render_contains_ontology_section():
    unit = _make_unit(
        title="Limitation of Liability",
        unit_type=LegalUnitType.LIABILITY_PROVISION,
        own_text=(
            "Neither Party shall be liable for any indirect or consequential damages "
            "arising out of this Agreement."
        ),
    )

    prompt = build_semantic_enrichment_prompt(unit=unit)

    assert isinstance(prompt, str)
    assert "ONTOLOGY ДЛЯ CLAUSE FUNCTION" in prompt
    assert "КРИТИЧЕСКОЕ УТОЧНЕНИЕ ПО suggested_clause_function" in prompt
    assert "ПРАВИЛА ПРИОРИТЕТА ДЛЯ CLAUSE FUNCTION" in prompt


def test_build_semantic_enrichment_prompt_real_render_contains_clause_function_guidance_examples():
    unit = _make_unit(
        title="Indemnification",
        unit_type=LegalUnitType.INDEMNIFICATION,
        own_text=(
            "The Seller shall indemnify and hold harmless the Buyer against all losses, "
            "damages and claims arising from breach of this Agreement."
        ),
    )

    prompt = build_semantic_enrichment_prompt(unit=unit)

    assert "limitations" in prompt
    assert "remedies" in prompt
    assert "procedures" in prompt
    assert "boilerplate" in prompt
    assert "indemnity" in prompt or "indemnif" in prompt


def test_build_semantic_enrichment_prompt_keeps_allowed_clause_functions_backward_compatible(monkeypatch):
    fake_loader = _FakePromptLoader()
    monkeypatch.setattr(prompting_module, "get_promptloader", lambda: fake_loader)

    unit = _make_unit(clause_function=ClauseFunction.OBLIGATIONS)

    build_semantic_enrichment_prompt(unit=unit)

    variables = fake_loader.calls[0]["variables"]
    allowed = json.loads(variables["allowed_clause_functions"])

    assert ClauseFunction.RIGHTS.value in allowed
    assert ClauseFunction.OBLIGATIONS.value in allowed
    assert ClauseFunction.LIMITATIONS.value in allowed
    assert ClauseFunction.PROCEDURES.value in allowed
    assert ClauseFunction.DEFINITIONS.value in allowed
    assert ClauseFunction.REPRESENTATIONS.value in allowed
    assert ClauseFunction.REMEDIES.value in allowed
    assert ClauseFunction.BOILERPLATE.value in allowed
    assert ClauseFunction.UNKNOWN.value in allowed



    