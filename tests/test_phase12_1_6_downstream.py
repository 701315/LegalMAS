"""
Tests for Phase 12.1.6 — Downstream Consumption of enrichment sidecar.

Покрывают:
1. ArtifactPath.legal_units_enrichment_v1() — корректность пути
2. LegalUnitsEnrichmentResult.from_dict() — round-trip сериализации
3. LegalUnitsSnapshot.from_dict() — round-trip сериализации
4. _apply_enrichment_if_available() — projection применяется корректно
5. _apply_enrichment_if_available() — fallback при отсутствии sidecar
6. _apply_enrichment_if_available() — fallback при ошибке загрузки
7. _apply_enrichment_if_available() — fallback при 0 applied enrichments
8. load_legal_units_from_segments() — baseline path (нет enrichment_ref)
9. load_legal_units_from_segments() — enrichment path (есть enrichment_ref)
10. load_legal_units_from_segments() — projection failure → baseline
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from storage.artifact_store import ArtifactPath
from services.structure.legal_unit_models import (
    LegalUnit,
    LegalUnitType,
    ClauseFunction,
    CitabilityMetrics,
    LegalUnitsSnapshot,
)
from services.structure.semantic_enrichment._types import (
    LegalUnitsEnrichmentResult,
    LegalUnitEnrichment,
    SemanticEnrichmentStatus,
    LLMEnrichmentProposal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_legal_unit(
    unit_id: str = "u1",
    unit_type: LegalUnitType = LegalUnitType.UNKNOWN,
    clause_function: ClauseFunction = ClauseFunction.UNKNOWN,
    topic_tags: list[str] | None = None,
) -> LegalUnit:
    return LegalUnit(
        unit_id=unit_id,
        raw_uid=f"raw_{unit_id}",
        scope="main",
        title=f"Clause {unit_id}",
        level=1,
        unit_type=unit_type,
        clause_function=clause_function,
        topic_tags=topic_tags or [],
        citability=CitabilityMetrics(
            citability_score=0.8,
            citability_band="high",
            has_own_text=True,
        ),
        own_text="Payment shall be made within 30 days.",
    )


def _make_snapshot(units: list[LegalUnit] | None = None) -> LegalUnitsSnapshot:
    return LegalUnitsSnapshot(
        document_id="doc1",
        document_version_id="ver1",
        segment_id="seg1",
        segment_type="main_contract",
        segment_order=0,
        is_primary_segment=True,
        units=[_make_legal_unit()] if units is None else units,
    )


def _make_enrichment_result(
    applied: bool = True,
    unit_id: str = "u1",
) -> LegalUnitsEnrichmentResult:
    status = SemanticEnrichmentStatus.APPLIED if applied else SemanticEnrichmentStatus.SKIPPED
    enrichment = LegalUnitEnrichment(
        unit_id=unit_id,
        status=status,
        base_unit_type=LegalUnitType.UNKNOWN,
        base_clause_function=ClauseFunction.UNKNOWN,
        base_topic_tags=[],
        effective_unit_type=LegalUnitType.PAYMENT_TERM,
        effective_clause_function=ClauseFunction.OBLIGATIONS,
        effective_topic_tags=["payment", "deadline"],
        applied_fields=["unit_type", "clause_function", "topic_tags"] if applied else [],
        llm_proposal=LLMEnrichmentProposal(
            suggested_unit_type=LegalUnitType.PAYMENT_TERM,
            suggested_clause_function=ClauseFunction.OBLIGATIONS,
            suggested_topics=["payment", "deadline"],
            confidence=0.91,
            reasoning="Payment clause",
            evidence_quotes=["Payment shall be made within 30 days"],
        ),
    )
    return LegalUnitsEnrichmentResult(
        document_id="doc1",
        document_version_id="ver1",
        segment_id="seg1",
        segment_type="main_contract",
        segment_order=0,
        is_primary_segment=True,
        enrichments=[enrichment],
    )


# ---------------------------------------------------------------------------
# 1. ArtifactPath.legal_units_enrichment_v1
# ---------------------------------------------------------------------------

class TestArtifactPathEnrichmentV1:
    def test_path_format(self):
        path = ArtifactPath.legal_units_enrichment_v1(
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            segment_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert path == (
            "tenants/t1/deals/d1/structures/doc1/"
            "legal_units_enrichment_550e8400.json"
        )

    def test_path_uses_short_id(self):
        path = ArtifactPath.legal_units_enrichment_v1(
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            segment_id="abcdef12-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        )
        assert "legal_units_enrichment_abcdef12.json" in path

    def test_path_differs_from_baseline(self):
        baseline = ArtifactPath.legal_units_v1(
            tenant_id="t1", deal_id="d1",
            document_id="doc1", segment_id="aabbccdd-xxxx",
        )
        enrichment = ArtifactPath.legal_units_enrichment_v1(
            tenant_id="t1", deal_id="d1",
            document_id="doc1", segment_id="aabbccdd-xxxx",
        )
        assert baseline != enrichment
        assert "enrichment" in enrichment
        assert "enrichment" not in baseline


# ---------------------------------------------------------------------------
# 2. LegalUnitsEnrichmentResult.from_dict — round-trip
# ---------------------------------------------------------------------------

class TestLegalUnitsEnrichmentResultFromDict:
    def test_roundtrip_full(self):
        original = _make_enrichment_result(applied=True)
        data = original.to_dict()
        restored = LegalUnitsEnrichmentResult.from_dict(data)

        assert restored.document_id == original.document_id
        assert restored.segment_id == original.segment_id
        assert restored.is_primary_segment == original.is_primary_segment
        assert len(restored.enrichments) == 1

        e = restored.enrichments[0]
        assert e.unit_id == "u1"
        assert e.status == SemanticEnrichmentStatus.APPLIED
        assert e.effective_unit_type == LegalUnitType.PAYMENT_TERM
        assert e.effective_clause_function == ClauseFunction.OBLIGATIONS
        assert "payment" in e.effective_topic_tags
        assert "unit_type" in e.applied_fields

    def test_roundtrip_skipped_enrichment(self):
        original = _make_enrichment_result(applied=False)
        data = original.to_dict()
        restored = LegalUnitsEnrichmentResult.from_dict(data)

        assert restored.enrichments[0].status == SemanticEnrichmentStatus.SKIPPED
        assert restored.enrichments[0].applied_fields == []

    def test_from_dict_tolerates_missing_fields(self):
        # Минимальный dict — не должен упасть
        minimal = {"document_id": "doc1", "enrichments": []}
        result = LegalUnitsEnrichmentResult.from_dict(minimal)
        assert result.document_id == "doc1"
        assert result.enrichments == []

    def test_from_dict_skips_invalid_enrichment_entries(self):
        data = _make_enrichment_result().to_dict()
        data["enrichments"].append("not_a_dict")  # невалидная запись
        result = LegalUnitsEnrichmentResult.from_dict(data)
        # Невалидная запись пропускается, валидная сохраняется
        assert len(result.enrichments) == 1


# ---------------------------------------------------------------------------
# 3. LegalUnitsSnapshot.from_dict — round-trip
# ---------------------------------------------------------------------------

class TestLegalUnitsSnapshotFromDict:
    def test_roundtrip(self):
        unit = _make_legal_unit("u1", LegalUnitType.OBLIGATION, ClauseFunction.OBLIGATIONS)
        snapshot = _make_snapshot([unit])
        data = snapshot.to_dict()
        restored = LegalUnitsSnapshot.from_dict(data)

        assert restored.document_id == "doc1"
        assert restored.segment_id == "seg1"
        assert len(restored.units) == 1

        u = restored.units[0]
        assert u.unit_id == "u1"
        assert u.unit_type == LegalUnitType.OBLIGATION
        assert u.clause_function == ClauseFunction.OBLIGATIONS

    def test_from_dict_tolerates_empty_units(self):
        snapshot = _make_snapshot([])
        data = snapshot.to_dict()
        restored = LegalUnitsSnapshot.from_dict(data)
        assert restored.units == []

    def test_from_dict_unknown_unit_type(self):
        snapshot = _make_snapshot([_make_legal_unit()])
        data = snapshot.to_dict()
        data["units"][0]["unit_type"] = "totally_invalid_type"
        restored = LegalUnitsSnapshot.from_dict(data)
        assert restored.units[0].unit_type == LegalUnitType.UNKNOWN


# ---------------------------------------------------------------------------
# 4–7. _apply_enrichment_if_available
# ---------------------------------------------------------------------------

class TestApplyEnrichmentIfAvailable:
    """
    Тесты для _apply_enrichment_if_available().
    Используем unit-level testing с мок-стором.
    """

    @pytest.mark.asyncio
    async def test_no_enrichment_ref_returns_baseline(self):
        from engine.content._document_content_semantic import (
            _apply_enrichment_if_available,
        )

        units_raw = [{"unit_id": "u1", "unit_type": "unknown"}]
        result = await _apply_enrichment_if_available(
            units_raw=units_raw,
            snapshot_dict={},
            enrichment_ref=None,
            artifact_store=MagicMock(),
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            segment_id="seg1",
            logger=MagicMock(),
        )
        assert result is units_raw

    @pytest.mark.asyncio
    async def test_projection_applied_enriches_units(self):
        from engine.content._document_content_semantic import (
            _apply_enrichment_if_available,
        )

        unit = _make_legal_unit("u1", LegalUnitType.UNKNOWN)
        snapshot = _make_snapshot([unit])
        enrichment_result = _make_enrichment_result(applied=True, unit_id="u1")

        mock_store = MagicMock()
        mock_store.get_json.return_value = enrichment_result.to_dict()

        units_raw = [u.to_dict() for u in snapshot.units]
        snapshot_dict = snapshot.to_dict()

        result = await _apply_enrichment_if_available(
            units_raw=units_raw,
            snapshot_dict=snapshot_dict,
            enrichment_ref="s3://bucket/enrichment.json",
            artifact_store=mock_store,
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            segment_id="seg1",
            logger=MagicMock(),
        )

        assert len(result) == 1
        assert result[0]["unit_type"] == "payment_term"
        assert result[0]["clause_function"] == "obligations"
        assert "payment" in result[0]["topic_tags"]

    @pytest.mark.asyncio
    async def test_store_error_returns_baseline(self):
        from engine.content._document_content_semantic import (
            _apply_enrichment_if_available,
        )

        mock_store = MagicMock()
        mock_store.get_json.side_effect = Exception("MinIO unavailable")

        units_raw = [{"unit_id": "u1", "unit_type": "unknown"}]
        result = await _apply_enrichment_if_available(
            units_raw=units_raw,
            snapshot_dict={},
            enrichment_ref="s3://bucket/enrichment.json",
            artifact_store=mock_store,
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            segment_id="seg1",
            logger=MagicMock(),
        )
        assert result is units_raw

    @pytest.mark.asyncio
    async def test_zero_applied_returns_baseline(self):
        from engine.content._document_content_semantic import (
            _apply_enrichment_if_available,
        )

        enrichment_result = _make_enrichment_result(applied=False)  # SKIPPED
        mock_store = MagicMock()
        mock_store.get_json.return_value = enrichment_result.to_dict()

        units_raw = [{"unit_id": "u1", "unit_type": "unknown"}]
        result = await _apply_enrichment_if_available(
            units_raw=units_raw,
            snapshot_dict=_make_snapshot().to_dict(),
            enrichment_ref="s3://bucket/enrichment.json",
            artifact_store=mock_store,
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            segment_id="seg1",
            logger=MagicMock(),
        )
        assert result is units_raw

    @pytest.mark.asyncio
    async def test_invalid_enrichment_dict_returns_baseline(self):
        from engine.content._document_content_semantic import (
            _apply_enrichment_if_available,
        )

        mock_store = MagicMock()
        mock_store.get_json.return_value = "not_a_dict"  # невалидный формат

        units_raw = [{"unit_id": "u1", "unit_type": "unknown"}]
        result = await _apply_enrichment_if_available(
            units_raw=units_raw,
            snapshot_dict={},
            enrichment_ref="s3://bucket/enrichment.json",
            artifact_store=mock_store,
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            segment_id="seg1",
            logger=MagicMock(),
        )
        assert result is units_raw


# ---------------------------------------------------------------------------
# 8–10. load_legal_units_from_segments integration
# ---------------------------------------------------------------------------

class TestLoadLegalUnitsFromSegmentsEnrichment:
    """
    Integration-level тесты для load_legal_units_from_segments().
    Мокаем artifact_store и segment objects.
    """

    def _make_segment(
        self,
        segment_id: str = "seg1",
        is_primary: bool = True,
        legal_units_ref: str | None = "s3://bucket/legal_units.json",
        legal_units_enrichment_ref: str | None = None,
    ) -> MagicMock:
        seg = MagicMock()
        seg.segment_id = segment_id
        seg.is_primary = is_primary
        meta: dict = {}
        if legal_units_ref:
            meta["legal_units_ref"] = legal_units_ref
        if legal_units_enrichment_ref:
            meta["legal_units_enrichment_ref"] = legal_units_enrichment_ref
        seg.segment_meta = meta
        return seg

    @pytest.mark.asyncio
    async def test_baseline_path_no_enrichment_ref(self):
        """Нет enrichment_ref — возвращает baseline units."""
        from engine.content._document_content_semantic import (
            load_legal_units_from_segments,
        )

        unit = _make_legal_unit("u1")
        snapshot = _make_snapshot([unit])

        mock_store = MagicMock()
        mock_store.get_json.return_value = snapshot.to_dict()

        segment = self._make_segment(
            legal_units_ref="s3://bucket/legal_units.json",
            legal_units_enrichment_ref=None,
        )

        result = await load_legal_units_from_segments(
            segments=[segment],
            artifact_store=mock_store,
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            primary_only=True,
            logger=MagicMock(),
        )

        assert len(result) == 1
        assert result[0]["unit_id"] == "u1"
        assert result[0]["unit_type"] == "unknown"  # не enriched

    @pytest.mark.asyncio
    async def test_enrichment_path_applies_projection(self):
        """Есть enrichment_ref — возвращает enriched units."""
        from engine.content._document_content_semantic import (
            load_legal_units_from_segments,
        )

        unit = _make_legal_unit("u1", LegalUnitType.UNKNOWN)
        snapshot = _make_snapshot([unit])
        enrichment_result = _make_enrichment_result(applied=True, unit_id="u1")

        call_count = 0
        def _get_json(ref: str) -> dict:
            nonlocal call_count
            call_count += 1
            if "enrichment" in ref:
                return enrichment_result.to_dict()
            return snapshot.to_dict()

        mock_store = MagicMock()
        mock_store.get_json.side_effect = _get_json

        segment = self._make_segment(
            legal_units_ref="s3://bucket/legal_units.json",
            legal_units_enrichment_ref="s3://bucket/legal_units_enrichment.json",
        )

        result = await load_legal_units_from_segments(
            segments=[segment],
            artifact_store=mock_store,
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            primary_only=True,
            logger=MagicMock(),
        )

        assert len(result) == 1
        assert result[0]["unit_type"] == "payment_term"
        assert "payment" in result[0]["topic_tags"]

    @pytest.mark.asyncio
    async def test_enrichment_failure_returns_baseline(self):
        """Ошибка загрузки enrichment → baseline без изменений."""
        from engine.content._document_content_semantic import (
            load_legal_units_from_segments,
        )

        unit = _make_legal_unit("u1", LegalUnitType.UNKNOWN)
        snapshot = _make_snapshot([unit])

        def _get_json(ref: str) -> dict:
            if "enrichment" in ref:
                raise Exception("sidecar not found")
            return snapshot.to_dict()

        mock_store = MagicMock()
        mock_store.get_json.side_effect = _get_json

        segment = self._make_segment(
            legal_units_ref="s3://bucket/legal_units.json",
            legal_units_enrichment_ref="s3://bucket/missing_enrichment.json",
        )

        result = await load_legal_units_from_segments(
            segments=[segment],
            artifact_store=mock_store,
            doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            primary_only=True,
            logger=MagicMock(),
        )

        assert len(result) == 1
        assert result[0]["unit_type"] == "unknown"  # baseline



