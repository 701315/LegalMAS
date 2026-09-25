"""Unit tests for _is_structural_marker and _normalize_location_bundle.

B7.9: honest field anchor — structural markers must not leak as
user-facing clause_ref + page references. Two invariants:
1. Scope-prefixed structural markers (main_contract:__preamble__) are
   recognized as structural markers, not as clause references.
2. When clause_ref is a structural marker — both clause_ref AND page
   are dropped. Page without clause_ref is a misleading reference.
"""
from __future__ import annotations

import pytest

from services.dd_grid_v1_builder import (
    _is_structural_marker,
    _normalize_location_bundle,
)


# ── _is_structural_marker ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value, expected",
    [
        # Bare structural markers — legacy behavior preserved
        ("__preamble__", True),
        ("__metadata__", True),
        ("__header__", True),
        ("  __preamble__  ", True),  # whitespace tolerated
        # Scope-prefixed structural markers — new contract
        ("main_contract:__preamble__", True),
        ("appendix_1:__header__", True),
        ("some_scope_2:__metadata__", True),
        # Regular clause references — NOT structural
        ("main_contract:7.3", False),
        ("main_contract:S", False),
        ("п. 5.1", False),
        ("п. 7.1.2", False),
        (None, False),
        ("", False),
    ],
)
def test_is_structural_marker(value, expected):
    assert _is_structural_marker(value) is expected


# ── _normalize_location_bundle — main fix ────────────────────────────────────


def test_normalize_drops_page_for_scoped_preamble():
    """B7.9 core case: scoped __preamble__ must drop both clause_ref and page."""
    clause_ref, page, confidence = _normalize_location_bundle(
        location_clause_ref="main_contract:__preamble__",
        location_page=2,
        location_confidence="low",
    )
    assert clause_ref is None
    assert page is None
    assert confidence == "low"


def test_normalize_drops_page_for_bare_preamble():
    """Bare __preamble__ must also drop both fields."""
    clause_ref, page, confidence = _normalize_location_bundle(
        location_clause_ref="__preamble__",
        location_page=2,
        location_confidence="low",
    )
    assert clause_ref is None
    assert page is None
    assert confidence == "low"


def test_normalize_keeps_real_clause_with_page():
    """Regression: real clause references pass through unchanged."""
    clause_ref, page, confidence = _normalize_location_bundle(
        location_clause_ref="main_contract:7.3",
        location_page=6,
        location_confidence="high",
    )
    assert clause_ref == "main_contract:7.3"
    assert page == 6
    assert confidence == "high"


def test_normalize_keeps_page_without_clause_ref():
    """Regression: page-only provenance (no clause_ref) is preserved.

    This case occurs for risk-detection checks where clause_ref is
    legitimately absent but page is meaningful.
    """
    clause_ref, page, confidence = _normalize_location_bundle(
        location_clause_ref=None,
        location_page=5,
        location_confidence="low",
    )
    assert clause_ref is None
    assert page == 5
    assert confidence == "low"


def test_normalize_english_prefix_localization():
    """Regression: English localization converts 'п. N' to 'cl. N'."""
    clause_ref, page, confidence = _normalize_location_bundle(
        location_clause_ref="п. 5.1",
        location_page=4,
        location_confidence="high",
        localization_map={"dd_grid.system.lang": "en"},
    )
    assert clause_ref == "cl. 5.1"
    assert page == 4
    assert confidence == "high"


    