"""
tests/services/structure/test_phase13_8_clause_function_ontology.py

Phase 13.8 — Clause Function Ontology Refinement tests.

Покрытие:
- normalize_clause_function_label()
- build_clause_function_ontology_payload()
- deterministic default mapping in semantic_enrichment._policy
- rule-based LegalUnitBuilder clause-function classification refinements
"""

from __future__ import annotations

from services.structure.legal_unit_builder import _classify_clause_function
from services.structure.legal_unit_models import (
    ClauseFunction,
    LegalUnitType,
    build_clause_function_ontology_payload,
    normalize_clause_function_label,
)
from services.structure.semantic_enrichment._policy import _default_clause_function_for_type


# ─────────────────────────────────────────────────────────────────────────────
# ClauseFunction normalization
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_clause_function_label_accepts_canonical_values():
    assert normalize_clause_function_label("rights") == ClauseFunction.RIGHTS
    assert normalize_clause_function_label("obligations") == ClauseFunction.OBLIGATIONS
    assert normalize_clause_function_label("limitations") == ClauseFunction.LIMITATIONS
    assert normalize_clause_function_label("procedures") == ClauseFunction.PROCEDURES
    assert normalize_clause_function_label("definitions") == ClauseFunction.DEFINITIONS
    assert normalize_clause_function_label("representations") == ClauseFunction.REPRESENTATIONS
    assert normalize_clause_function_label("remedies") == ClauseFunction.REMEDIES
    assert normalize_clause_function_label("boilerplate") == ClauseFunction.BOILERPLATE
    assert normalize_clause_function_label("unknown") == ClauseFunction.UNKNOWN


def test_normalize_clause_function_label_accepts_alias_warranty_to_representations():
    assert normalize_clause_function_label("warranty") == ClauseFunction.REPRESENTATIONS
    assert normalize_clause_function_label("warranties") == ClauseFunction.REPRESENTATIONS
    assert (
        normalize_clause_function_label("representations_and_warranties")
        == ClauseFunction.REPRESENTATIONS
    )
    assert (
        normalize_clause_function_label("representation and warranty")
        == ClauseFunction.REPRESENTATIONS
    )


def test_normalize_clause_function_label_accepts_alias_indemnity_to_remedies():
    assert normalize_clause_function_label("indemnity") == ClauseFunction.REMEDIES
    assert normalize_clause_function_label("indemnification") == ClauseFunction.REMEDIES
    assert normalize_clause_function_label("damages") == ClauseFunction.REMEDIES
    assert normalize_clause_function_label("penalty") == ClauseFunction.REMEDIES


def test_normalize_clause_function_label_accepts_alias_miscellaneous_to_boilerplate():
    assert normalize_clause_function_label("misc") == ClauseFunction.BOILERPLATE
    assert normalize_clause_function_label("miscellaneous") == ClauseFunction.BOILERPLATE
    assert normalize_clause_function_label("institutional") == ClauseFunction.BOILERPLATE
    assert normalize_clause_function_label("governing_law") == ClauseFunction.BOILERPLATE
    assert normalize_clause_function_label("jurisdiction") == ClauseFunction.BOILERPLATE
    assert normalize_clause_function_label("notices") == ClauseFunction.BOILERPLATE


def test_normalize_clause_function_label_accepts_alias_termination_mechanics_to_procedures():
    assert normalize_clause_function_label("termination_mechanics") == ClauseFunction.PROCEDURES
    assert normalize_clause_function_label("mechanism") == ClauseFunction.PROCEDURES
    assert normalize_clause_function_label("timeline") == ClauseFunction.PROCEDURES


def test_normalize_clause_function_label_handles_case_spacing_and_separators():
    assert normalize_clause_function_label("Representations") == ClauseFunction.REPRESENTATIONS
    assert normalize_clause_function_label("governing-law") == ClauseFunction.BOILERPLATE
    assert normalize_clause_function_label("termination mechanics") == ClauseFunction.PROCEDURES


def test_normalize_clause_function_label_unknown_returns_none():
    assert normalize_clause_function_label("") is None
    assert normalize_clause_function_label(None) is None
    assert normalize_clause_function_label("totally_new_label") is None


# ─────────────────────────────────────────────────────────────────────────────
# Ontology payload
# ─────────────────────────────────────────────────────────────────────────────


