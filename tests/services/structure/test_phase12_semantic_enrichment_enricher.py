"""
Тесты для enricher — orchestrator per-unit enrichment.

Тестируем:
- enrich_single_unit с мокнутым LLM.
- enrich_legal_units с мокнутым LLM.
- Обработку ошибок LLM (timeout, bad JSON).
- Корректную передачу соседей (previous/next).
- Skipping ineligible units.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitsSnapshot,
    LegalUnitType,
)
from services.structure.semantic_enrichment import (
    SemanticEnrichmentPolicy,
    SemanticEnrichmentStatus,
    enrich_legal_units,
    enrich_single_unit,
)


def _make_unit(
    *,
    unit_id: str = "doc:clause:main:1",
    title: str = "Payment",
    text: str = (
        "The Buyer shall pay the purchase price of USD 1,000,000 "
        "within five business days after receipt of the invoice "
        "and all supporting documents required under this Agreement."
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


def _make_snapshot(units: list[LegalUnit]) -> LegalUnitsSnapshot:
    return LegalUnitsSnapshot(
        document_id="doc-1",
        document_version_id="ver-1",
        segment_id="seg-1",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        units=units,
    )


def _mock_llm_response(
    *,
    unit_type: str = "payment_term",
    clause_function: str = "obligations",
    topics: list[str] | None = None,
    confidence: float = 0.9,
    reasoning: str = "Payment-related clause.",
) -> str:
    return (json.dumps(
        {
            "suggested_unit_type": unit_type,
            "suggested_clause_function": clause_function,
            "suggested_topics": topics or ["payment_terms"],
            "confidence": confidence,
            "reasoning": reasoning,
        }), {})


LLM_CLIENT_PATH = (
    "services.structure.semantic_enrichment._enricher.call_semantic_enrichment_llm"
)


class TestEnrichSingleUnit:
    def test_skips_technical_fallback(self) -> None:
        policy = SemanticEnrichmentPolicy()
        unit = _make_unit(is_technical_fallback=True)

        result = enrich_single_unit(
            unit=unit,
            previous_unit=None,
            next_unit=None,
            policy=policy,
            document_id="doc-1",
        )

        assert result.status == SemanticEnrichmentStatus.SKIPPED
        assert result.decision_reason == "technical_fallback"

    def test_skips_heading_only(self) -> None:
        policy = SemanticEnrichmentPolicy()
        unit = _make_unit(is_heading_only=True)

        result = enrich_single_unit(
            unit=unit,
            previous_unit=None,
            next_unit=None,
            policy=policy,
            document_id="doc-1",
        )

        assert result.status == SemanticEnrichmentStatus.SKIPPED

    @patch(LLM_CLIENT_PATH)
    def test_fills_unknown_type_from_llm(self, mock_llm) -> None:
        mock_llm.return_value = _mock_llm_response()
        policy = SemanticEnrichmentPolicy()
        unit = _make_unit()

        result = enrich_single_unit(
            unit=unit,
            previous_unit=None,
            next_unit=None,
            policy=policy,
            document_id="doc-1",
        )

        assert result.status == SemanticEnrichmentStatus.APPLIED
        assert result.effective_unit_type == LegalUnitType.PAYMENT_TERM
        assert "unit_type" in result.applied_fields

    @patch(LLM_CLIENT_PATH)
    def test_handles_llm_timeout(self, mock_llm) -> None:
        mock_llm.side_effect = RuntimeError("Connection timeout")
        policy = SemanticEnrichmentPolicy()
        unit = _make_unit()

        result = enrich_single_unit(
            unit=unit,
            previous_unit=None,
            next_unit=None,
            policy=policy,
            document_id="doc-1",
        )

        assert result.status == SemanticEnrichmentStatus.FAILED
        assert "llm_call_failed" in (result.decision_reason or "")

    @patch(LLM_CLIENT_PATH)
    def test_handles_invalid_json_response(self, mock_llm) -> None:
        mock_llm.return_value = ("not a json response", {})
        policy = SemanticEnrichmentPolicy()
        unit = _make_unit()

        result = enrich_single_unit(
            unit=unit,
            previous_unit=None,
            next_unit=None,
            policy=policy,
            document_id="doc-1",
        )

        assert result.status == SemanticEnrichmentStatus.FAILED
        assert result.decision_reason == "invalid_llm_response"


# tests/services/structure/test_phase12_semantic_enrichment_enricher.py

class TestEnrichLegalUnits:
    @patch(LLM_CLIENT_PATH)
    def test_enriches_snapshot_with_mixed_units(self, mock_llm) -> None:
        mock_llm.return_value = _mock_llm_response()

        units = [
            _make_unit(
                unit_id="u-1",
                title="Payment",
                text=(
                    "The Buyer shall pay the Purchase Price of USD 1,000,000 "
                    "within five business days after receipt of the invoice "
                    "and all supporting documents required under this Agreement."
                ),
            ),
            _make_unit(unit_id="u-2", is_heading_only=True),
            _make_unit(unit_id="u-3", is_technical_fallback=True),
            _make_unit(
                unit_id="u-4",
                title="Notices",
                text=(
                    "All notices, requests and other communications under this "
                    "Agreement shall be made in writing and delivered by hand, "
                    "courier or email to the addresses set out in Schedule 1."
                ),
            ),
        ]
        snapshot = _make_snapshot(units)
        policy = SemanticEnrichmentPolicy()

        result = enrich_legal_units(snapshot, policy=policy)

        assert len(result.enrichments) == 4
        statuses = [e.status for e in result.enrichments]

        assert statuses[0] == SemanticEnrichmentStatus.APPLIED
        assert statuses[1] == SemanticEnrichmentStatus.SKIPPED
        assert statuses[2] == SemanticEnrichmentStatus.SKIPPED
        assert statuses[3] == SemanticEnrichmentStatus.APPLIED

    @patch(LLM_CLIENT_PATH)
    def test_enrichment_result_has_correct_metadata(self, mock_llm) -> None:
        mock_llm.return_value = _mock_llm_response()

        units = [
            _make_unit(
                text=(
                    "The Buyer shall pay the Purchase Price within five business "
                    "days after receipt of the invoice and supporting documents."
                )
            )
        ]
        snapshot = _make_snapshot(units)

        result = enrich_legal_units(snapshot)

        assert result.document_id == "doc-1"
        assert result.segment_id == "seg-1"
        assert result.policy_version == "phase12_v1"
        assert result.prompt_version == "phase12_semantic_enrichment_v3_ru"


