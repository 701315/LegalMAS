"""
Tests for ExtractionLLMDetector universal robustness improvements.

Covers:
- _salvage_partial_json: recovers fields from truncated canonical JSON
- _parse_response: salvage path activates on truncation
- _build_prompt: compactness footer is always appended
- _normalize_fields: string length cap truncates verbose values

All tests are universal — not specific to any document, language, or check type.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from engine.detectors.extraction_llm_detector import (
    ExtractionLLMDetector,
    _salvage_partial_json,
)
from engine.playbook.models import (
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_detector() -> ExtractionLLMDetector:
    client = MagicMock()
    client.is_available.return_value = True
    return ExtractionLLMDetector(client=client)


def _make_extraction_cfg(fields: list[ExtractionFieldConfig]) -> ExtractionConfig:
    return ExtractionConfig(enabled=True, mode="hybrid", fields=fields)


def _make_string_field(
    name: str,
    *,
    allowed_values: list[str] | None = None,
    required: bool = False,
) -> ExtractionFieldConfig:
    return ExtractionFieldConfig(
        name=name,
        type=ExtractionFieldType.STRING,
        label=f"Label {name}",
        allowed_values=allowed_values or [],
        required=required,
    )


# ─── _salvage_partial_json ────────────────────────────────────────────────────


class TestSalvagePartialJson:
    def test_returns_none_for_empty_string(self) -> None:
        assert _salvage_partial_json("") is None

    def test_returns_none_for_valid_unrelated_text(self) -> None:
        assert _salvage_partial_json("some random text without JSON") is None

    def test_recovers_single_string_field(self) -> None:
        truncated = """
        {
          "fields": {
            "pretrial_status": {"value": "defined", "confidence": 0.9},
            "pretrial_details": {"value": "срок 30 дней
        """
        result = _salvage_partial_json(truncated)
        assert result is not None
        assert "fields" in result
        fields = result["fields"]
        assert "pretrial_status" in fields
        assert fields["pretrial_status"]["value"] == "defined"
        assert fields["pretrial_status"]["confidence"] == pytest.approx(0.9)

    def test_recovers_multiple_complete_fields(self) -> None:
        truncated = """
        {
          "fields": {
            "quality_status": {"value": "defined", "confidence": 0.85},
            "completeness_status": {"value": "not_defined", "confidence": 0.9},
            "warranty_status": {"value": "defined", "confidence": 0.8},
            "acceptance_status": {"value": "not_defined", "confidence": 0.7
        """
        result = _salvage_partial_json(truncated)
        assert result is not None
        fields = result["fields"]

        assert "quality_status" in fields
        assert "completeness_status" in fields
        assert "warranty_status" in fields
        assert "acceptance_status" not in fields  # incomplete — not recovered

    def test_recovers_null_value_field(self) -> None:
        text = '"seller_penalty_status": {"value": null, "confidence": 0.5}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["seller_penalty_status"]["value"] is None

    def test_clamps_confidence_to_valid_range(self) -> None:
        text = '"some_field": {"value": "пример", "confidence": 1.5}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["some_field"]["confidence"] == pytest.approx(1.0)

    def test_recovers_zero_confidence_field(self) -> None:
        text = '"some_field": {"value": "test", "confidence": 0.0}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["some_field"]["confidence"] == pytest.approx(0.0)

    def test_ignores_invalid_json_value(self) -> None:
        # A field with a broken value that json.loads can't parse
        # (hypothetical edge case — shouldn't appear in practice)
        text = (
            '"good_field": {"value": "ok", "confidence": 0.8}, '
            '"bad_field": {"value": {broken}, "confidence": 0.9}'
        )
        result = _salvage_partial_json(text)
        # good_field should be recovered, bad_field skipped
        assert result is not None
        assert "good_field" in result["fields"]
        assert "bad_field" not in result["fields"]

    def test_returns_none_when_nothing_recoverable(self) -> None:
        truncated = '{"fields": {"incomplete": {"val'
        result = _salvage_partial_json(truncated)
        assert result is None


# ─── _parse_response: salvage path ───────────────────────────────────────────


class TestParseResponseSalvagePath:
    def test_full_valid_json_parsed_normally(self) -> None:
        detector = _make_detector()

        data = {
            "fields": {
                "pretrial_status": {"value": "defined", "confidence": 0.9},
                "pretrial_details": {"value": "30 дней", "confidence": 0.85},
            }
        }
        result = detector._parse_response(json.dumps(data))

        assert "pretrial_status" in result
        assert result["pretrial_status"]["value"] == "defined"

    def test_truncated_json_triggers_salvage(self) -> None:
        detector = _make_detector()

        # Well-formed beginning, truncated at the end
        truncated = (
            '{"fields": {"pretrial_status": {"value": "defined", "confidence": 0.9}, '
            '"pretrial_details": {"value": "30 дней", "confidence": 0.85}, '
            '"claim_response_deadline_status": {"value": "not_defin'
        )

        result = detector._parse_response(truncated)

        # Two complete fields should be salvaged
        assert "pretrial_status" in result
        assert "pretrial_details" in result
        # Incomplete field should not be present
        assert "claim_response_deadline_status" not in result

    def test_completely_broken_json_returns_empty(self) -> None:
        detector = _make_detector()

        result = detector._parse_response("not json at all")
        assert result == {}

    def test_empty_response_returns_empty(self) -> None:
        detector = _make_detector()

        result = detector._parse_response("")
        assert result == {}

    def test_flat_json_accepted_via_tolerant_parser(self) -> None:
        detector = _make_detector()

        # Non-canonical flat format — accepted via tolerant parser
        flat = json.dumps(
            {
                "pretrial_status": {"value": "defined", "confidence": 0.9},
            }
        )
        result = detector._parse_response(flat)
        assert "pretrial_status" in result


# ─── _build_prompt: compactness footer ───────────────────────────────────────


class TestBuildPromptCompactnessFooter:
    def test_compactness_footer_is_appended_with_custom_prompt(self) -> None:
        detector = _make_detector()

        field = _make_string_field("pretrial_status", allowed_values=["defined", "not_defined"])
        cfg = _make_extraction_cfg([field])
        cfg = ExtractionConfig(
            enabled=True,
            mode="hybrid",
            fields=[field],
            llm_prompt_extraction="<role>Test</role>\n<context>{context}</context>",
        )

        check = MagicMock()
        check.extraction = cfg

        with patch(
            "engine.detectors.extraction_llm_detector._load_prompt_template",
            return_value="{CHECK_META}\n{FIELDS_SCHEMA}\n{EXAMPLE_JSON}",
        ):
            prompt = detector._build_prompt(check, cfg, context_text="Some contract text")

        assert "краткое резюме" in prompt
        assert "Не цитируй весь пункт" in prompt
        assert "Не добавляй пояснений вне JSON-объекта" in prompt

    def test_compactness_footer_is_appended_with_fallback_prompt(self) -> None:
        detector = _make_detector()

        field = _make_string_field("some_field")
        cfg = _make_extraction_cfg([field])

        check = MagicMock()
        check.name = "Test Check"
        check.description = "Test description"
        check.extraction = cfg

        with patch(
            "engine.detectors.extraction_llm_detector._load_prompt_template",
            return_value="{CHECK_META}\n{FIELDS_SCHEMA}\n{EXAMPLE_JSON}",
        ):
            prompt = detector._build_prompt(check, cfg, context_text="Some text")

        assert "краткое резюме" in prompt

    def test_compactness_footer_is_at_end_of_prompt(self) -> None:
        detector = _make_detector()

        field = _make_string_field("some_field")
        cfg = ExtractionConfig(
            enabled=True,
            mode="hybrid",
            fields=[field],
            llm_prompt_extraction="<context>{context}</context>",
        )
        check = MagicMock()
        check.extraction = cfg

        with patch(
            "engine.detectors.extraction_llm_detector._load_prompt_template",
            return_value="{CHECK_META}\n{FIELDS_SCHEMA}\n{EXAMPLE_JSON}",
        ):
            prompt = detector._build_prompt(check, cfg, context_text="text")

        # Footer should be the last meaningful content
        assert prompt.endswith("Не добавляй пояснений вне JSON-объекта.")


# ─── _normalize_fields: string length cap ────────────────────────────────────


class TestNormalizeFieldsStringLengthCap:
    def test_short_value_not_truncated(self) -> None:
        detector = _make_detector()

        field = _make_string_field("details")
        cfg = _make_extraction_cfg([field])

        raw = {"details": {"value": "Краткое резюме.", "confidence": 0.9}}
        result = detector._normalize_fields(raw, cfg)

        assert result["details"]["value"] == "Краткое резюме."

    def test_value_exactly_at_limit_not_truncated(self) -> None:
        detector = _make_detector()

        field = _make_string_field("details")
        cfg = _make_extraction_cfg([field])

        value_at_limit = "А" * 500
        raw = {"details": {"value": value_at_limit, "confidence": 0.9}}
        result = detector._normalize_fields(raw, cfg)

        assert result["details"]["value"] == value_at_limit
        assert "…" not in result["details"]["value"]

    def test_long_value_is_truncated(self) -> None:
        detector = _make_detector()

        field = _make_string_field("details")
        cfg = _make_extraction_cfg([field])

        long_value = "Длинный текст. " * 100  # well over 500 chars
        raw = {"details": {"value": long_value, "confidence": 0.9}}
        result = detector._normalize_fields(raw, cfg)

        assert len(result["details"]["value"]) <= 504  # 500 chars + "…"
        assert result["details"]["value"].endswith("…")

    def test_non_string_value_not_affected_by_cap(self) -> None:
        detector = _make_detector()

        field = ExtractionFieldConfig(
            name="amount",
            type=ExtractionFieldType.NUMBER,
            label="Amount",
        )
        cfg = _make_extraction_cfg([field])

        raw = {"amount": {"value": 1000000, "confidence": 0.9}}
        result = detector._normalize_fields(raw, cfg)

        assert result["amount"]["value"] == 1000000

    def test_fields_with_allowed_values_not_truncated(self) -> None:
        detector = _make_detector()

        field = _make_string_field(
            "status",
            allowed_values=["defined", "not_defined"],
        )
        cfg = _make_extraction_cfg([field])

        raw = {"status": {"value": "defined", "confidence": 0.9}}
        result = detector._normalize_fields(raw, cfg)

        # Allowed values are short — cap doesn't fire, value stays canonical
        assert result["status"]["value"] == "defined"

    def test_truncation_does_not_affect_confidence(self) -> None:
        detector = _make_detector()

        field = _make_string_field("details")
        cfg = _make_extraction_cfg([field])

        long_value = "Текст. " * 200
        raw = {"details": {"value": long_value, "confidence": 0.85}}
        result = detector._normalize_fields(raw, cfg)

        assert result["details"]["value"].endswith("…")
        assert result["details"]["confidence"] == pytest.approx(0.85)

    def test_unknown_fields_not_in_schema_are_ignored(self) -> None:
        detector = _make_detector()

        field = _make_string_field("known_field")
        cfg = _make_extraction_cfg([field])

        raw = {
            "known_field": {"value": "ok", "confidence": 0.9},
            "unknown_extra_field": {"value": "ignored", "confidence": 0.5},
        }
        result = detector._normalize_fields(raw, cfg)

        assert "known_field" in result
        assert "unknown_extra_field" not in result



        