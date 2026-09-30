# tests/unit/services/test_dd_request_rules.py

"""
Unit tests for services.dd_request_rules.

DD-request trigger is a pure function of check_result.result:
    default set = {missing_required_cla, unclear}
    per-check override via CheckDefinition.dd_request_when_result
"""

from __future__ import annotations

import pytest

from services.dd_request_rules import (
    DD_REQUEST_DEFAULT_RESULTS,
    normalize_dd_request_results,
    should_trigger_dd_request,
)


class TestDefaultResults:
    def test_default_set_contains_missing_and_unclear(self) -> None:
        assert DD_REQUEST_DEFAULT_RESULTS == frozenset(
            {"missing_required_cla", "unclear"}
        )

    @pytest.mark.parametrize("result", ["missing_required_cla", "unclear"])
    def test_default_results_trigger(self, result: str) -> None:
        cr = {"check_id": "chk_1", "result": result}
        assert should_trigger_dd_request(check_result=cr) is True

    @pytest.mark.parametrize(
        "result",
        [
            "pass",
            "fail",
            "not_applicable",
            "no",
            "defined",
            "not_defined",
            "",
            None,
        ],
    )
    def test_non_default_results_do_not_trigger(self, result) -> None:
        cr = {"check_id": "chk_1", "result": result}
        assert should_trigger_dd_request(check_result=cr) is False

    def test_missing_result_key_does_not_trigger(self) -> None:
        cr = {"check_id": "chk_1"}
        assert should_trigger_dd_request(check_result=cr) is False

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("MISSING_REQUIRED_CLA", True),
            ("  unclear  ", True),
            ("Pass", False),
            ("FAIL", False),
        ],
    )
    def test_case_and_whitespace_normalized(self, raw: str, expected: bool) -> None:
        cr = {"result": raw}
        assert should_trigger_dd_request(check_result=cr) is expected


class TestOverride:
    def test_override_replaces_default(self) -> None:
        cr = {"result": "fail"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=["fail"]
        ) is True

    def test_override_blocks_default(self) -> None:
        cr = {"result": "missing_required_cla"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=["pass"]
        ) is False

    def test_empty_override_disables_trigger(self) -> None:
        cr = {"result": "missing_required_cla"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=[]
        ) is False

    def test_none_override_falls_back_to_default(self) -> None:
        cr = {"result": "missing_required_cla"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=None
        ) is True

    def test_override_normalized(self) -> None:
        cr = {"result": "FAIL"}
        assert should_trigger_dd_request(
            check_result=cr, override_results=["  fail  "]
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
