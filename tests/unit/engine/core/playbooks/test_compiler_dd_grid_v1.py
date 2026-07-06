"""
Tests for DD Grid V1 extensions in GlobalCheckConfig (compiler).

Covers:
- display_order field
- dd_grid_columns field (raw dict)
- Backward compatibility: old YAML without new fields
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.playbooks.compiler import GlobalCheckConfig


class TestGlobalCheckConfigDisplayOrder:
    """GlobalCheckConfig.display_order field."""

    def test_default_zero(self):
        cfg = GlobalCheckConfig(
            id="chk_1",
            name="Check 1",
            detector_type="rules",
        )
        assert cfg.display_order == 0

    def test_explicit_value(self):
        cfg = GlobalCheckConfig(
            id="chk_2",
            name="Check 2",
            detector_type="llm",
            display_order=15,
        )
        assert cfg.display_order == 15


class TestGlobalCheckConfigDDGridColumns:
    """GlobalCheckConfig.dd_grid_columns field (raw dict storage)."""

    def test_default_none(self):
        cfg = GlobalCheckConfig(
            id="chk_3",
            name="Check 3",
            detector_type="rules",
        )
        assert cfg.dd_grid_columns is None

    def test_explicit_columns(self):
        columns = [
            {
                "column_id": "governing_law",
                "label": "Применимое право",
                "value_field": "governing_law_value",
                "display_order": 10,
            },
            {
                "column_id": "forum",
                "label": "Форум разрешения споров",
                "value_field": "forum_value",
                "format": "text",
                "display_order": 20,
            },
        ]
        cfg = GlobalCheckConfig(
            id="chk_4",
            name="Check 4",
            detector_type="llm",
            dd_grid_columns=columns,
        )
        assert cfg.dd_grid_columns is not None
        assert len(cfg.dd_grid_columns) == 2
        assert cfg.dd_grid_columns[0]["column_id"] == "governing_law"
        assert cfg.dd_grid_columns[1]["format"] == "text"

    def test_empty_list(self):
        cfg = GlobalCheckConfig(
            id="chk_5",
            name="Check 5",
            detector_type="rules",
            dd_grid_columns=[],
        )
        assert cfg.dd_grid_columns == []


class TestGlobalCheckConfigBackwardCompat:
    """Old YAML without V1 fields still parses correctly."""

    def test_old_style_dict(self):
        raw = {
            "id": "chk_old",
            "name": "Old Check",
            "detector_type": "hybrid",
            "severity": "high",
            "group": "liability",
            "ui_mode": "field_extraction",
            "doc_types": ["spa", "lease"],
            "rules": {"keywords": ["liability"]},
            "extraction": {"enabled": True},
        }
        cfg = GlobalCheckConfig(**raw)
        assert cfg.display_order == 0
        assert cfg.dd_grid_columns is None
        assert cfg.group == "liability"
        assert cfg.ui_mode == "field_extraction"

    def test_all_fields_together(self):
        """Full config with both old and new fields."""
        cfg = GlobalCheckConfig(
            id="chk_full",
            name="Full Check",
            detector_type="llm",
            severity="critical",
            group="dispute_resolution",
            display_order=5,
            ui_mode="field_extraction",
            extraction={"enabled": True},
            dd_grid_columns=[
                {"column_id": "c1", "label": "Col 1"},
            ],
        )
        assert cfg.group == "dispute_resolution"
        assert cfg.display_order == 5
        assert cfg.dd_grid_columns is not None
        assert len(cfg.dd_grid_columns) == 1


        