"""
Tests for DD Grid V1 extensions in DocTypeCheckLoader.

Covers:
- _parse_extraction: role field passed through to ExtractionFieldConfig
- _parse_extraction: dd_grid_columns passed through to ExtractionConfig
- _parse_extraction: legacy list[str] allowed_values still work
- _parse_extraction: list[dict] allowed_values (AllowedValueSpec) still work
- _build_check_from_v8: display_order passed through to CheckDefinition
- _build_check_from_doc_type: display_order passed through to CheckDefinition
- group is NOT propagated for doc-type checks
"""
from __future__ import annotations

import pytest

from engine.doc_type_checks.loader import DocTypeCheckLoader
from engine.playbook.models import AllowedValueSpec


def _make_loader() -> DocTypeCheckLoader:
    """Create loader without filesystem (used for internal method tests)."""
    return DocTypeCheckLoader.__new__(DocTypeCheckLoader)


# ─── _parse_extraction: role ──────────────────────────────────────────────────


class TestParseExtractionRole:
    """role field must be passed through to ExtractionFieldConfig."""

    def test_role_subgroup_metadata_passed_through(self):
        loader = _make_loader()
        extraction_cfg = {
            "enabled": True,
            "fields": [
                {
                    "name": "summary_display",
                    "type": "string",
                    "presentation": "summary",
                },
                {
                    "name": "evidence",
                    "type": "evidence_list",
                    "presentation": "diagnostic",
                    "role": "subgroup_metadata",
                },
            ],
        }
        result = loader._parse_extraction(extraction_cfg)
        assert result is not None
        fields_by_name = {f.name: f for f in result.fields}
        assert fields_by_name["evidence"].role == "subgroup_metadata"

    def test_role_none_by_default(self):
        loader = _make_loader()
        extraction_cfg = {
            "enabled": True,
            "fields": [
                {
                    "name": "value_field",
                    "type": "string",
                    "label": "Значение",
                },
            ],
        }
        result = loader._parse_extraction(extraction_cfg)
        assert result is not None
        assert result.fields[0].role is None

    def test_arbitrary_role_accepted(self):
        loader = _make_loader()
        extraction_cfg = {
            "enabled": True,
            "fields": [
                {
                    "name": "summary_display",
                    "presentation": "summary",
                },
                {
                    "name": "x_field",
                    "label": "X",
                    "role": "custom_role",
                },
            ],
        }
        result = loader._parse_extraction(extraction_cfg)
        assert result is not None
        fields_by_name = {f.name: f for f in result.fields}
        assert fields_by_name["x_field"].role == "custom_role"


# ─── _parse_extraction: dd_grid_columns ──────────────────────────────────────


class TestParseExtractionDDGridColumns:
    """dd_grid_columns must be passed through to ExtractionConfig."""

    def test_dd_grid_columns_passed_through(self):
        loader = _make_loader()
        extraction_cfg = {
            "enabled": True,
            "fields": [
                {"name": "summary_display", "presentation": "summary"},
            ],
            "dd_grid_columns": [
                {
                    "column_id": "gov_law",
                    "label": "Применимое право",
                    "value_field": "governing_law_value",
                    "display_order": 10,
                },
                {
                    "column_id": "forum",
                    "label": "Форум",
                    "value_field": "forum_value",
                    "display_order": 20,
                },
            ],
        }
        result = loader._parse_extraction(extraction_cfg)
        assert result is not None
        assert result.dd_grid_columns is not None
        assert len(result.dd_grid_columns) == 2
        assert result.dd_grid_columns[0].column_id == "gov_law"
        assert result.dd_grid_columns[1].label == "Форум"

    def test_no_dd_grid_columns_defaults_to_none(self):
        loader = _make_loader()
        extraction_cfg = {
            "enabled": True,
            "fields": [
                {"name": "value_field", "label": "Значение"},
            ],
        }
        result = loader._parse_extraction(extraction_cfg)
        assert result is not None
        assert result.dd_grid_columns is None


# ─── _parse_extraction: allowed_values formats ───────────────────────────────


