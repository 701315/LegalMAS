from __future__ import annotations

from services.structure.heading_llm_refiner import ScoredHeadingCandidate
from services.structure._heading_builder._bilingual import annotate_bilingual_heading_pairs
from services.structure._heading_builder._ranking import (
    _candidate_priority_tuple,
    _select_best_candidates_by_uid,
)


def make_candidate(
    *,
    uid: str,
    title: str,
    raw_text: str | None = None,
    score: float = 0.80,
    decision: str = "accepted",
    scope: str = "main_contract",
    page: int = 1,
    elem_i: int = 0,
    element_type: str = "heading_candidate",
    toc_match_type: str | None = None,
    toc_match_score: float = 0.0,
):
    return ScoredHeadingCandidate(
        elem_i=elem_i,
        page=page,
        raw_text=raw_text or f"{uid} {title}",
        uid=uid,
        title=title,
        decision=decision,
        reason="accepted",
        score=score,
        decision_source="rules",
        scope=scope,
        metadata={
            "element_id": f"el-{elem_i}",
            "raw_uid": uid,
            "effective_uid": f"{scope}::{uid}",
            "normalized_title": title,
            "element_type": element_type,
            "toc_match_type": toc_match_type,
            "toc_match_score": toc_match_score,
        },
    )


def test_annotate_bilingual_heading_pairs_marks_translation_pair():
    left = make_candidate(
        uid="1",
        title="DEFINITIONS",
        raw_text="1. DEFINITIONS",
        page=1,
        elem_i=10,
    )
    right = make_candidate(
        uid="1",
        title="ОПРЕДЕЛЕНИЯ",
        raw_text="1 ОПРЕДЕЛЕНИЯ",
        page=1,
        elem_i=11,
    )

    annotated = annotate_bilingual_heading_pairs([left, right])

    assert annotated[0].metadata["bilingual_heading_pair"] is True
    assert annotated[0].metadata["bilingual_pair_role"] == "primary"

    assert annotated[1].metadata["bilingual_heading_pair"] is True
    assert annotated[1].metadata["bilingual_pair_role"] == "translation"
    assert annotated[1].metadata["heading_translation_of"] == "el-10"


def test_annotate_bilingual_heading_pairs_skips_same_script_duplicates():
    left = make_candidate(
        uid="1",
        title="DEFINITIONS",
        raw_text="1. DEFINITIONS",
        page=1,
        elem_i=10,
    )
    right = make_candidate(
        uid="1",
        title="INTERPRETATION",
        raw_text="1. INTERPRETATION",
        page=1,
        elem_i=11,
    )

    annotated = annotate_bilingual_heading_pairs([left, right])

    assert "bilingual_pair_role" not in annotated[0].metadata
    assert "bilingual_pair_role" not in annotated[1].metadata


def test_annotate_bilingual_heading_pairs_skips_distant_duplicates():
    left = make_candidate(
        uid="2",
        title="TERM",
        raw_text="2. TERM",
        page=1,
        elem_i=10,
    )
    right = make_candidate(
        uid="2",
        title="СРОК",
        raw_text="2 СРОК",
        page=1,
        elem_i=20,
    )

    annotated = annotate_bilingual_heading_pairs([left, right])

    assert "bilingual_pair_role" not in annotated[0].metadata
    assert "bilingual_pair_role" not in annotated[1].metadata


def test_select_best_candidates_by_uid_prefers_primary_over_translation():
    left = make_candidate(
        uid="3",
        title="PAYMENT TERMS",
        raw_text="3. PAYMENT TERMS",
        score=0.72,
        page=1,
        elem_i=10,
    )
    right = make_candidate(
        uid="3",
        title="УСЛОВИЯ ОПЛАТЫ",
        raw_text="3 УСЛОВИЯ ОПЛАТЫ",
        score=0.96,
        page=1,
        elem_i=11,
    )

    annotated = annotate_bilingual_heading_pairs([left, right])
    selected = _select_best_candidates_by_uid(annotated, document_id="doc-1")

    assert len(selected) == 1
    assert selected[0].elem_i == 10
    assert selected[0].metadata.get("bilingual_pair_role") == "primary"


def test_candidate_priority_tuple_keeps_status_above_bilingual_priority():
    primary_ambiguous = make_candidate(
        uid="4",
        title="LIABILITY",
        raw_text="4. LIABILITY",
        decision="ambiguous",
        score=0.99,
        page=1,
        elem_i=10,
    )
    translation_accepted = make_candidate(
        uid="4",
        title="ОТВЕТСТВЕННОСТЬ",
        raw_text="4 ОТВЕТСТВЕННОСТЬ",
        decision="accepted",
        score=0.70,
        page=1,
        elem_i=11,
    )

    annotated = annotate_bilingual_heading_pairs([primary_ambiguous, translation_accepted])

    primary = annotated[0]
    translation = annotated[1]

    # accepted должен всё ещё бить ambiguous,
    # даже если ambiguous помечен primary.
    assert _candidate_priority_tuple(translation) > _candidate_priority_tuple(primary)


    