def test_build_clause_function_ontology_payload_contains_all_canonical_functions_except_unknown():
    payload = build_clause_function_ontology_payload()
    names = [item["name"] for item in payload]

    assert names == [
        ClauseFunction.RIGHTS.value,
        ClauseFunction.OBLIGATIONS.value,
        ClauseFunction.LIMITATIONS.value,
        ClauseFunction.PROCEDURES.value,
        ClauseFunction.DEFINITIONS.value,
        ClauseFunction.REPRESENTATIONS.value,
        ClauseFunction.REMEDIES.value,
        ClauseFunction.BOILERPLATE.value,
    ]


def test_build_clause_function_ontology_payload_items_have_required_fields():
    payload = build_clause_function_ontology_payload()

    assert payload
    for item in payload:
        assert set(item.keys()) == {"name", "description", "decision_rules"}
        assert isinstance(item["name"], str) and item["name"]
        assert isinstance(item["description"], str) and item["description"]
        assert isinstance(item["decision_rules"], list)
        assert item["decision_rules"]
        assert all(isinstance(rule, str) and rule for rule in item["decision_rules"])


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic default mapping
# ─────────────────────────────────────────────────────────────────────────────


def test_default_clause_function_for_general_provision_is_boilerplate():
    assert (
        _default_clause_function_for_type(LegalUnitType.GENERAL_PROVISION)
        == ClauseFunction.BOILERPLATE
    )


def test_default_clause_function_for_structural_anchor_is_unknown():
    assert (
        _default_clause_function_for_type(LegalUnitType.STRUCTURAL_ANCHOR)
        == ClauseFunction.UNKNOWN
    )


def test_default_clause_function_for_technical_fragment_is_unknown():
    assert (
        _default_clause_function_for_type(LegalUnitType.TECHNICAL_FRAGMENT)
        == ClauseFunction.UNKNOWN
    )


# ─────────────────────────────────────────────────────────────────────────────
# LegalUnitBuilder deterministic classification
# ─────────────────────────────────────────────────────────────────────────────


def test_classify_clause_function_general_provision_maps_to_boilerplate():
    result = _classify_clause_function(
        title="General Provisions",
        text="This Agreement shall be governed and interpreted in accordance with its general terms.",
        unit_type=LegalUnitType.GENERAL_PROVISION,
        scope="main",
        content_mode="full_text",
        is_technical_fallback=False,
    )
    assert result == ClauseFunction.BOILERPLATE


def test_classify_clause_function_structural_anchor_maps_to_unknown():
    result = _classify_clause_function(
        title="Section Heading",
        text="",
        unit_type=LegalUnitType.STRUCTURAL_ANCHOR,
        scope="main",
        content_mode="full_text",
        is_technical_fallback=False,
    )
    assert result == ClauseFunction.UNKNOWN


def test_classify_clause_function_technical_fragment_maps_to_unknown():
    result = _classify_clause_function(
        title="Fragment",
        text="Some technical fallback text",
        unit_type=LegalUnitType.TECHNICAL_FRAGMENT,
        scope="main",
        content_mode="full_text",
        is_technical_fallback=False,
    )
    assert result == ClauseFunction.UNKNOWN


def test_classify_clause_function_indemnity_text_maps_to_remedies():
    result = _classify_clause_function(
        title="Indemnification",
        text="The indemnifying party shall compensate the other party for damages and losses.",
        unit_type=LegalUnitType.UNKNOWN,
        scope="main",
        content_mode="full_text",
        is_technical_fallback=False,
    )
    assert result == ClauseFunction.REMEDIES


def test_classify_clause_function_penalty_text_maps_to_remedies():
    result = _classify_clause_function(
        title="Penalty",
        text="A penalty shall be payable as compensation for delay.",
        unit_type=LegalUnitType.UNKNOWN,
        scope="main",
        content_mode="full_text",
        is_technical_fallback=False,
    )
    assert result == ClauseFunction.REMEDIES


def test_classify_clause_function_termination_procedure_text_maps_to_procedures():
    result = _classify_clause_function(
        title="Termination Procedure",
        text="Either Party may terminate this Agreement by written notice within 30 days.",
        unit_type=LegalUnitType.UNKNOWN,
        scope="main",
        content_mode="full_text",
        is_technical_fallback=False,
    )
    assert result == ClauseFunction.PROCEDURES


def test_classify_clause_function_notice_workflow_text_maps_to_procedures():
    result = _classify_clause_function(
        title="Procedure for Notice",
        text="Any notice shall be delivered in writing following the procedure set out below.",
        unit_type=LegalUnitType.UNKNOWN,
        scope="main",
        content_mode="full_text",
        is_technical_fallback=False,
    )
    assert result == ClauseFunction.PROCEDURES


    