# tests/unit/engine/detectors/test_salvage_partial_json.py
"""
Tests for _salvage_partial_json robustness under JSON truncation.

Covers three salvage passes:
  Pass 1 — complete field blocks (short strings, null, bool, numbers).
  Pass 2 — partial long string values (truncated mid-string).
  Pass 3 — short signal values without confidence key.

Universal: not specific to any document type or check.
"""

import pytest

from engine.detectors.extraction_llm_detector import _salvage_partial_json


class TestPass1CompletFieldBlocks:
    """Pass 1: syntactically complete field blocks."""

    def test_recovers_short_string_value(self):
        text = '''
        "asset_schedule_status": {"value": "defined", "confidence": 0.95}
        '''
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["asset_schedule_status"]["value"] == "defined"
        assert result["fields"]["asset_schedule_status"]["confidence"] == 0.95

    def test_recovers_null_value(self):
        text = '"some_field": {"value": null, "confidence": 0.5}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["some_field"]["value"] is None

    def test_recovers_boolean_value(self):
        text = '"flag_field": {"value": true, "confidence": 0.8}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["flag_field"]["value"] is True

    def test_recovers_number_value(self):
        text = '"count_field": {"value": 42, "confidence": 0.9}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["count_field"]["value"] == 42

    def test_recovers_multiple_complete_fields(self):
        text = '''
        "status": {"value": "defined", "confidence": 0.95},
        "count": {"value": 5, "confidence": 0.8}
        '''
        result = _salvage_partial_json(text)
        assert result is not None
        assert "status" in result["fields"]
        assert "count" in result["fields"]

    def test_returns_none_when_no_complete_fields_and_no_partial(self):
        text = "this is not json at all"
        result = _salvage_partial_json(text)
        assert result is None

    def test_confidence_clamped_to_zero_one(self):
        text = '"f": {"value": "x", "confidence": 1.5}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["f"]["confidence"] == 1.0


class TestPass2PartialLongStringValues:
    """Pass 2: partial long string values truncated mid-string."""

    def test_recovers_partial_inventory_string(self):
        # Simulate: LLM wrote value but truncation happened before closing quote
        partial_value = "Нежилое здание | 77:01:0001001:123 | 120,5 кв.м. | г. Москва, ул. Ленина\nЗемельный участок | 50:22"
        text = f'"asset_schedule_details": {{"value": "{partial_value}'
        # No closing quote, no confidence key — truncated here

        result = _salvage_partial_json(text)
        assert result is not None
        field = result["fields"]["asset_schedule_details"]
        assert partial_value[:30] in field["value"]
        assert "ОБРЕЗАН" in field["value"] or "СПИСОК" in field["value"]
        assert field["confidence"] == 0.5

    def test_pass2_not_applied_when_pass1_succeeded(self):
        # If Pass 1 already recovered the field, Pass 2 must not override it.
        text = '''
        "asset_schedule_details": {"value": "complete value", "confidence": 0.9},
        "asset_schedule_details": {"value": "partial long string without closing
        '''
        result = _salvage_partial_json(text)
        assert result is not None
        # Pass 1 wins: value should be the complete one
        assert result["fields"]["asset_schedule_details"]["value"] == "complete value"
        assert result["fields"]["asset_schedule_details"]["confidence"] == 0.9

    def test_pass2_ignores_too_short_partial(self):
        # Partial text shorter than 30 chars must not be recovered
        text = '"some_field": {"value": "short'
        result = _salvage_partial_json(text)
        # Nothing recoverable
        assert result is None or "some_field" not in (result or {}).get("fields", {})

    def test_pass2_strips_trailing_backslash(self):
        partial = "А" * 35 + "\\"
        text = f'"details": {{"value": "{partial}'
        result = _salvage_partial_json(text)
        assert result is not None
        field = result["fields"]["details"]
        assert not field["value"].startswith("… [")  # Has actual content
        assert "ОБРЕЗАН" in field["value"]

    def test_full_truncated_inventory_json(self):
        # Realistic simulation: two-field inventory check, second field truncated
        text = (
            '{"fields": {'
            '"asset_schedule_status": {"value": "defined", "confidence": 0.95},'
            '"asset_schedule_details": {"value": "Нежилое здание | 77:01:0001001:123 | '
            '120,5 кв.м. | г. Москва\\nЗемельный участок | 50:22:0030001:45 | '
            '3500 кв.м. | Московская область'
            # Truncated here — no closing quote, no confidence, no closing braces
        )

        result = _salvage_partial_json(text)
        assert result is not None
        fields = result["fields"]

        # Pass 1: status recovered completely
        assert fields["asset_schedule_status"]["value"] == "defined"
        assert fields["asset_schedule_status"]["confidence"] == 0.95

        # Pass 2: details recovered partially
        assert "asset_schedule_details" in fields
        details_value = fields["asset_schedule_details"]["value"]
        assert "77:01:0001001:123" in details_value
        assert "ОБРЕЗАН" in details_value
        assert fields["asset_schedule_details"]["confidence"] == 0.5


class TestPass3ShortSignalWithoutConfidence:
    """Pass 3: short signal values where confidence key was not yet written."""

    def test_recovers_signal_field_without_confidence(self):
        # Truncated after closing quote of value, before "confidence" key
        text = '"status_field": {"value": "defined"'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["status_field"]["value"] == "defined"

    def test_pass3_not_applied_when_pass1_succeeded(self):
        text = (
            '"status": {"value": "defined", "confidence": 0.95},'
            '"status": {"value": "other"'
        )
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["status"]["confidence"] == 0.95

    def test_pass3_not_applied_when_pass2_succeeded(self):
        long_partial = "А" * 35
        text = (
            f'"details": {{"value": "{long_partial},'
            f'"details": {{"value": "short"'
        )
        result = _salvage_partial_json(text)
        assert result is not None
        # Pass 2 wins for long partial
        assert len(result["fields"]["details"]["value"]) > 35


class TestSalvageEdgeCases:
    """Edge cases for salvage robustness."""

    def test_empty_string_returns_none(self):
        assert _salvage_partial_json("") is None

    def test_whitespace_only_returns_none(self):
        assert _salvage_partial_json("   \n  ") is None

    def test_valid_complete_json_passes_through_pass1(self):
        text = '"field_a": {"value": "val_a", "confidence": 0.7}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["field_a"]["value"] == "val_a"

    def test_field_name_pattern_requires_lowercase_and_underscore(self):
        # CamelCase field names not matched — our schema uses snake_case
        text = '"CamelField": {"value": "x", "confidence": 0.9}'
        result = _salvage_partial_json(text)
        # Should not match (uppercase in name)
        assert result is None or "CamelField" not in (result or {}).get("fields", {})

    def test_multiple_passes_contribute_different_fields(self):
        long_partial = "Объект 1 | 77:01:00100:1 | 100 кв.м. | Москва\nОбъект 2 | 77:01"
        text = (
            '"status": {"value": "defined", "confidence": 0.9},'
            f'"details": {{"value": "{long_partial}'
        )
        result = _salvage_partial_json(text)
        assert result is not None
        fields = result["fields"]

        # Pass 1 recovered status
        assert fields["status"]["value"] == "defined"
        assert fields["status"]["confidence"] == 0.9

        # Pass 2 recovered partial details
        assert "details" in fields
        assert "77:01" in fields["details"]["value"]
        assert fields["details"]["confidence"] == 0.5



        