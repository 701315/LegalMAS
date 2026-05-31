from __future__ import annotations

from services.structure.legal_unit_models import ClauseFunction, LegalUnitType
from services.structure.semantic_enrichment import parse_llm_enrichment_response


def test_parse_llm_enrichment_response_valid_payload() -> None:
    raw = """
    {
      "suggested_unit_type": "payment_term",
      "suggested_clause_function": "obligations",
      "suggested_topics": ["payment_terms", "purchase_price"],
      "confidence": 0.91,
      "reasoning": "The clause regulates payment timing and amount."
    }
    """

    parsed = parse_llm_enrichment_response(raw)

    assert parsed is not None
    assert parsed.suggested_unit_type == LegalUnitType.PAYMENT_TERM
    assert parsed.suggested_clause_function == ClauseFunction.OBLIGATIONS
    assert parsed.suggested_topics == ["payment_terms", "purchase_price"]
    assert parsed.confidence == 0.91
    assert parsed.reasoning == "The clause regulates payment timing and amount."


def test_parse_llm_enrichment_response_accepts_code_fences() -> None:
    raw = """
    ```json
    {
      "suggested_unit_type": "definition",
      "suggested_clause_function": "definitions",
      "suggested_topics": ["definitions"],
      "confidence": 0.88,
      "reasoning": "This is a definitions clause."
    }
    ```
    """

    parsed = parse_llm_enrichment_response(raw)

    assert parsed is not None
    assert parsed.suggested_unit_type == LegalUnitType.DEFINITION
    assert parsed.suggested_clause_function == ClauseFunction.DEFINITIONS
    assert parsed.suggested_topics == ["definitions"]
    assert parsed.confidence == 0.88


def test_parse_llm_enrichment_response_handles_invalid_enum_values() -> None:
    raw = """
    {
      "suggested_unit_type": "custom_magic_type",
      "suggested_clause_function": "custom_magic_function",
      "suggested_topics": ["payment_terms"],
      "confidence": 0.77,
      "reasoning": "Invalid enums should not break parsing."
    }
    """

    parsed = parse_llm_enrichment_response(raw)

    assert parsed is not None
    assert parsed.suggested_unit_type is None
    assert parsed.suggested_clause_function is None
    assert parsed.suggested_topics == ["payment_terms"]
    assert parsed.diagnostics["invalid_fields"]["suggested_unit_type"] == "custom_magic_type"
    assert (
        parsed.diagnostics["invalid_fields"]["suggested_clause_function"]
        == "custom_magic_function"
    )


def test_parse_llm_enrichment_response_parses_topics_from_string() -> None:
    raw = """
    {
      "suggested_unit_type": "warranty",
      "suggested_clause_function": "representations",
      "suggested_topics": "warranties, seller_warranties; liability",
      "confidence": 0.8,
      "reasoning": "Topic string should be split."
    }
    """

    parsed = parse_llm_enrichment_response(raw)

    assert parsed is not None
    assert parsed.suggested_unit_type == LegalUnitType.WARRANTY
    assert parsed.suggested_clause_function == ClauseFunction.REPRESENTATIONS
    assert parsed.suggested_topics == ["warranties", "seller_warranties", "liability"]


def test_parse_llm_enrichment_response_returns_none_for_invalid_json() -> None:
    raw = "not a json payload"

    parsed = parse_llm_enrichment_response(raw)

    assert parsed is None

    