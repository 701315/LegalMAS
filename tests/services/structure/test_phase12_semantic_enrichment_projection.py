"""
Тесты для projection — построение effective enriched units.

Тестируем:
- project_single_unit с APPLIED enrichment.
- project_single_unit с SKIPPED/FAILED (без изменений).
- project_enriched_units с None enrichment_result (passthrough).
- project_enriched_units с mixed enrichments.
- Оригинальный unit НЕ мутируется.
"""

from __future__ import annotations

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitsSnapshot,
    LegalUnitType,
)
from services.structure.semantic_enrichment import (
    LLMEnrichmentProposal,
    LegalUnitEnrichment,
    LegalUnitsEnrichmentResult,
    SemanticEnrichmentStatus,
    project_enriched_units,
    project_single_unit,
)


def _make_unit(
    *,
    unit_id: str = "doc:clause:main:1",
    unit_type: LegalUnitType = LegalUnitType.UNKNOWN,
    clause_function: ClauseFunction = ClauseFunction.UNKNOWN,
    topic_tags: list[str] | None = None,
) -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid="1",
        scope="main_contract",
        title="Test",
        level=1,
        unit_type=unit_type,
        clause_function=clause_function,
        segment_id="seg-1",
        segment_type="contract",
        page_start=1,
        page_end=1,
        own_text="Some legal text.",
        subtree_text="Some legal text.",
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


def _make_applied_enrichment(
    *,
    unit_id: str,
    effective_type: LegalUnitType = LegalUnitType.PAYMENT_TERM,
    effective_function: ClauseFunction = ClauseFunction.OBLIGATIONS,
    effective_topics: list[str] | None = None,
    applied_fields: list[str] | None = None,
) -> LegalUnitEnrichment:
    return LegalUnitEnrichment(
        unit_id=unit_id,
        status=SemanticEnrichmentStatus.APPLIED,
        base_unit_type=LegalUnitType.UNKNOWN,
        base_clause_function=ClauseFunction.UNKNOWN,
        base_topic_tags=[],
        effective_unit_type=effective_type,
        effective_clause_function=effective_function,
        effective_topic_tags=list(effective_topics or ["payment_terms"]),
        applied_fields=list(applied_fields or ["unit_type", "clause_function", "topic_tags"]),
        llm_proposal=LLMEnrichmentProposal(
            suggested_unit_type=effective_type,
            suggested_clause_function=effective_function,
            suggested_topics=list(effective_topics or ["payment_terms"]),
            confidence=0.9,
            reasoning="Test.",
        ),
        decision_reason="fields_applied",
    )


def test_project_single_unit_applies_enrichment() -> None:
    unit = _make_unit()
    enrichment = _make_applied_enrichment(unit_id=unit.unit_id)

    projected = project_single_unit(unit, enrichment)

    assert projected.unit_type == LegalUnitType.PAYMENT_TERM
    assert projected.clause_function == ClauseFunction.OBLIGATIONS
    assert projected.topic_tags == ["payment_terms"]
    assert "llm_enrichment" in projected.diagnostics


def test_project_single_unit_does_not_mutate_original() -> None:
    unit = _make_unit()
    enrichment = _make_applied_enrichment(unit_id=unit.unit_id)

    _ = project_single_unit(unit, enrichment)

    assert unit.unit_type == LegalUnitType.UNKNOWN
    assert unit.clause_function == ClauseFunction.UNKNOWN
    assert unit.topic_tags == []
    assert "llm_enrichment" not in unit.diagnostics


def test_project_single_unit_skipped_keeps_original() -> None:
    unit = _make_unit(
        unit_type=LegalUnitType.WARRANTY,
        topic_tags=["warranties"],
    )
    enrichment = LegalUnitEnrichment(
        unit_id=unit.unit_id,
        status=SemanticEnrichmentStatus.SKIPPED,
        base_unit_type=LegalUnitType.WARRANTY,
        base_clause_function=ClauseFunction.REPRESENTATIONS,
        base_topic_tags=["warranties"],
        effective_unit_type=LegalUnitType.WARRANTY,
        effective_clause_function=ClauseFunction.REPRESENTATIONS,
        effective_topic_tags=["warranties"],
        decision_reason="heading_only",
    )

    projected = project_single_unit(unit, enrichment)

    assert projected.unit_type == LegalUnitType.WARRANTY
    assert projected.topic_tags == ["warranties"]
    assert projected.diagnostics["llm_enrichment"]["enrichment_status"] == "skipped"


def test_project_enriched_units_without_enrichment_result() -> None:
    units = [_make_unit(unit_id="u-1"), _make_unit(unit_id="u-2")]
    snapshot = LegalUnitsSnapshot(
        document_id="doc-1",
        document_version_id="ver-1",
        segment_id="seg-1",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        units=units,
    )

    projected = project_enriched_units(snapshot, None)

    assert len(projected) == 2
    assert projected[0].unit_type == LegalUnitType.UNKNOWN
    assert projected[1].unit_type == LegalUnitType.UNKNOWN


def test_project_enriched_units_with_mixed_enrichments() -> None:
    units = [
        _make_unit(unit_id="u-1"),
        _make_unit(unit_id="u-2", unit_type=LegalUnitType.NOTICE, topic_tags=["notices"]),
    ]
    snapshot = LegalUnitsSnapshot(
        document_id="doc-1",
        document_version_id="ver-1",
        segment_id="seg-1",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        units=units,
    )

    enrichment_result = LegalUnitsEnrichmentResult(
        document_id="doc-1",
        document_version_id="ver-1",
        segment_id="seg-1",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        enrichments=[
            _make_applied_enrichment(unit_id="u-1"),
            LegalUnitEnrichment(
                unit_id="u-2",
                status=SemanticEnrichmentStatus.NO_CHANGE,
                base_unit_type=LegalUnitType.NOTICE,
                base_clause_function=ClauseFunction.BOILERPLATE,
                base_topic_tags=["notices"],
                effective_unit_type=LegalUnitType.NOTICE,
                effective_clause_function=ClauseFunction.BOILERPLATE,
                effective_topic_tags=["notices"],
                decision_reason="proposal_matches_base",
            ),
        ],
    )

    projected = project_enriched_units(snapshot, enrichment_result)

    assert projected[0].unit_type == LegalUnitType.PAYMENT_TERM
    assert projected[0].topic_tags == ["payment_terms"]
    assert projected[1].unit_type == LegalUnitType.NOTICE
    assert projected[1].topic_tags == ["notices"]


    