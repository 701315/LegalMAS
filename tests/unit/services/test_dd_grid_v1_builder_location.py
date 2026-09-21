"""Unit tests for B0.3 location-positive-only filter in dd_grid_v1_builder."""
from __future__ import annotations

import pytest

from services.dd_grid_v1_builder import _is_positive_location_finding


@pytest.mark.parametrize("ui_mode,review_status,expected", [
    # Positive findings — location preserved
    ("field_extraction", "no_issue_detected", True),
    ("field_extraction", "unclear",           True),
    ("clause_presence",  "no_issue_detected", True),
    ("clause_presence",  "unclear",           True),
    ("risk_detection",   "issue_detected",    True),
    ("risk_detection",   "unclear",           True),
    # Negative findings — location suppressed
    ("field_extraction", "clause_missing",    False),
    ("clause_presence",  "clause_missing",    False),
    ("risk_detection",   "no_issue_detected", False),
    ("field_extraction", "not_applicable",    False),
    ("field_extraction", "technical_failure", False),
    ("field_extraction", "manual_review_required", False),
    # Fail-safe: unknown values -> suppress
    ("unknown_mode",     "no_issue_detected", False),
    ("field_extraction", "unknown_status",    False),
    (None,               "no_issue_detected", False),
    ("",                 "no_issue_detected", False),
])
def test_positive_location_finding_matrix(ui_mode, review_status, expected):
    assert _is_positive_location_finding(ui_mode, review_status) is expected


def test_case_insensitive_normalization():
    assert _is_positive_location_finding("FIELD_EXTRACTION", "NO_ISSUE_DETECTED") is True
    assert _is_positive_location_finding(" field_extraction ", " unclear ") is True
    assert _is_positive_location_finding("Field_Extraction", "Clause_Missing") is False


def test_legacy_review_status_none_returns_none():
    """review_status=None -> legacy path, caller uses cell_state only."""
    assert _is_positive_location_finding("field_extraction", None) is None
    assert _is_positive_location_finding(None, None) is None
    assert _is_positive_location_finding("clause_presence", None) is None
