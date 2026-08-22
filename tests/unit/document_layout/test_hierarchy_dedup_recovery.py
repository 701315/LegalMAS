"""Unit-тесты для верификации TOC-aware дедупликации в иерархии."""

from __future__ import annotations

from services.structure.heading_llm_refiner import ScoredHeadingCandidate
from services.structure._heading_builder._ranking import _select_best_candidates_by_uid
from services.structure._heading_builder._core import filter_heading_sequence, HeadingCandidate


def test_toc_and_body_candidates_are_both_preserved_during_ranking():
    """Тест проверяет, что заголовок из Body не уничтожается аналогичным из TOC."""
    toc_candidate = ScoredHeadingCandidate(
        elem_i=15,
        page=1,
        raw_text="1.1. Scope of Work",
        uid="1.1",
        title="Scope of Work",
        decision="accepted",
        reason="rules",
        score=0.95,
        scope="main_contract",
        metadata={
            "raw_uid": "1.1",
            "possible_toc": True,
            "strong_toc_confirmation": True,
            "_preamble_zone": "in_toc",
        },
    )

    body_candidate = ScoredHeadingCandidate(
        elem_i=120,
        page=3,
        raw_text="1.1. Scope of Work",
        uid="1.1",
        title="Scope of Work",
        decision="accepted",
        reason="rules",
        score=0.85,
        scope="main_contract",
        metadata={
            "raw_uid": "1.1",
            "possible_toc": False,
            "strong_toc_confirmation": False,
            "_preamble_zone": "post_toc",
        },
    )

    candidates = [toc_candidate, body_candidate]
    result = _select_best_candidates_by_uid(candidates, "test-doc")

    # ОБА кандидата должны успешно выжить
    assert len(result) == 2
    elem_ids = {c.elem_i for c in result}
    assert 15 in elem_ids
    assert 120 in elem_ids


def test_filter_heading_sequence_preserves_both_toc_and_body():
    """Тест проверяет финальную дедупликацию последовательности."""
    cand_toc = HeadingCandidate(
        elem_i=15,
        uid="1.1",
        title="Definitions",
        page=1,
        scope="main_contract",
        raw_uid="1.1",
        toc_entry=True,
        metadata={"_preamble_zone": "in_toc"}
    )
    
    cand_body = HeadingCandidate(
        elem_i=120,
        uid="1.1",
        title="Definitions",
        page=3,
        scope="main_contract",
        raw_uid="1.1",
        toc_entry=False,
        metadata={"_preamble_zone": "post_toc"}
    )

    result = filter_heading_sequence([cand_toc, cand_body], document_id="test-doc")
    assert len(result) == 2



    