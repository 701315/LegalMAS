from __future__ import annotations

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
)
from services.structure.semantic_enrichment import (
    LLMEnrichmentProposal,
    SemanticEnrichmentPolicy,
    SemanticEnrichmentStatus,
    apply_enrichment_policy,
    build_failed_enrichment,
    build_skipped_enrichment,
    is_unit_eligible_for_enrichment,
)


def _make_unit(
    *,
    unit_id: str = "doc:clause:main:1",
    title: str = "Payment clause",
    text: str = (
        "The Buyer shall pay the purchase price within five business days "
        "after receipt of the invoice and supporting documents."
    ),
    unit_type: LegalUnitType = LegalUnitType.UNKNOWN,
    clause_function: ClauseFunction = ClauseFunction.UNKNOWN,
    topic_tags: list[str] | None = None,
    is_heading_only: bool = False,
    is_technical_fallback: bool = False,
) -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid="1",
        scope="main_contract",
        title=title,
        level=1,
        unit_type=unit_type,
        clause_function=clause_function,
        segment_id="seg-1",
        segment_type="contract",
        page_start=1,
        page_end=1,
        own_text=None if is_heading_only else text,
        subtree_text=None if is_heading_only else text,
        own_element_ids=[],
        topic_tags=list(topic_tags or []),
        cross_refs=[],
        citability=CitabilityMetrics(
            citability_score=0.9,
            citability_band="high",
            has_own_text=not is_heading_only,
            has_subtree_text=not is_heading_only,
            is_heading_only=is_heading_only,
            recovered_via_best_effort=False,
            parse_confidence=0.9,
            is_technical_fallback=is_technical_fallback,
        ),
        node_kind="leaf",
        semantic_node_type=None,
        node_origin="unknown",
        content_mode="heading_only" if is_heading_only else "full_text",
        recovered_via_best_effort=False,
        fallback_reason="technical_fallback" if is_technical_fallback else None,
        diagnostics={},
    )


def test_is_unit_eligible_for_enrichment_skips_technical_fallback() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit(is_technical_fallback=True)

    eligible, reason = is_unit_eligible_for_enrichment(unit, policy=policy)

    assert eligible is False
    assert reason == "technical_fallback"


def test_is_unit_eligible_for_enrichment_skips_heading_only() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit(is_heading_only=True)

    eligible, reason = is_unit_eligible_for_enrichment(unit, policy=policy)

    assert eligible is False
    assert reason == "heading_only"


def test_is_unit_eligible_for_enrichment_skips_short_text() -> None:
    policy = SemanticEnrichmentPolicy(min_text_chars=50)
    unit = _make_unit(text="Short payment text.")

    eligible, reason = is_unit_eligible_for_enrichment(unit, policy=policy)

    assert eligible is False
    assert reason == "text_too_short"


def test_apply_enrichment_policy_fills_missing_type_function_and_topics() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit()

    proposal = LLMEnrichmentProposal(
        suggested_unit_type=LegalUnitType.PAYMENT_TERM,
        suggested_clause_function=None,
        suggested_topics=["payment_terms", "purchase_price"],
        confidence=0.88,
        reasoning="The clause clearly regulates payment timing and price mechanics.",
    )

    result = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    assert result.status == SemanticEnrichmentStatus.APPLIED
    assert result.effective_unit_type == LegalUnitType.PAYMENT_TERM
    assert result.effective_clause_function == ClauseFunction.OBLIGATIONS
    assert result.effective_topic_tags == ["payment_terms", "purchase_price"]
    assert "unit_type" in result.applied_fields
    assert "clause_function" in result.applied_fields
    assert "topic_tags" in result.applied_fields


def test_apply_enrichment_policy_adds_topics_to_existing_unit() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit(
        unit_type=LegalUnitType.WARRANTY,
        clause_function=ClauseFunction.REPRESENTATIONS,
        topic_tags=["warranties"],
        title="Seller warranties",
    )

    proposal = LLMEnrichmentProposal(
        suggested_unit_type=LegalUnitType.WARRANTY,
        suggested_clause_function=ClauseFunction.REPRESENTATIONS,
        suggested_topics=["seller_warranties", "liability"],
        confidence=0.84,
        reasoning="The clause contains seller-specific warranty language.",
    )

    result = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    assert result.status == SemanticEnrichmentStatus.APPLIED
    assert result.effective_unit_type == LegalUnitType.WARRANTY
    assert result.effective_clause_function == ClauseFunction.REPRESENTATIONS
    assert result.effective_topic_tags == ["warranties", "liability", "seller_warranties"]


