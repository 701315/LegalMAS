# tests/services/structure/models/test_recovery.py

"""Tests for Phase 4 — Recovery Engine contracts."""

from __future__ import annotations

import pytest

from services.structure.models import (
    CandidateWindow,
    DEFAULT_CANDIDATE_WINDOW,
    RecoveryCandidate,
    RecoveryDecision,
    RecoveryReport,
    RecoveryStrategyType,
    TieBreakPolicy,
)


class TestRecoveryStrategyType:
    def test_all_values_exist(self):
        values = {s.value for s in RecoveryStrategyType}
        assert "numbering_inference" in values
        assert "grammar_compatibility" in values
        assert "layout_similarity" in values
        assert "embeddings" in values
        assert "best_effort_root" in values
        assert "unrecovered" in values

    def test_embeddings_exists_but_not_wave1(self):
        # Strategy 4 существует как тип но НЕ активна в Wave 1
        assert RecoveryStrategyType.EMBEDDINGS == "embeddings"


class TestTieBreakPolicy:
    def test_rank_returns_tuple(self):
        policy = TieBreakPolicy()
        key = policy.rank(page_distance=1, level_delta=1, elem_i=5, uid="1.1")
        assert key == (1, 1, 5, "1.1")

    def test_smaller_page_distance_wins(self):
        policy = TieBreakPolicy()
        k1 = policy.rank(page_distance=1, level_delta=0, elem_i=0, uid="1")
        k2 = policy.rank(page_distance=2, level_delta=0, elem_i=0, uid="1")
        assert k1 < k2

    def test_smaller_level_delta_wins_on_tie(self):
        policy = TieBreakPolicy()
        k1 = policy.rank(page_distance=1, level_delta=0, elem_i=0, uid="1")
        k2 = policy.rank(page_distance=1, level_delta=1, elem_i=0, uid="1")
        assert k1 < k2

    def test_earlier_appearance_wins_on_tie(self):
        policy = TieBreakPolicy()
        k1 = policy.rank(page_distance=1, level_delta=0, elem_i=3, uid="1")
        k2 = policy.rank(page_distance=1, level_delta=0, elem_i=5, uid="1")
        assert k1 < k2

    def test_lexical_uid_wins_on_full_tie(self):
        policy = TieBreakPolicy()
        k1 = policy.rank(page_distance=1, level_delta=0, elem_i=3, uid="1")
        k2 = policy.rank(page_distance=1, level_delta=0, elem_i=3, uid="2")
        assert k1 < k2


class TestCandidateWindow:
    def test_basic_creation(self):
        w = CandidateWindow(max_page_distance=3, max_level_delta=2)
        assert w.max_page_distance == 3
        assert w.max_level_delta == 2
        assert w.compatible_token_types is None

    def test_negative_page_distance_raises(self):
        with pytest.raises(ValueError, match="max_page_distance"):
            CandidateWindow(max_page_distance=-1, max_level_delta=2)

    def test_negative_level_delta_raises(self):
        with pytest.raises(ValueError, match="max_level_delta"):
            CandidateWindow(max_page_distance=3, max_level_delta=-1)

    def test_allows_within_bounds(self):
        w = CandidateWindow(max_page_distance=3, max_level_delta=2)
        assert w.allows(page_distance=2, level_delta=1) is True

    def test_allows_at_exact_bounds(self):
        w = CandidateWindow(max_page_distance=3, max_level_delta=2)
        assert w.allows(page_distance=3, level_delta=2) is True

    def test_rejects_exceeds_page_distance(self):
        w = CandidateWindow(max_page_distance=3, max_level_delta=2)
        assert w.allows(page_distance=4, level_delta=1) is False

    def test_rejects_exceeds_level_delta(self):
        w = CandidateWindow(max_page_distance=3, max_level_delta=2)
        assert w.allows(page_distance=1, level_delta=3) is False

    def test_compatible_token_types_filter(self):
        w = CandidateWindow(
            max_page_distance=3,
            max_level_delta=2,
            compatible_token_types=["numeric"],
        )
        assert w.allows(page_distance=1, level_delta=1, token_type="numeric") is True
        assert w.allows(page_distance=1, level_delta=1, token_type="roman") is False

    def test_compatible_token_types_none_allows_any(self):
        w = CandidateWindow(max_page_distance=3, max_level_delta=2)
        assert w.allows(page_distance=1, level_delta=1, token_type="roman") is True

    def test_default_window(self):
        assert DEFAULT_CANDIDATE_WINDOW.max_page_distance == 3
        assert DEFAULT_CANDIDATE_WINDOW.max_level_delta == 2

    def test_to_dict(self):
        w = CandidateWindow(max_page_distance=3, max_level_delta=2)
        d = w.to_dict()
        assert d["max_page_distance"] == 3
        assert d["max_level_delta"] == 2


