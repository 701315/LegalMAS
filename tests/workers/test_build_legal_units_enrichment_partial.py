"""
Tests for partial persistence in build_legal_units_enrichment worker.

Covers:
- _build_partial_enrichment_result produces structurally complete sidecar
- units not reached get skipped status with correct reason
- build_warnings contains partial marker
"""

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
    LegalUnitsSnapshot,
)
from services.structure.semantic_enrichment._types import (
    LegalUnitEnrichment,
    SemanticEnrichmentPolicy,
    SemanticEnrichmentStatus,
)
from workers.build_legal_units_enrichment import _build_partial_enrichment_result


def _make_unit(unit_id: str) -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid=unit_id,
        scope="test",
        title=f"Title {unit_id}",
        level=1,
        unit_type=LegalUnitType.OBLIGATION,
        clause_function=ClauseFunction.OBLIGATIONS,
        page_start=1,
        page_end=1,
        own_text="Test text that is long enough.",
        subtree_text="Test text that is long enough.",
        exact_text="Test text that is long enough.",
        retrieval_text="Test text that is long enough.",
        citability=CitabilityMetrics(
            citability_score=0.8,
            citability_band="high",
        ),
    )


def _make_enrichment(unit_id: str, status: str = "applied") -> LegalUnitEnrichment:
    return LegalUnitEnrichment(
        unit_id=unit_id,
        status=SemanticEnrichmentStatus(status),
        base_unit_type=LegalUnitType.UNKNOWN,
        base_clause_function=ClauseFunction.UNKNOWN,
        effective_unit_type=LegalUnitType.OBLIGATION,
        effective_clause_function=ClauseFunction.OBLIGATIONS,
        applied_fields=["unit_type", "clause_function"],
    )


def _make_snapshot(unit_ids: list[str]) -> LegalUnitsSnapshot:
    return LegalUnitsSnapshot(
        document_id="doc-1",
        document_version_id="ver-1",
        segment_id="seg-main",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        units=[_make_unit(uid) for uid in unit_ids],
    )


class TestBuildPartialEnrichmentResult:
    def test_all_units_accounted_for(self) -> None:
        """Every unit in snapshot must appear in result enrichments."""
        snapshot = _make_snapshot(["u1", "u2", "u3", "u4", "u5"])
        partial = [
            _make_enrichment("u1"),
            _make_enrichment("u2"),
            _make_enrichment("u3"),
        ]
        policy = SemanticEnrichmentPolicy()

        result = _build_partial_enrichment_result(
            snapshot=snapshot,
            partial_enrichments=partial,
            policy=policy,
            llm_provider="ollama",
            llm_model="test-model",
        )

        assert len(result.enrichments) == 5
        unit_ids = [e.unit_id for e in result.enrichments]
        assert set(unit_ids) == {"u1", "u2", "u3", "u4", "u5"}

    def test_processed_units_keep_original_status(self) -> None:
        snapshot = _make_snapshot(["u1", "u2", "u3"])
        partial = [
            _make_enrichment("u1", "applied"),
            _make_enrichment("u2", "failed"),
        ]
        policy = SemanticEnrichmentPolicy()

        result = _build_partial_enrichment_result(
            snapshot=snapshot,
            partial_enrichments=partial,
            policy=policy,
            llm_provider="ollama",
            llm_model="test-model",
        )

        by_id = {e.unit_id: e for e in result.enrichments}
        assert by_id["u1"].status == SemanticEnrichmentStatus.APPLIED
        assert by_id["u2"].status == SemanticEnrichmentStatus.FAILED

    def test_unreached_units_get_skipped_with_correct_reason(self) -> None:
        snapshot = _make_snapshot(["u1", "u2", "u3"])
        partial = [_make_enrichment("u1")]
        policy = SemanticEnrichmentPolicy()

        result = _build_partial_enrichment_result(
            snapshot=snapshot,
            partial_enrichments=partial,
            policy=policy,
            llm_provider="ollama",
            llm_model="test-model",
        )

        by_id = {e.unit_id: e for e in result.enrichments}
        assert by_id["u2"].status == SemanticEnrichmentStatus.SKIPPED
        assert by_id["u2"].decision_reason == "segment_timeout_not_reached"
        assert by_id["u3"].status == SemanticEnrichmentStatus.SKIPPED
        assert by_id["u3"].decision_reason == "segment_timeout_not_reached"

    def test_build_warnings_contains_partial_marker(self) -> None:
        snapshot = _make_snapshot(["u1", "u2"])
        partial = [_make_enrichment("u1")]
        policy = SemanticEnrichmentPolicy()

        result = _build_partial_enrichment_result(
            snapshot=snapshot,
            partial_enrichments=partial,
            policy=policy,
            llm_provider="ollama",
            llm_model="test-model",
        )

        assert "partial_enrichment_segment_timeout" in result.build_warnings

    def test_status_counts_reflect_partial_state(self) -> None:
        snapshot = _make_snapshot(["u1", "u2", "u3", "u4"])
        partial = [
            _make_enrichment("u1", "applied"),
            _make_enrichment("u2", "failed"),
        ]
        policy = SemanticEnrichmentPolicy()

        result = _build_partial_enrichment_result(
            snapshot=snapshot,
            partial_enrichments=partial,
            policy=policy,
            llm_provider="ollama",
            llm_model="test-model",
        )

        counts = result.status_counts
        assert counts.get("applied") == 1
        assert counts.get("failed") == 1
        assert counts.get("skipped") == 2

    def test_empty_partial_enrichments_all_skipped(self) -> None:
        """Edge case: timeout before any unit processed."""
        snapshot = _make_snapshot(["u1", "u2"])
        partial: list[LegalUnitEnrichment] = []
        policy = SemanticEnrichmentPolicy()

        result = _build_partial_enrichment_result(
            snapshot=snapshot,
            partial_enrichments=partial,
            policy=policy,
            llm_provider="ollama",
            llm_model="test-model",
        )

        assert len(result.enrichments) == 2
        assert all(
            e.status == SemanticEnrichmentStatus.SKIPPED
            for e in result.enrichments
        )

    def test_to_dict_serialization_works(self) -> None:
        """Partial result must be serializable for MinIO sidecar."""
        snapshot = _make_snapshot(["u1", "u2", "u3"])
        partial = [_make_enrichment("u1")]
        policy = SemanticEnrichmentPolicy()

        result = _build_partial_enrichment_result(
            snapshot=snapshot,
            partial_enrichments=partial,
            policy=policy,
            llm_provider="ollama",
            llm_model="test-model",
        )

        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["stats"]["total_units"] == 3
        assert len(d["enrichments"]) == 3
        assert "partial_enrichment_segment_timeout" in d["stats"]["build_warnings"]
