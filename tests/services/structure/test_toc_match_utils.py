import pytest

from services.structure.toc_match_utils import (
    normalize_toc_match_title,
    toc_match_payload,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Definitions", "definitions"),
        ("  Definitions  ", "definitions"),
        ("DEFINITIONS", "definitions"),
        ("Definitions.", "definitions"),
        ("Definitions - General", "definitions general"),
        ("Definitions / General", "definitions general"),
        ("Definitions   General", "definitions general"),
    ],
)
def test_normalize_toc_match_title(raw, expected):
    assert normalize_toc_match_title(raw) == expected


def test_toc_match_payload_returns_exact_payload():
    toc_match_index = {
        ("1", "definitions"): {
            "match_type": "exact",
            "match_score": 100.0,
            "page_hint": 4,
            "toc_missing_in_body": False,
        }
    }

    payload = toc_match_payload(
        raw_uid="1",
        title="Definitions",
        toc_match_index=toc_match_index,
    )

    assert payload is not None
    assert payload["match_type"] == "exact"
    assert payload["page_hint"] == 4
    assert payload["toc_missing_in_body"] is False


def test_toc_match_payload_uses_normalized_title_lookup():
    toc_match_index = {
        ("2.1", "term loan facility"): {
            "match_type": "fuzzy",
            "match_score": 91.0,
            "page_hint": 7,
            "toc_missing_in_body": False,
        }
    }

    payload = toc_match_payload(
        raw_uid="2.1",
        title="Term Loan Facility.",
        toc_match_index=toc_match_index,
    )

    assert payload is not None
    assert payload["match_type"] == "fuzzy"
    assert payload["match_score"] == 91.0


def test_toc_match_payload_returns_none_for_unknown_key():
    toc_match_index = {
        ("1", "definitions"): {"match_type": "exact"},
    }

    payload = toc_match_payload(
        raw_uid="2",
        title="Representations",
        toc_match_index=toc_match_index,
    )

    assert payload is None


def test_toc_match_payload_returns_none_when_index_missing():
    payload = toc_match_payload(
        raw_uid="1",
        title="Definitions",
        toc_match_index=None,
    )
    assert payload is None


    