class TestRecoveryCandidate:
    def _make(self, **kwargs) -> RecoveryCandidate:
        defaults = dict(
            parent_uid="main_contract:7",
            strategy=RecoveryStrategyType.NUMBERING_INFERENCE,
            confidence=0.9,
            page_distance=0,
            level_delta=1,
            elem_i=10,
        )
        defaults.update(kwargs)
        return RecoveryCandidate(**defaults)

    def test_basic_creation(self):
        c = self._make()
        assert c.parent_uid == "main_contract:7"
        assert c.strategy == RecoveryStrategyType.NUMBERING_INFERENCE
        assert c.confidence == 0.9

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            self._make(confidence=1.5)

    def test_negative_page_distance_raises(self):
        with pytest.raises(ValueError, match="page_distance"):
            self._make(page_distance=-1)

    def test_tiebreak_key(self):
        c = self._make(page_distance=1, level_delta=1, elem_i=5, parent_uid="1")
        policy = TieBreakPolicy()
        assert c.tiebreak_key(policy) == (1, 1, 5, "1")

    def test_to_dict(self):
        c = self._make()
        d = c.to_dict()
        assert d["strategy"] == "numbering_inference"
        assert d["confidence"] == 0.9


class TestRecoveryDecision:
    def _make_candidate(self) -> RecoveryCandidate:
        return RecoveryCandidate(
            parent_uid="main_contract:7",
            strategy=RecoveryStrategyType.NUMBERING_INFERENCE,
            confidence=0.9,
            page_distance=0,
            level_delta=1,
            elem_i=10,
        )

    def test_recovered(self):
        c = self._make_candidate()
        d = RecoveryDecision(
            recovered=True,
            orphan_uid="main_contract:7.1",
            strategy_used=RecoveryStrategyType.NUMBERING_INFERENCE,
            chosen_parent=c,
        )
        assert d.recovered is True
        assert d.parent_uid == "main_contract:7"
        assert d.recovery_confidence == 0.9

    def test_unrecovered(self):
        d = RecoveryDecision(
            recovered=False,
            orphan_uid="main_contract:7.1",
            strategy_used=RecoveryStrategyType.UNRECOVERED,
        )
        assert d.recovered is False
        assert d.parent_uid is None
        assert d.recovery_confidence == 0.0

    def test_to_dict(self):
        d = RecoveryDecision(
            recovered=False,
            orphan_uid="main_contract:7.1",
            strategy_used=RecoveryStrategyType.UNRECOVERED,
        )
        result = d.to_dict()
        assert result["recovered"] is False
        assert result["parent_uid"] is None
        assert result["strategy_used"] == "unrecovered"


class TestRecoveryReport:
    def _make_decision(self, recovered: bool, uid: str) -> RecoveryDecision:
        if recovered:
            c = RecoveryCandidate(
                parent_uid="main_contract:7",
                strategy=RecoveryStrategyType.NUMBERING_INFERENCE,
                confidence=0.85,
                page_distance=0,
                level_delta=1,
                elem_i=5,
            )
        else:
            c = None
        return RecoveryDecision(
            recovered=recovered,
            orphan_uid=uid,
            strategy_used=(
                RecoveryStrategyType.NUMBERING_INFERENCE
                if recovered
                else RecoveryStrategyType.UNRECOVERED
            ),
            chosen_parent=c,
        )

    def test_empty_report(self):
        r = RecoveryReport(document_id="doc_001")
        assert r.total_orphans == 0
        assert r.orphan_ratio == 0.0
        assert r.recovery_rate == 1.0

    def test_all_recovered(self):
        r = RecoveryReport(document_id="doc_001")
        r.add(self._make_decision(True, "main_contract:7.1"))
        r.add(self._make_decision(True, "main_contract:8.1"))
        assert r.recovery_rate == 1.0
        assert r.orphan_ratio == 0.0

    def test_partial_recovery(self):
        r = RecoveryReport(document_id="doc_001")
        r.add(self._make_decision(True, "main_contract:7.1"))
        r.add(self._make_decision(False, "main_contract:8.1"))
        assert r.recovered_count == 1
        assert r.unrecovered_count == 1
        assert r.orphan_ratio == 0.5

    def test_orphan_ratio_warning_threshold(self):
        """Quality gate: warning если orphan_ratio > 0.1 (Phase 9)."""
        r = RecoveryReport(document_id="doc_001")
        for i in range(9):
            r.add(self._make_decision(True, f"main_contract:{i}.1"))
        r.add(self._make_decision(False, "main_contract:99.1"))
        # 1 unrecovered из 10 = 0.1 — на границе
        assert r.orphan_ratio == 0.1

    def test_by_strategy(self):
        r = RecoveryReport(document_id="doc_001")
        r.add(self._make_decision(True, "main_contract:7.1"))
        r.add(self._make_decision(False, "main_contract:8.1"))
        assert len(r.by_strategy(RecoveryStrategyType.NUMBERING_INFERENCE)) == 1
        assert len(r.by_strategy(RecoveryStrategyType.UNRECOVERED)) == 1

    def test_deterministic(self):
        """Recovery report детерминирован."""
        r1 = RecoveryReport(document_id="doc_001")
        r1.add(self._make_decision(True, "main_contract:7.1"))
        r2 = RecoveryReport(document_id="doc_001")
        r2.add(self._make_decision(True, "main_contract:7.1"))
        assert r1.to_dict() == r2.to_dict()


        