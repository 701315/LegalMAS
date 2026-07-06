"""
Tests for DD Grid V1 extensions in load_playbook_from_dict (global playbook loader).

Covers:
- group and display_order passed through to CheckDefinition
- top-level dd_grid_columns parsed into ExtractionConfig.dd_grid_columns
- invalid dd_grid_columns items skipped gracefully
- backward compat: old compiled dicts without V1 fields still work
"""
from __future__ import annotations

import pytest

from engine.playbook.loader import _parse_dd_grid_columns, load_playbook_from_dict
from engine.playbook.models import DDGridColumnSpec


# ─── Helper ──────────────────────────────────────────────────────────────────


def _make_raw_playbook(checks: list[dict]) -> dict:
    return {"checks": checks, "meta": {"version_schema": 1}}


def _make_field_extraction_check(**overrides) -> dict:
    """
    Minimal field_extraction check that passes CheckDefinition validator.
    Has a summary field → no label required on other fact fields.
    """
    base = {
        "id": "test_check",
        "name": "Test Check",
        "detector_type": "hybrid",
        "ui_mode": "field_extraction",
        "severity": "medium",
        "group": "dispute_resolution",
        "display_order": 10,
        "extraction": {
            "enabled": True,
            "fields": [
                {
                    "name": "summary_display",
                    "type": "string",
                    "presentation": "summary",
                },
                {
                    "name": "value_field",
                    "type": "string",
                    "label": "Значение",
                },
            ],
        },
    }
    base.update(overrides)
    return base


# ─── _parse_dd_grid_columns unit tests ───────────────────────────────────────


class TestParseDDGridColumns:
    """Unit tests for the _parse_dd_grid_columns helper."""

    def test_none_returns_none(self):
        assert _parse_dd_grid_columns(None, check_id="chk") is None

    def test_empty_list_returns_none(self):
        assert _parse_dd_grid_columns([], check_id="chk") is None

    def test_not_a_list_returns_none(self):
        assert _parse_dd_grid_columns("invalid", check_id="chk") is None  # type: ignore[arg-type]

    def test_valid_columns_parsed(self):
        raw = [
            {"column_id": "col1", "label": "Column 1", "display_order": 10},
            {"column_id": "col2", "label": "Column 2", "format": "enum", "display_order": 20},
        ]
        result = _parse_dd_grid_columns(raw, check_id="chk")
        assert result is not None
        assert len(result) == 2
        assert isinstance(result[0], DDGridColumnSpec)
        assert result[0].column_id == "col1"
        assert result[1].format == "enum"

    def test_invalid_item_skipped_gracefully(self):
        raw = [
            {"column_id": "col1", "label": "Valid"},
            {"no_column_id_here": "bad"},  # missing required column_id
            "not_a_dict",
        ]
        result = _parse_dd_grid_columns(raw, check_id="chk")  # type: ignore[arg-type]
        assert result is not None
        assert len(result) == 1
        assert result[0].column_id == "col1"

    def test_all_invalid_items_returns_none(self):
        raw = [
            {"no_column_id": "bad1"},
            {"no_column_id": "bad2"},
        ]
        result = _parse_dd_grid_columns(raw, check_id="chk")
        assert result is None


# ─── load_playbook_from_dict: group + display_order ──────────────────────────


