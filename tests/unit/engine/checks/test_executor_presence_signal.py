"""Unit tests for CheckExecutor._classify_presence_signal verdicts."""
from __future__ import annotations

import pytest

from engine.checks.executor import CheckExecutor
from engine.playbook.models import PresenceSignalConfig


@pytest.fixture
def signal() -> PresenceSignalConfig:
    return PresenceSignalConfig(
        field="coc_status",
        present_values=["present"],
        missing_values=["missing"],
        unclear_values=["unclear"],
    )


def _payload(value, *, found=True):
    return {"value": value, "found": found}


def test_present_verdict(signal):
    sd = {"coc_status": _payload("present")}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "present"


def test_missing_verdict(signal):
    sd = {"coc_status": _payload("missing")}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "missing"


def test_unclear_verdict(signal):
    sd = {"coc_status": _payload("unclear")}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "unclear"


def test_undeclared_verdict(signal):
    sd = {"coc_status": _payload("some_other_token")}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "undeclared"


def test_not_extracted_when_structured_data_none(signal):
    assert CheckExecutor._classify_presence_signal(None, signal) == "not_extracted"


def test_not_extracted_when_field_absent(signal):
    sd = {"other_field": _payload("x")}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "not_extracted"


def test_not_extracted_when_payload_not_dict(signal):
    sd = {"coc_status": "present"}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "not_extracted"


def test_not_extracted_when_found_false(signal):
    sd = {"coc_status": _payload("present", found=False)}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "not_extracted"


def test_case_insensitive_matching(signal):
    sd = {"coc_status": _payload("PRESENT")}
    assert CheckExecutor._classify_presence_signal(sd, signal) == "present"
