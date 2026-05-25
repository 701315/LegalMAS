import pytest

from services.structure.heading_scoring import (
    CandidateStatus,
    score_heading_candidate,
)


def test_score_heading_candidate_accepts_plain_numeric_heading_without_toc():
    result = score_heading_candidate(
        uid="1",
        title="Definitions",
        raw_text="1. Definitions",
    )

    assert result.status == CandidateStatus.ACCEPTED
    assert result.score == 0.95
    assert result.toc_match_score == 0.0
    assert result.toc_match_type is None
    assert "top_level_numeric_heading" in result.accept_reasons


def test_score_heading_candidate_applies_exact_toc_bonus():
    result = score_heading_candidate(
        uid="1",
        title="Definitions",
        raw_text="1. Definitions",
        toc_match={
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 4,
            "toc_missing_in_body": False,
        },
    )

    assert result.status == CandidateStatus.ACCEPTED
    assert result.score == 1.0
    assert result.toc_match_score == 0.08
    assert result.toc_match_type == "exact"
    assert "toc_exact_match" in result.accept_reasons


@pytest.mark.parametrize(
    ("match_score", "expected_bonus", "expected_reason"),
    [
        (92.0, 0.06, "toc_fuzzy_match_strong"),
        (90.0, 0.045, "toc_fuzzy_match"),
        (82.0, 0.03, "toc_fuzzy_match_weak"),
    ],
)
def test_score_heading_candidate_applies_fuzzy_toc_bonus(
    match_score,
    expected_bonus,
    expected_reason,
):
    result = score_heading_candidate(
        uid="2.1",
        title="Term Loan Facility",
        raw_text="2.1 Term Loan Facility",
        toc_match={
            "match_type": "fuzzy",
            "match_score": match_score,
            "page_hint": 8,
            "toc_missing_in_body": False,
        },
    )

    assert result.status == CandidateStatus.ACCEPTED
    assert result.toc_match_score == expected_bonus
    assert result.toc_match_type == "fuzzy"
    assert expected_reason in result.accept_reasons


def test_score_heading_candidate_stale_toc_does_not_add_bonus():
    result = score_heading_candidate(
        uid="3",
        title="Representations",
        raw_text="3. Representations",
        toc_match={
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 10,
            "toc_missing_in_body": True,
        },
    )

    assert result.status == CandidateStatus.ACCEPTED
    assert result.score == 0.95
    assert result.toc_match_score == 0.0


def test_score_heading_candidate_toc_does_not_override_toc_like_line_guard():
    result = score_heading_candidate(
        uid="1",
        title="Definitions",
        raw_text="1. Definitions .......... 4",
        toc_match={
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 4,
            "toc_missing_in_body": False,
        },
    )

    assert result.status == CandidateStatus.REJECTED
    assert result.primary_reason == "toc_like_line"
    assert result.score == 0.0


def test_score_heading_candidate_toc_does_not_override_bad_title_guard():
    result = score_heading_candidate(
        uid="1",
        title="12345",
        raw_text="1. 12345",
        toc_match={
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 4,
            "toc_missing_in_body": False,
        },
    )

    assert result.status == CandidateStatus.REJECTED
    assert result.primary_reason in {
        "toc_like_line",
        "title_without_letters",
        "digit_uid_without_textual_title",
        "bad_heading_title",
    }
    assert result.score <= 0.10

from services.structure.heading_scoring import (
    CandidateStatus,
    score_heading_candidate,
)


def test_score_heading_candidate_body_like_title_stays_ambiguous_with_toc(mocker):
    mocker.patch(
        "services.structure.heading_scoring.looks_like_body_sentence_title",
        return_value=True,
    )

    result = score_heading_candidate(
        uid="2.1",
        title="Any sufficiently long text",
        raw_text="2.1 Any sufficiently long text",
        toc_match={
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 7,
            "toc_missing_in_body": False,
        },
    )

    assert result.status == CandidateStatus.AMBIGUOUS
    assert result.primary_reason == "body_like_sentence_title"
    assert result.toc_match_score <= 0.03
    assert result.toc_match_type == "exact"
    
def test_score_heading_candidate_body_like_top_level_title_stays_rejected_with_toc(mocker):
    mocker.patch(
        "services.structure.heading_scoring.looks_like_body_sentence_title",
        return_value=True,
    )

    result = score_heading_candidate(
        uid="1",
        title="Any sufficiently long text",
        raw_text="1. Any sufficiently long text",
        toc_match={
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 3,
            "toc_missing_in_body": False,
        },
    )

    assert result.status == CandidateStatus.REJECTED
    assert result.primary_reason == "body_like_sentence_title"
    assert result.toc_match_score == 0.0