class TestLoadPlaybookFromDictGroupAndDisplayOrder:
    """group and display_order must be passed through to CheckDefinition."""

    def test_group_passed_through(self):
        raw = _make_raw_playbook([
            _make_field_extraction_check(id="c1", group="liability", display_order=5),
        ])
        playbook = load_playbook_from_dict(raw)
        check = playbook.checks[0]
        assert check.group == "liability"

    def test_display_order_passed_through(self):
        raw = _make_raw_playbook([
            _make_field_extraction_check(id="c1", display_order=25),
        ])
        playbook = load_playbook_from_dict(raw)
        assert playbook.checks[0].display_order == 25

    def test_missing_group_defaults_to_none(self):
        check_data = _make_field_extraction_check(id="c1")
        check_data.pop("group", None)
        raw = _make_raw_playbook([check_data])
        playbook = load_playbook_from_dict(raw)
        assert playbook.checks[0].group is None

    def test_missing_display_order_defaults_to_zero(self):
        check_data = _make_field_extraction_check(id="c1")
        check_data.pop("display_order", None)
        raw = _make_raw_playbook([check_data])
        playbook = load_playbook_from_dict(raw)
        assert playbook.checks[0].display_order == 0

    def test_multiple_checks_each_get_own_group_and_order(self):
        raw = _make_raw_playbook([
            _make_field_extraction_check(id="c1", group="liability", display_order=10),
            _make_field_extraction_check(id="c2", group="finance", display_order=20),
        ])
        playbook = load_playbook_from_dict(raw)
        by_id = {c.id: c for c in playbook.checks}
        assert by_id["c1"].group == "liability"
        assert by_id["c1"].display_order == 10
        assert by_id["c2"].group == "finance"
        assert by_id["c2"].display_order == 20


# ─── load_playbook_from_dict: dd_grid_columns ────────────────────────────────


class TestLoadPlaybookFromDictDDGridColumns:
    """dd_grid_columns from top-level must be injected into ExtractionConfig."""

    def test_dd_grid_columns_injected_into_extraction(self):
        check_data = _make_field_extraction_check(id="c1")
        check_data["dd_grid_columns"] = [
            {
                "column_id": "gov_law",
                "label": "Применимое право",
                "value_field": "governing_law_value",
                "display_order": 10,
            }
        ]
        raw = _make_raw_playbook([check_data])
        playbook = load_playbook_from_dict(raw)
        check = playbook.checks[0]

        assert check.extraction is not None
        assert check.extraction.dd_grid_columns is not None
        assert len(check.extraction.dd_grid_columns) == 1
        assert check.extraction.dd_grid_columns[0].column_id == "gov_law"

    def test_invalid_dd_grid_columns_skipped_gracefully(self):
        check_data = _make_field_extraction_check(id="c1")
        check_data["dd_grid_columns"] = [
            {"column_id": "valid_col", "label": "Valid"},
            {"no_column_id": "bad"},
        ]
        raw = _make_raw_playbook([check_data])
        playbook = load_playbook_from_dict(raw)
        check = playbook.checks[0]

        assert check.extraction is not None
        assert check.extraction.dd_grid_columns is not None
        assert len(check.extraction.dd_grid_columns) == 1
        assert check.extraction.dd_grid_columns[0].column_id == "valid_col"

    def test_dd_grid_columns_without_extraction_ignored(self):
        """
        dd_grid_columns declared at top level but extraction is absent
        → dd_grid_columns must be silently ignored, check loads successfully.
        """
        raw = _make_raw_playbook([
            {
                "id": "c1",
                "name": "C1",
                "detector_type": "rules",
                "severity": "medium",
                "dd_grid_columns": [
                    {"column_id": "col1", "label": "Col 1"},
                ],
            }
        ])
        playbook = load_playbook_from_dict(raw)
        check = playbook.checks[0]
        assert check.extraction is None

    def test_no_dd_grid_columns_extraction_still_works(self):
        """Backward compat: no dd_grid_columns → extraction.dd_grid_columns is None."""
        raw = _make_raw_playbook([_make_field_extraction_check(id="c1")])
        playbook = load_playbook_from_dict(raw)
        check = playbook.checks[0]
        assert check.extraction is not None
        assert check.extraction.dd_grid_columns is None


# ─── Backward compatibility ───────────────────────────────────────────────────


class TestLoadPlaybookFromDictBackwardCompat:
    """Old compiled dicts without V1 fields still load correctly."""

    def test_old_check_without_group_display_order_dd_grid_columns(self):
        raw = _make_raw_playbook([
            {
                "id": "legacy_check",
                "name": "Legacy",
                "detector_type": "rules",
                "severity": "medium",
                "ui_mode": "risk_detection",
                "rules": {"keywords": ["риск"]},
            }
        ])
        playbook = load_playbook_from_dict(raw)
        check = playbook.checks[0]

        assert check.id == "legacy_check"
        assert check.group is None
        assert check.display_order == 0
        assert check.extraction is None
        assert check.ui_mode == "risk_detection"


        