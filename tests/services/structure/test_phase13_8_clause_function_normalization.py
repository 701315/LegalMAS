"""
tests/services/structure/test_phase13_8_clause_function_normalization.py

Phase 13.8 — Clause Function normalization integration tests.

Покрытие:
- LegalUnit.from_dict() uses clause-function normalization
- semantic_enrichment._validator._parse_clause_function() uses normalization
- LegalUnitsEnrichmentResult.from_dict() normalizes aliases
- engine.content._document_content_semantic.restore_legal_units() normalizes aliases
"""

from __future__ import annotations

import uuid

from engine.content._document_content_semantic import restore_legal_units
from services.structure.legal_unit_models import ClauseFunction, LegalUnit
from services.structure.semantic_enrichment._types import LegalUnitsEnrichmentResult
from services.structure.semantic_enrichment._validator import _parse_clause_function


class _FakeLogger:
    def debug(self, *args, **kwargs):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# LegalUnit.from_dict()
# ─────────────────────────────────────────────────────────────────────────────


def test_legal_unit_from_dict_normalizes_warranties_to_representations():
    raw = {
        "unit_id": "u1",
        "raw_uid": "1.1",
        "scope": "main",
        "title": "Seller Warranties",
        "level": 2,
        "unit_type": "warranty",
        "clause_function": "warranties",
    }

    unit = LegalUnit.from_dict(raw)

    assert unit.clause_function == ClauseFunction.REPRESENTATIONS


def test_legal_unit_from_dict_normalizes_miscellaneous_to_boilerplate():
    raw = {
        "unit_id": "u2",
        "raw_uid": "10",
        "scope": "main",
        "title": "Miscellaneous",
        "level": 1,
        "unit_type": "general_provision",
        "clause_function": "miscellaneous",
    }

    unit = LegalUnit.from_dict(raw)

    assert unit.clause_function == ClauseFunction.BOILERPLATE


def test_legal_unit_from_dict_invalid_clause_function_falls_back_to_unknown():
    raw = {
        "unit_id": "u3",
        "raw_uid": "9",
        "scope": "main",
        "title": "Unknown",
        "level": 1,
        "unit_type": "unknown",
        "clause_function": "not_a_real_clause_function",
    }

    unit = LegalUnit.from_dict(raw)

    assert unit.clause_function == ClauseFunction.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# Validator normalization
# ─────────────────────────────────────────────────────────────────────────────


def test_validator_parse_clause_function_normalizes_indemnity_to_remedies():
    parsed, invalid = _parse_clause_function("indemnity")

    assert parsed == ClauseFunction.REMEDIES
    assert invalid is None


def test_validator_parse_clause_function_normalizes_termination_mechanics_to_procedures():
    parsed, invalid = _parse_clause_function("termination_mechanics")

    assert parsed == ClauseFunction.PROCEDURES
    assert invalid is None


def test_validator_parse_clause_function_invalid_value_returns_invalid_marker():
    parsed, invalid = _parse_clause_function("this_is_not_valid")

    assert parsed is None
    assert invalid == "this_is_not_valid"


# ─────────────────────────────────────────────────────────────────────────────
# LegalUnitsEnrichmentResult.from_dict()
# ─────────────────────────────────────────────────────────────────────────────


def test_enrichment_result_from_dict_normalizes_base_effective_and_proposal_clause_functions():
    payload = {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "segment": {
            "segment_id": "seg-1",
            "segment_type": "main_contract",
            "segment_order": 0,
            "is_primary_segment": True,
        },
        "llm": {
            "provider": "test",
            "model": "test-model",
        },
        "stats": {
            "build_warnings": [],
        },
        "enrichments": [
            {
                "unit_id": "u1",
                "status": "applied",
                "base": {
                    "unit_type": "general_provision",
                    "clause_function": "miscellaneous",
                    "topic_tags": [],
                },
                "effective": {
                    "unit_type": "warranty",
                    "clause_function": "warranties",
                    "topic_tags": ["warranties"],
                },
                "applied_fields": ["clause_function"],
                "llm_proposal": {
                    "suggested_unit_type": "indemnification",
                    "suggested_clause_function": "indemnity",
                    "suggested_topics": ["indemnification"],
                    "confidence": 0.88,
                    "reasoning": "Contains indemnity language",
                    "evidence_quotes": ["indemnify and hold harmless"],
                    "diagnostics": {},
                },
                "decision_reason": "applied",
                "diagnostics": {},
            }
        ],
    }

    result = LegalUnitsEnrichmentResult.from_dict(payload)

    assert len(result.enrichments) == 1
    enrichment = result.enrichments[0]

    assert enrichment.base_clause_function == ClauseFunction.BOILERPLATE
    assert enrichment.effective_clause_function == ClauseFunction.REPRESENTATIONS
    assert enrichment.llm_proposal is not None
    assert enrichment.llm_proposal.suggested_clause_function == ClauseFunction.REMEDIES


