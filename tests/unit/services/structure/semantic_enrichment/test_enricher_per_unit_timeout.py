"""
Tests for per-unit timeout behaviour in enrich_legal_units_async.

Covers:
- single slow unit times out, others succeed
- callback is invoked for each completed unit
- timed-out unit gets status=failed with reason=per_unit_timeout
"""

import asyncio

import pytest
from unittest.mock import MagicMock, patch

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
    LegalUnitsSnapshot,
)
from services.structure.semantic_enrichment._enricher import enrich_legal_units_async
from services.structure.semantic_enrichment._types import SemanticEnrichmentPolicy


def _make_unit(
    unit_id: str,
    text: str = "Some legal text for enrichment testing purposes that is definitely long enough.",
) -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid=unit_id.split(":")[-1] if ":" in unit_id else unit_id,
        scope="test_scope",
        title=f"Title {unit_id}",
        level=1,
        unit_type=LegalUnitType.UNKNOWN,
        clause_function=ClauseFunction.UNKNOWN,
        page_start=1,
        page_end=1,
        # IMPORTANT:
        # semantic enrichment eligibility currently reads own_text/subtree_text
        # via _policy._get_unit_text(), not exact_text/retrieval_text.
        own_text=text,
        subtree_text=text,
        exact_text=text,
        retrieval_text=text,
        citability=CitabilityMetrics(
            citability_score=0.8,
            citability_band="high",
            has_own_text=True,
        ),
    )


def _make_snapshot(units: list[LegalUnit]) -> LegalUnitsSnapshot:
    return LegalUnitsSnapshot(
        document_id="test-doc-id",
        document_version_id="test-doc-version-id",
        segment_id="seg-main",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        units=units,
    )


def _make_settings_mock() -> MagicMock:
    s = MagicMock()
    s.SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS = 900
    s.SEMANTIC_ENRICHMENT_PER_UNIT_TIMEOUT_SECONDS = 1
    s.SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS = 1
    s.SEMANTIC_ENRICHMENT_MAX_INFLIGHT_LLM_CALLS = 1
    s.SEMANTIC_ENRICHMENT_CACHE_ENABLED = False
    s.LLM_PROVIDER = "ollama"
    s.LLM_OLLAMA_MODEL = "test-model"
    return s


@pytest.mark.asyncio
async def test_slow_unit_times_out_others_succeed() -> None:
    """One unit hangs forever; it should get failed, others should succeed."""
    units = [_make_unit(f"unit_{i}") for i in range(3)]
    snapshot = _make_snapshot(units)

    call_count = 0

    async def _mock_llm_call(*, prompt: str, max_retries: int = 0) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            # Second unit hangs long enough to trigger per-unit timeout.
            await asyncio.sleep(999)
        return (
            '{"unit_type": "obligation", '
            '"clause_function": "obligations", '
            '"confidence": 0.9, '
            '"reasoning": "test"}'
        )

    settings_mock = _make_settings_mock()

    with (
        patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ),
        patch(
            "services.structure.semantic_enrichment._enricher._resolve_llm_info",
            return_value=("ollama", "test-model"),
        ),
        patch(
            "services.structure.semantic_enrichment._enricher._is_semantic_enrichment_cache_enabled",
            return_value=False,
        ),
        patch(
            "services.structure.semantic_enrichment._enricher._resolve_semantic_enrichment_max_inflight_llm_calls",
            return_value=1,
        ),
        patch(
            "services.structure.semantic_enrichment._llm_client.call_semantic_enrichment_llm_async",
            side_effect=_mock_llm_call,
        ),
        patch(
            "core.config.settings",
            settings_mock,
        ),
    ):
        result = await enrich_legal_units_async(
            snapshot,
            policy=SemanticEnrichmentPolicy(
                skip_technical_fallback_units=False,
                skip_heading_only_units=False,
                skip_semantically_complete_units=False,
                min_text_chars=1,
            ),
            segment_timeout_seconds=900.0,
        )

    assert len(result.enrichments) == 3

    statuses = [e.status.value for e in result.enrichments]
    assert statuses.count("failed") == 1
    assert statuses[1] == "failed"

    failed_enrichment = result.enrichments[1]
    assert failed_enrichment.decision_reason == "per_unit_timeout"


@pytest.mark.asyncio
async def test_callback_invoked_for_each_unit() -> None:
    """on_unit_enriched callback should fire for every processed unit."""
    units = [_make_unit(f"unit_{i}") for i in range(3)]
    snapshot = _make_snapshot(units)

    async def _mock_llm_call(*, prompt: str, max_retries: int = 0) -> str:
        return (
            '{"unit_type": "obligation", '
            '"clause_function": "obligations", '
            '"confidence": 0.9, '
            '"reasoning": "ok"}'
        )

    settings_mock = _make_settings_mock()
    settings_mock.SEMANTIC_ENRICHMENT_PER_UNIT_TIMEOUT_SECONDS = 60

    callback_results: list[str] = []

    def _on_enriched(enrichment) -> None:
        callback_results.append(enrichment.unit_id)

    with (
        patch(
            "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available",
            return_value=True,
        ),
        patch(
            "services.structure.semantic_enrichment._enricher._resolve_llm_info",
            return_value=("ollama", "test-model"),
        ),
        patch(
            "services.structure.semantic_enrichment._enricher._is_semantic_enrichment_cache_enabled",
            return_value=False,
        ),
        patch(
            "services.structure.semantic_enrichment._enricher._resolve_semantic_enrichment_max_inflight_llm_calls",
            return_value=1,
        ),
        patch(
            "services.structure.semantic_enrichment._llm_client.call_semantic_enrichment_llm_async",
            side_effect=_mock_llm_call,
        ),
        patch(
            "core.config.settings",
            settings_mock,
        ),
    ):
        await enrich_legal_units_async(
            snapshot,
            policy=SemanticEnrichmentPolicy(
                skip_technical_fallback_units=False,
                skip_heading_only_units=False,
                skip_semantically_complete_units=False,
                min_text_chars=1,
            ),
            segment_timeout_seconds=900.0,
            on_unit_enriched=_on_enriched,
        )

    assert len(callback_results) == 3
    assert callback_results == ["unit_0", "unit_1", "unit_2"]
