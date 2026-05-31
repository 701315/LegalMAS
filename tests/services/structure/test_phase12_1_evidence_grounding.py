"""
Тесты Phase 12.1 — evidence grounding и structural context.

Тестируем:
- Evidence quotes парсятся из LLM response.
- Grounding ratio корректно вычисляется.
- Низкий grounding ratio снижает confidence.
- Heading path строится корректно.
- Prompt содержит evidence_quotes инструкцию.
- Prompt содержит heading_path.
"""

from __future__ import annotations

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
)
from services.structure.semantic_enrichment import (
    SemanticEnrichmentPolicy,
    apply_enrichment_policy,
    build_semantic_enrichment_prompt,
    parse_llm_enrichment_response,
)
from services.structure.semantic_enrichment._policy import _verify_evidence_grounding
from services.structure.semantic_enrichment._prompting import _build_heading_path
from services.structure.semantic_enrichment._types import LLMEnrichmentProposal


def _make_unit(
    *,
    unit_id: str = "doc:clause:main:1",
    raw_uid: str = "7.2",
    title: str = "Payment Procedure",
    text: str = (
        "The Buyer shall pay the Purchase Price of USD 1,000,000 "
        "within five business days after receipt of the invoice "
        "and all supporting documents required under this Agreement."
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


class TestVerifyEvidenceGrounding:
    def test_all_quotes_grounded(self) -> None:
        text = "The Buyer shall pay the Purchase Price within five business days."
        quotes = ["shall pay the Purchase Price", "five business days"]

        grounded, ungrounded, ratio = _verify_evidence_grounding(quotes, text)

        assert len(grounded) == 2
        assert len(ungrounded) == 0
        assert ratio == 1.0

    def test_no_quotes_grounded(self) -> None:
        text = "The Buyer shall pay the Purchase Price."
        quotes = ["termination for cause", "governing law applies"]

        grounded, ungrounded, ratio = _verify_evidence_grounding(quotes, text)

        assert len(grounded) == 0
        assert len(ungrounded) == 2
        assert ratio == 0.0

    def test_partial_grounding(self) -> None:
        text = "The Buyer shall pay the Purchase Price within five business days."
        quotes = ["shall pay the Purchase Price", "arbitration clause"]

        grounded, ungrounded, ratio = _verify_evidence_grounding(quotes, text)

        assert len(grounded) == 1
        assert len(ungrounded) == 1
        assert ratio == 0.5

    def test_empty_quotes(self) -> None:
        grounded, ungrounded, ratio = _verify_evidence_grounding([], "some text")

        assert grounded == []
        assert ungrounded == []
        assert ratio == 0.0

    def test_case_insensitive_matching(self) -> None:
        text = "The Buyer SHALL PAY the Purchase Price."
        quotes = ["shall pay"]

        grounded, _, ratio = _verify_evidence_grounding(quotes, text)

        assert len(grounded) == 1
        assert ratio == 1.0


class TestEvidenceGroundingInPolicy:
    def test_low_grounding_adds_policy_note(self) -> None:
        policy = SemanticEnrichmentPolicy()
        unit = _make_unit()

        high_grounding_proposal = LLMEnrichmentProposal(
            suggested_unit_type=LegalUnitType.PAYMENT_TERM,
            suggested_topics=["payment_terms"],
            confidence=0.75,
            reasoning="Payment clause.",
            evidence_quotes=["shall pay the Purchase Price"],
        )

        low_grounding_proposal = LLMEnrichmentProposal(
            suggested_unit_type=LegalUnitType.PAYMENT_TERM,
            suggested_topics=["payment_terms"],
            confidence=0.75,
            reasoning="Payment clause.",
            evidence_quotes=["this text does not exist in clause"],
        )

        result_high = apply_enrichment_policy(
            unit,
            proposal=high_grounding_proposal,
            policy=policy,
        )
        result_low = apply_enrichment_policy(
            unit,
            proposal=low_grounding_proposal,
            policy=policy,
        )

        assert "low_evidence_grounding" not in result_high.diagnostics.get("notes", [])
        assert "low_evidence_grounding" in result_low.diagnostics.get("notes", [])


class TestValidatorParsesEvidence:
    def test_parses_evidence_quotes_list(self) -> None:
        raw = """
        {
          "suggested_unit_type": "payment_term",
          "suggested_clause_function": "obligations",
          "suggested_topics": ["payment_terms"],
          "confidence": 0.9,
          "reasoning": "Payment clause.",
          "evidence_quotes": ["shall pay the Purchase Price", "five business days"]
        }
        """

        parsed = parse_llm_enrichment_response(raw)

        assert parsed is not None
        assert len(parsed.evidence_quotes) == 2
        assert "shall pay the Purchase Price" in parsed.evidence_quotes

    def test_handles_missing_evidence_quotes(self) -> None:
        raw = """
        {
          "suggested_unit_type": "definition",
          "confidence": 0.8,
          "reasoning": "Definitions."
        }
        """

        parsed = parse_llm_enrichment_response(raw)

        assert parsed is not None
        assert parsed.evidence_quotes == []

    def test_handles_evidence_quotes_as_string(self) -> None:
        raw = """
        {
          "suggested_unit_type": "warranty",
          "confidence": 0.8,
          "reasoning": "Warranty.",
          "evidence_quotes": "represents and warrants"
        }
        """

        parsed = parse_llm_enrichment_response(raw)

        assert parsed is not None
        assert len(parsed.evidence_quotes) == 1
        assert "represents and warrants" in parsed.evidence_quotes


class TestBuildHeadingPath:
    def test_builds_path_from_uid(self) -> None:
        units = [
            _make_unit(unit_id="u-7", raw_uid="7", title="Payment"),
            _make_unit(unit_id="u-7.2", raw_uid="7.2", title="Payment Procedure"),
            _make_unit(unit_id="u-7.2.1", raw_uid="7.2.1", title="Invoice Submission"),
        ]

        path = _build_heading_path(units[2], units)

        assert "7 Payment" in path
        assert "7.2 Payment Procedure" in path

    def test_returns_empty_for_no_units(self) -> None:
        unit = _make_unit()

        path = _build_heading_path(unit, None)

        assert path == ""

    def test_root_level_path_contains_root_or_empty(self) -> None:
        unit = _make_unit(raw_uid="7")
        units = [unit]

        path = _build_heading_path(unit, units)

        assert "7" in path or path == ""


class TestPromptContainsNewFields:
    def test_prompt_contains_evidence_quotes_instruction(self) -> None:
        unit = _make_unit()

        prompt = build_semantic_enrichment_prompt(unit=unit)

        assert "evidence_quotes" in prompt

    def test_prompt_contains_heading_path(self) -> None:
        units = [
            _make_unit(unit_id="u-7", raw_uid="7", title="Платежи"),
            _make_unit(unit_id="u-7.2", raw_uid="7.2", title="Порядок оплаты"),
        ]

        prompt = build_semantic_enrichment_prompt(
            unit=units[1],
            all_units=units,
        )

        assert "heading_path" in prompt

    def test_prompt_is_russian_with_bilingual_awareness(self) -> None:
        unit = _make_unit()

        prompt = build_semantic_enrichment_prompt(unit=unit)

        assert "русском языке" in prompt
        assert "английском" in prompt
        assert "двуязычным" in prompt



        