def test_enrichment_result_from_dict_unknown_alias_falls_back_to_unknown():
    payload = {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "segment": {
            "segment_id": "seg-1",
            "segment_type": "main_contract",
            "segment_order": 0,
            "is_primary_segment": True,
        },
        "enrichments": [
            {
                "unit_id": "u1",
                "status": "applied",
                "base": {
                    "unit_type": "unknown",
                    "clause_function": "not_valid",
                    "topic_tags": [],
                },
                "effective": {
                    "unit_type": "unknown",
                    "clause_function": "still_not_valid",
                    "topic_tags": [],
                },
                "applied_fields": [],
                "diagnostics": {},
            }
        ],
    }

    result = LegalUnitsEnrichmentResult.from_dict(payload)

    enrichment = result.enrichments[0]
    assert enrichment.base_clause_function == ClauseFunction.UNKNOWN
    assert enrichment.effective_clause_function == ClauseFunction.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# restore_legal_units()
# ─────────────────────────────────────────────────────────────────────────────


def test_restore_legal_units_normalizes_clause_function_aliases():
    units_raw = [
        {
            "unit_id": "u1",
            "raw_uid": "15",
            "scope": "main",
            "title": "Termination Mechanics",
            "level": 1,
            "unit_type": "termination_provision",
            "clause_function": "termination_mechanics",
            "segment_id": "seg-1",
            "segment_type": "main_contract",
            "page_start": 1,
            "page_end": 1,
            "topic_tags": [],
            "citability": {
                "citability_score": 0.8,
                "citability_band": "high",
                "has_own_text": True,
                "has_subtree_text": False,
                "is_heading_only": False,
            },
        },
        {
            "unit_id": "u2",
            "raw_uid": "16",
            "scope": "main",
            "title": "Miscellaneous",
            "level": 1,
            "unit_type": "general_provision",
            "clause_function": "miscellaneous",
            "segment_id": "seg-1",
            "segment_type": "main_contract",
            "page_start": 2,
            "page_end": 2,
            "topic_tags": [],
            "citability": {
                "citability_score": 0.8,
                "citability_band": "high",
                "has_own_text": True,
                "has_subtree_text": False,
                "is_heading_only": False,
            },
        },
    ]

    restored = restore_legal_units(
        units_raw=units_raw,
        doc_id=uuid.uuid4(),
        logger=_FakeLogger(),
    )

    assert len(restored) == 2
    assert restored[0].clause_function == ClauseFunction.PROCEDURES
    assert restored[1].clause_function == ClauseFunction.BOILERPLATE


def test_restore_legal_units_invalid_clause_function_falls_back_to_unknown():
    units_raw = [
        {
            "unit_id": "u1",
            "raw_uid": "99",
            "scope": "main",
            "title": "Unknown",
            "level": 1,
            "unit_type": "unknown",
            "clause_function": "not_valid",
            "segment_id": "seg-1",
            "segment_type": "main_contract",
            "page_start": 1,
            "page_end": 1,
            "topic_tags": [],
            "citability": {
                "citability_score": 0.5,
                "citability_band": "low",
                "has_own_text": True,
                "has_subtree_text": False,
                "is_heading_only": False,
            },
        }
    ]

    restored = restore_legal_units(
        units_raw=units_raw,
        doc_id=uuid.uuid4(),
        logger=_FakeLogger(),
    )

    assert len(restored) == 1
    assert restored[0].clause_function == ClauseFunction.UNKNOWN




