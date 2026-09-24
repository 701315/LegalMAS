"""
tests/services/structure/test_phase13_5_heading_confidence_calibration.py

Phase 13.5 — Heading Confidence Calibration tests.

Покрытие:
- strong TOC confirmation thresholds в scorer и builder
- builder score/decision alignment after post-adjustments
- recoverable TOC candidates use calibrated strong_toc signal
- EvidenceAssessmentInput.avg_accepted_heading_score normalization
- _extract_evidence_metrics() reads canonical heading_candidates
- _extract_evidence_metrics() computes avg accepted heading score correctly
- _calculate_heading_quality_score() blends structural heuristic with real scores
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import services.structure._heading_builder._core as heading_builder_core
from services.structure._heading_builder._core import (
    _has_strong_toc_confirmation as builder_has_strong_toc_confirmation,
)
from services.structure._heading_scoring._core import (
    _has_strong_toc_confirmation as scorer_has_strong_toc_confirmation,
)
from services.structure._heading_scoring._types import (
    CandidateStatus,
    HeadingScoreResult,
)
from services.structure._pipeline._quality_metrics import (
    EvidenceAssessmentInput,
    HierarchyAssessmentInput,
    _calculate_heading_quality_score,
    _extract_evidence_metrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_element(
    *,
    text: str,
    element_type: str,
    page: int = 1,
    metadata: dict | None = None,
) -> dict:
    return {
        "element_id": "el-1",
        "id": "el-1",
        "text": text,
        "element_type": element_type,
        "page": page,
        "metadata": metadata or {},
    }


def _run_collect_single_candidate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    element_type: str,
    parsed_uid: str,
    parsed_title: str,
    score_result: HeadingScoreResult,
    strong: bool = False,
    weak: bool = False,
    recoverable_toc: bool = False,
    metadata: dict | None = None,
) -> list:
    """
    Изолированный запуск collect_scored_heading_candidates() на одном элементе.

    Мы патчим внешний parsing/scoring, чтобы тестировать именно
    builder-level post-adjustments + calibration, а не весь Phase 2 pipeline.
    """
    monkeypatch.setattr(
        heading_builder_core,
        "_require_element_structure_contract",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        heading_builder_core,
        "_is_candidate_element_type_allowed",
        lambda element_type_value: True,
    )
    monkeypatch.setattr(
        heading_builder_core,
        "_is_strong_structural_element_type",
        lambda element_type_value: strong,
    )
    monkeypatch.setattr(
        heading_builder_core,
        "_is_weak_structural_element_type",
        lambda element_type_value: weak,
    )
    monkeypatch.setattr(
        heading_builder_core,
        "_is_recoverable_toc_like_element_type",
        lambda element_type_value: recoverable_toc,
    )
    monkeypatch.setattr(
        heading_builder_core,
        "_element_scope",
        lambda element: "main",
    )
    monkeypatch.setattr(
        heading_builder_core,
        "parse_raw_heading",
        lambda raw_text: (parsed_uid, parsed_title),
    )
    monkeypatch.setattr(
        heading_builder_core,
        "toc_match_payload",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        heading_builder_core,
        "score_heading_candidate",
        lambda **kwargs: score_result,
    )
    monkeypatch.setattr(
        heading_builder_core,
        "_select_best_candidates_by_uid",
        lambda candidates, document_id: candidates,
    )

    elements = [
        _make_element(
            text=f"{parsed_uid} {parsed_title}",
            element_type=element_type,
            metadata=metadata,
        )
    ]
    return heading_builder_core.collect_scored_heading_candidates(
        elements,
        document_id="doc-1",
    )


def _make_global_signals(**overrides):
    base = {
        "toc_detected": False,
        "toc_confidence": 0.0,
        "main_section_chain_length": 0,
        "appendix_chain_length": 0,
        "crossref_anchor_count": 0,
        "document_quality_signals": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_stats(**overrides):
    base = {
        "candidate_count": 0,
        "numeric_heading_count": 0,
        "roman_heading_count": 0,
        "alpha_heading_count": 0,
        "max_depth_observed": 0,
        "scope_count": 0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_evidence_candidate(
    *,
    score: float,
    decision: str | None = None,
    is_toc_entry: bool = False,
):
    features = {}
    if decision is not None:
        features["decision"] = decision
    return SimpleNamespace(
        score=score,
        is_toc_entry=is_toc_entry,
        features=features,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOC strong confirmation thresholds
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("checker", "label"),
    [
        (scorer_has_strong_toc_confirmation, "scorer"),
        (builder_has_strong_toc_confirmation, "builder"),
    ],
)
def test_strong_toc_confirmation_exact_is_strong(checker, label):
    assert checker("exact", 0.01) is True, label


@pytest.mark.parametrize(
    ("checker", "label"),
    [
        (scorer_has_strong_toc_confirmation, "scorer"),
        (builder_has_strong_toc_confirmation, "builder"),
    ],
)
def test_strong_toc_confirmation_fuzzy_bonus_003_is_strong(checker, label):
    assert checker("fuzzy", 0.03) is True, label


@pytest.mark.parametrize(
    ("checker", "label"),
    [
        (scorer_has_strong_toc_confirmation, "scorer"),
        (builder_has_strong_toc_confirmation, "builder"),
    ],
)
def test_strong_toc_confirmation_fuzzy_bonus_004_is_strong(checker, label):
    assert checker("fuzzy", 0.04) is True, label


@pytest.mark.parametrize(
    ("checker", "label"),
    [
        (scorer_has_strong_toc_confirmation, "scorer"),
        (builder_has_strong_toc_confirmation, "builder"),
    ],
)
def test_strong_toc_confirmation_fuzzy_bonus_002_not_strong(checker, label):
    assert checker("fuzzy", 0.02) is False, label


# ─────────────────────────────────────────────────────────────────────────────
# Builder score/decision alignment
# ─────────────────────────────────────────────────────────────────────────────


def test_builder_promoted_accepted_score_gets_floor_065(monkeypatch: pytest.MonkeyPatch):
    """
    Strong structural element type может повысить ambiguous -> accepted.
    После Phase 13.5 score должен быть откалиброван до минимального accepted floor.
    """
    score_result = HeadingScoreResult(
        status=CandidateStatus.AMBIGUOUS,
        score=0.55,
        primary_reason="needs_confirmation",
    )

    scored = _run_collect_single_candidate(
        monkeypatch,
        element_type="section_heading",
        parsed_uid="1",
        parsed_title="General Provisions",
        score_result=score_result,
        strong=True,
    )

    assert len(scored) == 1
    candidate = scored[0]
    assert candidate.decision == "accepted"
    assert candidate.reason == "strong_structural_element_type"
    assert candidate.score == pytest.approx(0.65, abs=0.001)


def test_builder_demoted_ambiguous_score_gets_cap_084(monkeypatch: pytest.MonkeyPatch):
    """
    definition_item при accepted решении builder предпочитает трактовать как ambiguous.
    Высокий score должен быть capped, чтобы не выглядеть как уверенный accepted.
    """
    score_result = HeadingScoreResult(
        status=CandidateStatus.ACCEPTED,
        score=0.90,
        primary_reason="accepted",
    )

    scored = _run_collect_single_candidate(
        monkeypatch,
        element_type="definition_item",
        parsed_uid="1",
        parsed_title="Term",
        score_result=score_result,
    )

    assert len(scored) == 1
    candidate = scored[0]
    assert candidate.decision == "ambiguous"
    assert candidate.reason == "definition_item_prefer_non_section_interpretation"
    assert candidate.score == pytest.approx(0.84, abs=0.001)


def test_builder_demoted_rejected_score_gets_cap_049(monkeypatch: pytest.MonkeyPatch):
    """
    list_item с non-numeric UID принудительно reject-ится builder'ом.
    Score должен быть capped ниже 0.50.
    """
    score_result = HeadingScoreResult(
        status=CandidateStatus.ACCEPTED,
        score=0.90,
        primary_reason="accepted",
    )

    scored = _run_collect_single_candidate(
        monkeypatch,
        element_type="list_item",
        parsed_uid="INVALID?",
        parsed_title="Not a numeric heading",
        score_result=score_result,
    )

    assert len(scored) == 1
    candidate = scored[0]
    assert candidate.decision == "rejected"
    assert candidate.reason == "list_item_non_numeric_uid"
    assert candidate.score == pytest.approx(0.49, abs=0.001)


def test_recoverable_toc_candidate_with_strong_fuzzy_confirmation_stays_accepted(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Phase 13.5: recoverable TOC candidate должен использовать strong_toc,
    где fuzzy bonus=0.03 уже считается strong.

    До фикса builder использовал свой порог 0.045 и такой кандидат
    понижался бы в ambiguous.
    """
    score_result = HeadingScoreResult(
        status=CandidateStatus.ACCEPTED,
        score=0.84,
        primary_reason="accepted",
        toc_match_score=0.03,
        toc_match_type="fuzzy",
    )

    scored = _run_collect_single_candidate(
        monkeypatch,
        element_type="toc_false_positive",
        parsed_uid="1",
        parsed_title="Recovered Heading",
        score_result=score_result,
        recoverable_toc=True,
    )

    assert len(scored) == 1
    candidate = scored[0]
    assert candidate.decision == "accepted"
    assert candidate.score == pytest.approx(0.84, abs=0.001)


