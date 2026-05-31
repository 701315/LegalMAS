"""
Тесты Phase 12.1.4 + 12.1.5 — Preflight Gate и Runtime Config.

Тестируем:
- make_policy_from_settings() читает из settings.
- make_policy_from_settings() возвращает defaults при отсутствии settings.
- is_semantic_enrichment_llm_available() не бросает исключений.
- enrich_legal_units() пропускает все units когда LLM недоступна.
- enrich_legal_units() возвращает build_warnings при недоступном LLM.
"""

from __future__ import annotations

from unittest.mock import patch

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitsSnapshot,
    LegalUnitType,
)
from services.structure.semantic_enrichment import (
    SemanticEnrichmentStatus,
    enrich_legal_units,
    is_semantic_enrichment_llm_available,
    make_policy_from_settings,
)
from services.structure.semantic_enrichment._policy import SemanticEnrichmentPolicy


def _make_unit(unit_id: str = "u-1") -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid="1",
        scope="main_contract",
        title="Платёж",
        level=1,
        unit_type=LegalUnitType.UNKNOWN,
        clause_function=ClauseFunction.UNKNOWN,
        segment_id="seg-1",
        segment_type="contract",
        page_start=1,
        page_end=1,
        own_text=(
            "Покупатель обязан уплатить покупную цену в размере 1 000 000 руб. "
            "в течение пяти рабочих дней с момента получения счёта."
        ),
        subtree_text=None,
        own_element_ids=[],
        topic_tags=[],
        cross_refs=[],
        citability=CitabilityMetrics(
            citability_score=0.9,
            citability_band="high",
            has_own_text=True,
            has_subtree_text=False,
        ),
        node_kind="leaf",
        diagnostics={},
    )


def _make_snapshot(units: list[LegalUnit] | None = None) -> LegalUnitsSnapshot:
    return LegalUnitsSnapshot(
        document_id="doc-1",
        document_version_id="ver-1",
        segment_id="seg-1",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        units=[_make_unit()] if units is None else units,
    )


# ── make_policy_from_settings ─────────────────────────────────────────────


class TestMakePolicyFromSettings:
    def test_returns_policy_instance(self) -> None:
        policy = make_policy_from_settings()

        assert isinstance(policy, SemanticEnrichmentPolicy)

    def test_policy_has_expected_defaults(self) -> None:
        policy = make_policy_from_settings()

        assert 0.0 < policy.min_confidence_fill_missing <= 1.0
        assert 0.0 < policy.min_confidence_add_topics <= 1.0
        assert 0.0 < policy.min_confidence_override_existing <= 1.0
        assert isinstance(policy.allow_override_existing_type, bool)
        assert isinstance(policy.allow_add_topics_to_existing, bool)
        assert policy.max_topics_from_llm > 0
        assert policy.min_text_chars > 0

    def test_policy_reads_from_settings(self) -> None:
        with patch("core.config.settings") as mock_settings:
            mock_settings.SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_FILL = 0.80
            mock_settings.SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_TOPICS = 0.80
            mock_settings.SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_OVERRIDE = 0.95
            mock_settings.SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_TYPE = True
            mock_settings.SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_FUNCTION = False
            mock_settings.SEMANTIC_ENRICHMENT_ALLOW_ADD_TOPICS = True
            mock_settings.SEMANTIC_ENRICHMENT_MAX_TOPICS_FROM_LLM = 5
            mock_settings.SEMANTIC_ENRICHMENT_MIN_TEXT_CHARS = 60

            policy = make_policy_from_settings()

        assert policy.min_confidence_fill_missing == 0.80
        assert policy.min_confidence_override_existing == 0.95
        assert policy.allow_override_existing_type is True
        assert policy.max_topics_from_llm == 5
        assert policy.min_text_chars == 60


# ── is_semantic_enrichment_llm_available ─────────────────────────────────


class TestIsSemanticEnrichmentLLMAvailable:
    def test_returns_bool_without_exception(self) -> None:
        result = is_semantic_enrichment_llm_available()

        assert isinstance(result, bool)

    def test_returns_false_when_llm_client_raises(self) -> None:
        with patch(
            "engine.llm.client.LLMClient.is_available",
            side_effect=RuntimeError("is_available failed"),
        ):
            result = is_semantic_enrichment_llm_available()

        assert result is False


# ── Preflight Gate in enrich_legal_units ─────────────────────────────────


LLM_AVAILABLE_PATH = (
    "services.structure.semantic_enrichment._enricher.is_semantic_enrichment_llm_available"
)


class TestPreflightGateInEnrichLegalUnits:
    def test_all_units_skipped_when_llm_unavailable(self) -> None:
        snapshot = _make_snapshot(
            units=[_make_unit("u-1"), _make_unit("u-2"), _make_unit("u-3")]
        )

        with patch(LLM_AVAILABLE_PATH, return_value=False):
            result = enrich_legal_units(snapshot)

        assert len(result.enrichments) == 3
        for enrichment in result.enrichments:
            assert enrichment.status == SemanticEnrichmentStatus.SKIPPED
            assert enrichment.decision_reason == "llm_unavailable"

    def test_build_warnings_contain_unavailable_when_llm_unavailable(self) -> None:
        snapshot = _make_snapshot()

        with patch(LLM_AVAILABLE_PATH, return_value=False):
            result = enrich_legal_units(snapshot)

        assert any("llm_unavailable" in w for w in result.build_warnings)

    def test_deterministic_baseline_preserved_when_llm_unavailable(self) -> None:
        unit = _make_unit()
        unit.unit_type = LegalUnitType.WARRANTY
        unit.topic_tags = ["warranties"]
        snapshot = _make_snapshot(units=[unit])

        with patch(LLM_AVAILABLE_PATH, return_value=False):
            result = enrich_legal_units(snapshot)

        enrichment = result.enrichments[0]
        assert enrichment.effective_unit_type == LegalUnitType.WARRANTY
        assert enrichment.effective_topic_tags == ["warranties"]

    def test_empty_snapshot_returns_empty_result(self) -> None:
        snapshot = _make_snapshot(units=[])

        with patch(LLM_AVAILABLE_PATH, return_value=False):
            result = enrich_legal_units(snapshot)

        assert len(result.enrichments) == 0
        assert result.build_warnings == []


        