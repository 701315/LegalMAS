from services.structure.heading_builder import _candidate_priority_tuple
from services.structure.heading_llm_refiner import ScoredHeadingCandidate


def make_candidate(
    *,
    uid: str,
    title: str,
    score: float,
    decision: str = "accepted",
    toc_match_type: str | None = None,
    toc_match_score: float = 0.0,
    element_type: str = "heading_candidate",
    elem_i: int = 0,
):
    return ScoredHeadingCandidate(
        elem_i=elem_i,
        page=1,
        raw_text=f"{uid} {title}",
        uid=uid,
        title=title,
        decision=decision,
        reason="accepted",
        score=score,
        decision_source="rules",
        scope="main_contract",
        metadata={
            "raw_uid": uid,
            "effective_uid": f"main_contract::{uid}",
            "element_type": element_type,
            "toc_match_type": toc_match_type,
            "toc_match_score": toc_match_score,
        },
    )


def test_candidate_priority_tuple_prefers_exact_toc_over_higher_score():
    exact_toc_candidate = make_candidate(
        uid="2.1",
        title="Definitions",
        score=0.88,
        toc_match_type="exact",
        toc_match_score=0.08,
        elem_i=10,
    )
    no_toc_candidate = make_candidate(
        uid="2.1",
        title="Definitions",
        score=0.95,
        toc_match_type=None,
        toc_match_score=0.0,
        elem_i=9,
    )

    assert _candidate_priority_tuple(exact_toc_candidate) > _candidate_priority_tuple(no_toc_candidate)


def test_candidate_priority_tuple_prefers_fuzzy_toc_over_no_toc():
    fuzzy_toc_candidate = make_candidate(
        uid="3",
        title="Representations",
        score=0.90,
        toc_match_type="fuzzy",
        toc_match_score=0.045,
        elem_i=10,
    )
    no_toc_candidate = make_candidate(
        uid="3",
        title="Representations",
        score=0.93,
        toc_match_type=None,
        toc_match_score=0.0,
        elem_i=8,
    )

    assert _candidate_priority_tuple(fuzzy_toc_candidate) > _candidate_priority_tuple(no_toc_candidate)


def test_candidate_priority_tuple_still_prefers_accepted_over_ambiguous():
    accepted_candidate = make_candidate(
        uid="4",
        title="Covenants",
        score=0.85,
        decision="accepted",
        toc_match_type=None,
        toc_match_score=0.0,
    )
    ambiguous_candidate = make_candidate(
        uid="4",
        title="Covenants",
        score=0.99,
        decision="ambiguous",
        toc_match_type="exact",
        toc_match_score=0.08,
    )

    assert _candidate_priority_tuple(accepted_candidate) > _candidate_priority_tuple(ambiguous_candidate)


    