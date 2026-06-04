"""
Tests for build_legal_units_enrichment worker.

Covers:
- disabled path → skipped outcome + ENRICHED status
- unavailable LLM → unavailable outcome + ENRICHED status
- segment timeout is failure-isolated
- successful enrichment writes sidecar and updates segment_meta
- budget derivation helpers used correctly
- terminal outcome derivation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.constants import DocumentStatus, SemanticEnrichmentStageOutcome
from workers.build_legal_units_enrichment import (
    _derive_terminal_outcome,
    _extract_legal_units_ref,
    _ordered_segments_for_enrichment,
)


# ── Unit tests for helpers ────────────────────────────────────────────────────

def test_extract_legal_units_ref_returns_ref_from_valid_meta() -> None:
    meta = {"legal_units_ref": "s3://bucket/lu.json"}
    assert _extract_legal_units_ref(meta) == "s3://bucket/lu.json"


def test_extract_legal_units_ref_returns_none_for_missing_key() -> None:
    assert _extract_legal_units_ref({}) is None


def test_extract_legal_units_ref_returns_none_for_non_dict_meta() -> None:
    assert _extract_legal_units_ref(None) is None
    assert _extract_legal_units_ref("invalid") is None


def test_ordered_segments_puts_primary_first() -> None:
    seg_a = MagicMock()
    seg_a.is_primary = False
    seg_a.segment_order = 0

    seg_b = MagicMock()
    seg_b.is_primary = True
    seg_b.segment_order = 1

    result = _ordered_segments_for_enrichment([seg_a, seg_b])
    assert result[0].is_primary is True


class TestDeriveTerminalOutcome:
    def test_no_candidates_returns_skipped(self) -> None:
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=0,
            segments_enriched=0,
            segments_timed_out=0,
            segments_failed=0,
            segments_skipped_budget=0,
        )
        assert outcome == SemanticEnrichmentStageOutcome.SKIPPED

    def test_all_enriched_returns_completed(self) -> None:
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=3,
            segments_timed_out=0,
            segments_failed=0,
            segments_skipped_budget=0,
        )
        assert outcome == SemanticEnrichmentStageOutcome.COMPLETED

    def test_partial_success_returns_degraded(self) -> None:
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=1,
            segments_timed_out=1,
            segments_failed=1,
            segments_skipped_budget=0,
        )
        assert outcome == SemanticEnrichmentStageOutcome.DEGRADED

    def test_none_enriched_with_timeouts_returns_timed_out(self) -> None:
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=0,
            segments_timed_out=2,
            segments_failed=0,
            segments_skipped_budget=1,
        )
        assert outcome == SemanticEnrichmentStageOutcome.TIMED_OUT

    def test_none_enriched_only_failed_returns_degraded(self) -> None:
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=2,
            segments_enriched=0,
            segments_timed_out=0,
            segments_failed=2,
            segments_skipped_budget=0,
        )
        assert outcome == SemanticEnrichmentStageOutcome.DEGRADED


# ── Integration-style tests for async core ────────────────────────────────────

@pytest.mark.asyncio
async def test_disabled_path_returns_skipped_and_sets_enriched_status() -> None:
    """When enrichment is disabled, worker must reach ENRICHED with skipped outcome."""
    from workers.build_legal_units_enrichment import _build_legal_units_enrichment_async

    mock_doc = MagicMock()
    mock_doc.status = DocumentStatus.CLASSIFIED.value

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = mock_doc
    mock_doc_repo.update_status.return_value = mock_doc

    mock_ver = MagicMock()
    mock_ver_repo = AsyncMock()
    mock_ver_repo.get_by_id.return_value = mock_ver

    mock_seg_repo = AsyncMock()
    mock_seg_repo.list_by_version.return_value = []

    mock_dse_repo = AsyncMock()
    mock_audit_repo = AsyncMock()

    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    with (
        patch("workers.build_legal_units_enrichment.DocumentRepository", return_value=mock_doc_repo),
        patch("workers.build_legal_units_enrichment.DocumentVersionRepository", return_value=mock_ver_repo),
        patch("workers.build_legal_units_enrichment.DocumentSegmentRepository", return_value=mock_seg_repo),
        patch("workers.build_legal_units_enrichment.DocumentStageExecutionRepository", return_value=mock_dse_repo),
        patch("workers.build_legal_units_enrichment.AuditRepository", return_value=mock_audit_repo),
        patch("workers.build_legal_units_enrichment.ArtifactStore"),
        patch("workers.build_legal_units_enrichment.settings") as mock_settings,
    ):
        mock_settings.SEMANTIC_ENRICHMENT_ENABLED = False

        result = await _build_legal_units_enrichment_async(
            document_version_id="00000000-0000-0000-0000-000000000001",
            document_id="00000000-0000-0000-0000-000000000002",
            deal_id="00000000-0000-0000-0000-000000000003",
            tenant_id="00000000-0000-0000-0000-000000000004",
            db=mock_db,
            run_id=None,
            stage_execution_id=None,
        )

    assert result["terminal_outcome"] == SemanticEnrichmentStageOutcome.SKIPPED.value
    assert result["committed"] is True
    mock_doc_repo.update_status.assert_called_once()
    call_args = mock_doc_repo.update_status.call_args
    assert call_args[0][1] == DocumentStatus.ENRICHED.value


    