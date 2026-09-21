"""Unit tests for B1.1: sanitize structural markers in location_clause_ref."""
from __future__ import annotations

import pytest

from services.dd_grid_v1_builder import (
    _derive_clause_ref_from_uid,
    _is_structural_marker,
    _normalize_location_bundle,
)


@pytest.mark.parametrize("value,expected", [
    ("__preamble__", True),
    ("__metadata__", True),
    ("__header__", True),
    ("__intro__", True),
    ("__some_long_marker__", True),
    ("__marker_with_123__", True),
    ("__PREAMBLE__", False),          # case-sensitive
    ("__ pre amble __", False),       # spaces
    ("__preamble__extra", False),     # not fully wrapped
    ("п. 1.2", False),
    ("cl. 3.5", False),
    ("Преамбула", False),
    ("", False),
    (None, False),
])
def test_is_structural_marker(value, expected):
    assert _is_structural_marker(value) is expected


def test_derive_clause_ref_handles_preamble():
    assert _derive_clause_ref_from_uid("main_contract:__preamble__") is None


def test_derive_clause_ref_handles_arbitrary_marker():
    assert _derive_clause_ref_from_uid("main_contract:__metadata__") is None
    assert _derive_clause_ref_from_uid("main_contract:__header__") is None


def test_derive_clause_ref_normal_number():
    assert _derive_clause_ref_from_uid("main_contract:7.2") == "п. 7.2"
    assert _derive_clause_ref_from_uid("main_contract:7.2", is_en=True) == "cl. 7.2"


def test_normalize_bundle_sanitizes_marker():
    ref, page, conf = _normalize_location_bundle(
        location_clause_ref="__preamble__",
        location_page=1,
        location_confidence="low",
    )
    assert ref is None
    assert page == 1
    assert conf == "low"


def test_normalize_bundle_keeps_valid_ref():
    ref, page, conf = _normalize_location_bundle(
        location_clause_ref="п. 7.2",
        location_page=4,
        location_confidence="medium",
    )
    assert ref == "п. 7.2"
    assert page == 4


def test_normalize_bundle_sanitizes_other_markers():
    for marker in ("__metadata__", "__header__", "__intro__"):
        ref, _, _ = _normalize_location_bundle(
            location_clause_ref=marker,
            location_page=1,
            location_confidence=None,
        )
        assert ref is None, f"{marker} not sanitized"