class TestParseExtractionAllowedValues:
    """Both list[str] and list[dict] (AllowedValueSpec) formats work."""

    def test_legacy_list_str_allowed_values(self):
        loader = _make_loader()
        extraction_cfg = {
            "enabled": True,
            "fields": [
                {
                    "name": "status",
                    "label": "Статус",
                    "allowed_values": ["defined", "not_defined"],
                },
            ],
        }
        result = loader._parse_extraction(extraction_cfg)
        assert result is not None
        assert result.fields[0].allowed_values == ["defined", "not_defined"]

    def test_allowed_value_spec_dicts(self):
        loader = _make_loader()
        extraction_cfg = {
            "enabled": True,
            "fields": [
                {
                    "name": "status",
                    "label": "Статус",
                    "allowed_values": [
                        {"value": "defined", "label": "Указано", "display_order": 10},
                        {"value": "not_defined", "label": "Не указано", "display_order": 20},
                    ],
                },
            ],
        }
        result = loader._parse_extraction(extraction_cfg)
        assert result is not None
        specs = result.fields[0].allowed_values
        assert len(specs) == 2
        assert isinstance(specs[0], AllowedValueSpec)
        assert specs[0].value == "defined"
        assert specs[0].label == "Указано"
        assert specs[1].display_order == 20


# ─── _build_check_from_v8: display_order ─────────────────────────────────────


class TestBuildCheckFromV8DisplayOrder:
    """display_order must be passed through to CheckDefinition."""

    def test_explicit_display_order(self):
        loader = _make_loader()
        item = {
            "id": "test_check",
            "name": "Test",
            "detector_type": "rules",
            "severity": "medium",
            "display_order": 15,
            "rules": {"keywords": ["тест"]},
        }
        check = loader._build_check_from_v8(item, "test_type", {})
        assert check is not None
        assert check.display_order == 15

    def test_missing_display_order_defaults_to_zero(self):
        loader = _make_loader()
        item = {
            "id": "test_check",
            "name": "Test",
            "detector_type": "rules",
            "severity": "medium",
            "rules": {"keywords": ["тест"]},
        }
        check = loader._build_check_from_v8(item, "test_type", {})
        assert check is not None
        assert check.display_order == 0

    def test_group_is_not_set_for_doc_type_checks(self):
        """
        Doc-type checks must NOT have group — grouping is via doc-type class/type.
        """
        loader = _make_loader()
        item = {
            "id": "test_check",
            "name": "Test",
            "detector_type": "rules",
            "severity": "medium",
            "group": "should_be_ignored",
            "rules": {"keywords": ["тест"]},
        }
        check = loader._build_check_from_v8(item, "test_type", {})
        assert check is not None
        # group should be None — doc-type checks don't use global group hierarchy
        assert check.group is None


# ─── _build_check_from_doc_type: display_order ───────────────────────────────


class TestBuildCheckFromDocTypeDisplayOrder:
    """display_order must be passed through to CheckDefinition."""

    def test_explicit_display_order(self):
        loader = _make_loader()
        item = {
            "id": "rules_check",
            "name": "Rules Check",
            "severity": "medium",
            "display_order": 30,
            "rules": {"keywords": ["ключевое слово"]},
        }
        check = loader._build_check_from_doc_type(item, "test_type", {})
        assert check is not None
        assert check.display_order == 30

    def test_missing_display_order_defaults_to_zero(self):
        loader = _make_loader()
        item = {
            "id": "rules_check",
            "name": "Rules Check",
            "severity": "medium",
            "rules": {"keywords": ["ключевое слово"]},
        }
        check = loader._build_check_from_doc_type(item, "test_type", {})
        assert check is not None
        assert check.display_order == 0


# ─── Backward compat ─────────────────────────────────────────────────────────


class TestDocTypeLoaderBackwardCompat:
    """Old YAML items without V1 fields still load correctly."""

    def test_old_v8_item_without_v1_fields(self):
        loader = _make_loader()
        item = {
            "id": "legacy_v8",
            "name": "Legacy V8 Check",
            "detector_type": "hybrid",
            "severity": "high",
            "ui_mode": "risk_detection",
            "rules": {"keywords": ["риск"]},
            "llm": {"prompt_template": "test"},
        }
        check = loader._build_check_from_v8(item, "contract_1.1_general_sale", {})
        assert check is not None
        assert check.id == "legacy_v8"
        assert check.display_order == 0
        assert check.group is None
        assert check.extraction is None

    def test_old_doc_type_item_without_v1_fields(self):
        loader = _make_loader()
        item = {
            "id": "legacy_doc_type",
            "name": "Legacy Doc Type Check",
            "severity": "medium",
            "rules": {"keywords": ["обязательство"]},
        }
        check = loader._build_check_from_doc_type(item, "contract_2.1_lease", {})
        assert check is not None
        assert check.display_order == 0
        assert check.group is None


        