def test_recoverable_toc_candidate_with_weak_fuzzy_confirmation_becomes_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    fuzzy bonus=0.02 остаётся недостаточным для strong confirmation,
    поэтому accepted кандидат с низким score должен быть понижен в ambiguous.
    """
    score_result = HeadingScoreResult(
        status=CandidateStatus.ACCEPTED,
        score=0.84,
        primary_reason="accepted",
        toc_match_score=0.02,
        toc_match_type="fuzzy",
    )

    scored = _run_collect_single_candidate(
        monkeypatch,
        element_type="toc_false_positive",
        parsed_uid="1",
        parsed_title="Recovered Heading",
        score_result=score_result,
        recoverable_toc=True,
    )

    assert len(scored) == 1
    candidate = scored[0]
    assert candidate.decision == "ambiguous"
    assert candidate.reason == "recoverable_toc_like_requires_stronger_evidence"
    assert candidate.score == pytest.approx(0.84, abs=0.001)


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceAssessmentInput normalization
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (1.7, 1.0),
        (-0.2, 0.0),
        (0.73, 0.73),
    ],
)
def test_evidence_assessment_input_clamps_avg_accepted_heading_score(raw_value, expected):
    evidence = EvidenceAssessmentInput(avg_accepted_heading_score=raw_value)
    assert evidence.avg_accepted_heading_score == pytest.approx(expected, abs=0.0001)


# ─────────────────────────────────────────────────────────────────────────────
# _extract_evidence_metrics
# ─────────────────────────────────────────────────────────────────────────────


def test_extract_evidence_metrics_prefers_heading_candidates_over_legacy_candidates():
    """
    Canonical StructureEvidenceBundle хранит кандидатов в heading_candidates.
    Если одновременно присутствуют legacy candidates, должен использоваться
    именно canonical список.
    """
    structure_evidence = SimpleNamespace(
        global_signals=_make_global_signals(),
        stats=_make_stats(candidate_count=0, scope_count=0),
        scope_boundaries=[],
        heading_candidates=[
            _make_evidence_candidate(score=0.80, decision="accepted"),
        ],
        candidates=[
            _make_evidence_candidate(score=0.10, decision="accepted"),
        ],
        appendix_markers=[],
    )

    result = _extract_evidence_metrics(structure_evidence)

    assert result.candidate_count == 1
    assert result.avg_accepted_heading_score == pytest.approx(0.80, abs=0.0001)


def test_extract_evidence_metrics_computes_avg_accepted_heading_score():
    structure_evidence = SimpleNamespace(
        global_signals=_make_global_signals(
            toc_detected=True,
            toc_confidence=0.9,
            main_section_chain_length=5,
            crossref_anchor_count=2,
        ),
        stats=_make_stats(candidate_count=0, scope_count=0),
        scope_boundaries=[],
        heading_candidates=[
            _make_evidence_candidate(score=0.80, decision="accepted"),
            _make_evidence_candidate(score=0.60, decision="accepted"),
            _make_evidence_candidate(score=0.95, decision="ambiguous"),
            _make_evidence_candidate(score=0.20, decision="rejected"),
        ],
        appendix_markers=[],
    )

    result = _extract_evidence_metrics(structure_evidence)

    assert result.present is True
    assert result.toc_detected is True
    assert result.toc_confidence == pytest.approx(0.9, abs=0.0001)
    assert result.avg_accepted_heading_score == pytest.approx(0.70, abs=0.0001)


def test_extract_evidence_metrics_excludes_toc_entries_from_avg_score():
    structure_evidence = SimpleNamespace(
        global_signals=_make_global_signals(),
        stats=_make_stats(candidate_count=0, scope_count=0),
        scope_boundaries=[],
        heading_candidates=[
            _make_evidence_candidate(score=0.95, decision="accepted", is_toc_entry=True),
            _make_evidence_candidate(score=0.70, decision="accepted", is_toc_entry=False),
        ],
        appendix_markers=[],
    )

    result = _extract_evidence_metrics(structure_evidence)

    assert result.avg_accepted_heading_score == pytest.approx(0.70, abs=0.0001)


def test_extract_evidence_metrics_legacy_candidates_without_decision_still_supported():
    """
    Backward compatibility:
    legacy candidate shape может не содержать features["decision"].
    Тогда score должен быть использован как fallback.
    """
    structure_evidence = SimpleNamespace(
        global_signals=_make_global_signals(),
        stats=_make_stats(candidate_count=0, scope_count=0),
        scope_boundaries=[],
        candidates=[
            _make_evidence_candidate(score=0.70, decision=None, is_toc_entry=False),
        ],
        appendix_markers=[],
    )

    result = _extract_evidence_metrics(structure_evidence)

    assert result.candidate_count == 1
    assert result.avg_accepted_heading_score == pytest.approx(0.70, abs=0.0001)


# ─────────────────────────────────────────────────────────────────────────────
# _calculate_heading_quality_score
# ─────────────────────────────────────────────────────────────────────────────


def test_heading_quality_score_blends_structural_and_real_scores():
    hierarchy = HierarchyAssessmentInput(
        headings_count=8,
        numeric_ratio=0.60,
        empty_title_count=0,
    )
    evidence = EvidenceAssessmentInput(
        toc_detected=True,
        toc_confidence=0.60,
        avg_accepted_heading_score=0.50,
    )

    reasons: list[str] = []
    result = _calculate_heading_quality_score(hierarchy, evidence, reasons)

    # structural_score = 1.05
    # blended score = clamp(0.75*1.05 + 0.25*0.50) = 0.9125
    # structural_confidence = 0.88
    # blended avg_conf = 0.60*0.88 + 0.40*0.50 = 0.728
    assert result.score == pytest.approx(0.9125, abs=0.0001)
    assert result.avg_heading_confidence == pytest.approx(0.7280, abs=0.0001)
    assert result.toc_validated is True
    assert result.low_confidence_ratio == pytest.approx(0.0, abs=0.0001)


def test_heading_quality_score_falls_back_to_structural_when_no_real_scores():
    hierarchy = HierarchyAssessmentInput(
        headings_count=8,
        numeric_ratio=0.60,
        empty_title_count=0,
    )
    evidence = EvidenceAssessmentInput(
        toc_detected=True,
        toc_confidence=0.60,
        avg_accepted_heading_score=0.0,
    )

    reasons: list[str] = []
    result = _calculate_heading_quality_score(hierarchy, evidence, reasons)

    # structural_score = clamp(1.05) = 1.0
    # structural_confidence = 0.88
    assert result.score == pytest.approx(1.0, abs=0.0001)
    assert result.avg_heading_confidence == pytest.approx(0.88, abs=0.0001)
    assert result.toc_validated is True
    assert result.low_confidence_ratio == pytest.approx(0.0, abs=0.0001)


@pytest.mark.parametrize("uid", ["A", "IV"])
@pytest.mark.parametrize(
    "status, score, expected",
    [
        (CandidateStatus.ACCEPTED, 0.90, "accepted"),
        (CandidateStatus.AMBIGUOUS, 0.40, "ambiguous"),
        (CandidateStatus.REJECTED, 0.20, "rejected"),
    ],
)
def test_non_numeric_structural_uid_respects_scorer_decision(
    monkeypatch: pytest.MonkeyPatch,
    uid: str,
    status: CandidateStatus,
    score: float,
    expected: str,
):
    result = HeadingScoreResult(
        status=status,
        score=score,
        primary_reason="calibrated_scorer",
    )
    scored = _run_collect_single_candidate(
        monkeypatch,
        element_type="list_item",
        parsed_uid=uid,
        parsed_title="Synthetic heading",
        score_result=result,
    )

    assert len(scored) == 1
    candidate = scored[0]
    assert candidate.decision == expected
    if expected == "accepted":
        assert candidate.reason == "list_item_structural_heading"
    else:
        assert candidate.score < 0.65

