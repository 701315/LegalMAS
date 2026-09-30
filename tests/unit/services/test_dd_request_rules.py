# tests/unit/services/test_dd_request_rules.py

"""
Unit tests for services.dd_request_rules.

DD-request trigger is a pure function of check_result.review_status:
    default set = {clause_missing, clause_partially_defined, unclear}
    per-check override via CheckDefinition.dd_request_when_result
"""

from __future__ import annotations

import pytest

from services.dd_request_rules import (
    DD_REQUEST_DEFAULT_REVIEW_STATUSES,
    DD_REQUEST_DEFAULT_RESULTS,  # backward-compat alias
    normalize_dd_request_results,
    should_trigger_dd_request,
)


class TestDefaultReviewStatuses:
    def test_default_set_contains_three_statuses(self) -> None:
        assert DD_REQUEST_DEFAULT_REVIEW_STATUSES == frozenset(
            {"clause_missing", "clause_partially_defined", "unclear"}
        )

    @pytest.mark.parametrize(
        "review_status",
        ["clause_missing", "clause_partially_defined", "unclear"],
    )
    def test_default_statuses_trigger(self, review_status: str) -> None:
        cr = {"check_id": "chk_1", "review_status": review_status}
        assert should_trigger_dd_request(check_result=cr) is True

    @pytest.mark.parametrize(
        "review_status",
        [
            "clause_defined",
            "risk_detected",
            "no_issue_detected",
            "",
            None,
        ],
    )
    def test_non_default_statuses_do_not_trigger(self, review_status) -> None:
        cr = {"check_id": "chk_1", "review_status": review_status}
        assert should_trigger_dd_request(check_result=cr) is False

    def test_missing_review_status_key_does_not_trigger(self) -> None:
        cr = {"check_id": "chk_1"}
        assert should_trigger_dd_request(check_result=cr) is False

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("CLAUSE_MISSING", True),
            ("  clause_partially_defined  ", True),
            ("Clause_Defined", False),
            ("RISK_DETECTED", False),
        ],
    )
    def test_case_and_whitespace_normalized(self, raw: str, expected: bool) -> None:
        cr = {"review_status": raw}
        assert should_trigger_dd_request(check_result=cr) is expected


class TestOverride:
    def test_override_replaces_default(self) -> None:
        cr = {"review_status": "risk_detected"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=["risk_detected"]
        ) is True

    def test_override_blocks_default(self) -> None:
        cr = {"review_status": "clause_missing"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=["clause_defined"]
        ) is False

    def test_empty_override_disables_trigger(self) -> None:
        cr = {"review_status": "clause_missing"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=[]
        ) is False

    def test_none_override_falls_back_to_default(self) -> None:
        cr = {"review_status": "clause_missing"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=None
        ) is True

    def test_override_normalized(self) -> None:
        cr = {"review_status": "RISK_DETECTED"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=["  risk_detected  "]
        ) is True


class TestNormalize:
    def test_none_returns_empty(self) -> None:
        assert normalize_dd_request_results(None) == frozenset()

    def test_empty_iterable_returns_empty(self) -> None:
        assert normalize_dd_request_results([]) == frozenset()

    def test_dedup_and_normalize(self) -> None:
        out = normalize_dd_request_results(
            ["  Fail ", "FAIL", "missing_required_cla", "", None]
        )
        assert out == frozenset({"fail", "missing_required_cla"})

    def test_non_string_coerced(self) -> None:
        out = normalize_dd_request_results([1, "x"])
        assert out == frozenset({"1", "x"})