def test_apply_enrichment_policy_rejects_override_when_policy_disallows() -> None:
    policy = SemanticEnrichmentPolicy(
        allow_override_existing_type=False,
        allow_override_existing_clause_function=False,
    )
    unit = _make_unit(
        unit_type=LegalUnitType.WARRANTY,
        clause_function=ClauseFunction.REPRESENTATIONS,
        topic_tags=["warranties"],
        title="Representations and warranties",
    )

    proposal = LLMEnrichmentProposal(
        suggested_unit_type=LegalUnitType.OBLIGATION,
        suggested_clause_function=ClauseFunction.OBLIGATIONS,
        suggested_topics=[],
        confidence=0.97,
        reasoning="The clause contains shall-statements, but base rule type is warranty.",
    )

    result = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    assert result.status == SemanticEnrichmentStatus.REJECTED
    assert result.effective_unit_type == LegalUnitType.WARRANTY
    assert result.effective_clause_function == ClauseFunction.REPRESENTATIONS
    assert result.effective_topic_tags == ["warranties"]


def test_apply_enrichment_policy_allows_override_when_enabled_and_high_confidence() -> None:
    policy = SemanticEnrichmentPolicy(
        allow_override_existing_type=True,
        allow_override_existing_clause_function=True,
        min_confidence_override_existing=0.9,
    )
    unit = _make_unit(
        unit_type=LegalUnitType.WARRANTY,
        clause_function=ClauseFunction.REPRESENTATIONS,
        topic_tags=["warranties"],
        title="Operational covenants",
    )

    proposal = LLMEnrichmentProposal(
        suggested_unit_type=LegalUnitType.OBLIGATION,
        suggested_clause_function=ClauseFunction.OBLIGATIONS,
        suggested_topics=["liability"],
        confidence=0.96,
        reasoning="The clause primarily imposes ongoing obligations rather than warranties.",
    )

    result = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    assert result.status == SemanticEnrichmentStatus.APPLIED
    assert result.effective_unit_type == LegalUnitType.OBLIGATION
    assert result.effective_clause_function == ClauseFunction.OBLIGATIONS
    assert result.effective_topic_tags == ["warranties", "liability"]


def test_apply_enrichment_policy_filters_topics_not_in_taxonomy() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit()

    proposal = LLMEnrichmentProposal(
        suggested_unit_type=LegalUnitType.PAYMENT_TERM,
        suggested_clause_function=ClauseFunction.OBLIGATIONS,
        suggested_topics=["payment_terms", "custom_non_taxonomy_tag", "purchase price"],
        confidence=0.9,
        reasoning="Payment-related clause.",
    )

    result = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    assert result.status == SemanticEnrichmentStatus.APPLIED
    assert result.effective_topic_tags == ["payment_terms", "purchase_price"]
    assert "custom_non_taxonomy_tag" in result.diagnostics["rejected_topics"]


def test_apply_enrichment_policy_returns_no_change_when_proposal_matches_base() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit(
        unit_type=LegalUnitType.DEFINITION,
        clause_function=ClauseFunction.DEFINITIONS,
        topic_tags=["definitions"],
        title="Definitions",
    )

    proposal = LLMEnrichmentProposal(
        suggested_unit_type=LegalUnitType.DEFINITION,
        suggested_clause_function=ClauseFunction.DEFINITIONS,
        suggested_topics=["definitions"],
        confidence=0.95,
        reasoning="The clause is a standard definitions section.",
    )

    result = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    assert result.status == SemanticEnrichmentStatus.NO_CHANGE
    assert result.applied_fields == []
    assert result.effective_unit_type == LegalUnitType.DEFINITION
    assert result.effective_clause_function == ClauseFunction.DEFINITIONS
    assert result.effective_topic_tags == ["definitions"]


def test_build_failed_enrichment_keeps_deterministic_fields() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit(
        unit_type=LegalUnitType.NOTICE,
        clause_function=ClauseFunction.BOILERPLATE,
        topic_tags=["notices"],
        title="Notices",
    )

    result = build_failed_enrichment(
        unit,
        policy=policy,
        reason="llm_call_failed",
        diagnostics={"error": "timeout"},
    )

    assert result.status == SemanticEnrichmentStatus.FAILED
    assert result.effective_unit_type == LegalUnitType.NOTICE
    assert result.effective_clause_function == ClauseFunction.BOILERPLATE
    assert result.effective_topic_tags == ["notices"]
    assert result.decision_reason == "llm_call_failed"
    assert result.diagnostics["error"] == "timeout"


def test_build_skipped_enrichment_keeps_deterministic_fields() -> None:
    policy = SemanticEnrichmentPolicy()
    unit = _make_unit(
        unit_type=LegalUnitType.NOTICE,
        clause_function=ClauseFunction.BOILERPLATE,
        topic_tags=["notices"],
        title="Notices",
    )

    result = build_skipped_enrichment(
        unit,
        policy=policy,
        reason="heading_only",
    )

    assert result.status == SemanticEnrichmentStatus.SKIPPED
    assert result.effective_unit_type == LegalUnitType.NOTICE
    assert result.effective_clause_function == ClauseFunction.BOILERPLATE
    assert result.effective_topic_tags == ["notices"]
    assert result.decision_reason == "heading_only"


    