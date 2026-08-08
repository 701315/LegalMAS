"""
Tests for ExtractionLLMDetector universal robustness improvements.

Covers:
- _salvage_partial_json: recovers fields from truncated canonical JSON
- _parse_response: salvage path activates on truncation
- _build_prompt: compact_output tri-state policy
- _normalize_fields: string length cap truncates verbose values
- Budget invariant: context budget uses extraction budget, not detection budget
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


def _make_detector() -> ExtractionLLMDetector:
    client = MagicMock()
    client.is_available.return_value = True
    return ExtractionLLMDetector(client=client)


def _make_extraction_cfg(fields):
    return ExtractionConfig(enabled=True, mode="hybrid", fields=fields)


def _make_string_field(name, *, allowed_values=None, required=False):
    return ExtractionFieldConfig(
        name=name,
        type=ExtractionFieldType.STRING,
        label=f"Label {name}",
        allowed_values=allowed_values or [],
        required=required,
    )


# ─── _salvage_partial_json ────────────────────────────────────────────────────

class TestSalvagePartialJson:
    def test_returns_none_for_empty_string(self):
        assert _salvage_partial_json("") is None

    def test_returns_none_for_valid_unrelated_text(self):
        assert _salvage_partial_json("some random text without JSON") is None

    def test_recovers_single_string_field(self):
        truncated = '{"fields": {"pretrial_status": {"value": "defined", "confidence": 0.9}, "pretrial_details": {"value": "срок 30 дней'
        result = _salvage_partial_json(truncated)
        assert result is not None
        assert "pretrial_status" in result["fields"]
        assert result["fields"]["pretrial_status"]["value"] == "defined"
        assert result["fields"]["pretrial_status"]["confidence"] == pytest.approx(0.9)

    def test_recovers_multiple_complete_fields(self):
        truncated = (
            '{"fields": {"quality_status": {"value": "defined", "confidence": 0.85},'
            '"completeness_status": {"value": "not_defined", "confidence": 0.9},'
            '"warranty_status": {"value": "defined", "confidence": 0.8},'
            '"acceptance_status": {"value": "not_defin'
        )
        result = _salvage_partial_json(truncated)
        assert result is not None
        fields = result["fields"]
        assert "quality_status" in fields
        assert "completeness_status" in fields
        assert "warranty_status" in fields
        assert "acceptance_status" not in fields

    def test_recovers_null_value_field(self):
        text = '"seller_penalty_status": {"value": null, "confidence": 0.5}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["seller_penalty_status"]["value"] is None

    def test_clamps_confidence_to_valid_range(self):
        text = '"some_field": {"value": "пример", "confidence": 1.5}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["some_field"]["confidence"] == pytest.approx(1.0)

    def test_recovers_zero_confidence_field(self):
        text = '"some_field": {"value": "test", "confidence": 0.0}'
        result = _salvage_partial_json(text)
        assert result is not None
        assert result["fields"]["some_field"]["confidence"] == pytest.approx(0.0)

    def test_ignores_invalid_json_value(self):
        text = (
            '"good_field": {"value": "ok", "confidence": 0.8}, '
            '"bad_field": {"value": {broken}, "confidence": 0.9}'
        )
        result = _salvage_partial_json(text)
        assert result is not None
        assert "good_field" in result["fields"]
        assert "bad_field" not in result["fields"]

    def test_returns_none_when_nothing_recoverable(self):
        assert _salvage_partial_json('{"fields": {"incomplete": {"val') is None


# ─── _parse_response ──────────────────────────────────────────────────────────

class TestParseResponseSalvagePath:
    def test_full_valid_json_parsed_normally(self):
        detector = _make_detector()
        data = {"fields": {
            "pretrial_status": {"value": "defined", "confidence": 0.9},
            "pretrial_details": {"value": "30 дней", "confidence": 0.85},
        }}
        result = detector._parse_response(json.dumps(data))
        assert "pretrial_status" in result
        assert result["pretrial_status"]["value"] == "defined"

    def test_truncated_json_triggers_salvage(self):
        detector = _make_detector()
        truncated = (
            '{"fields": {"pretrial_status": {"value": "defined", "confidence": 0.9}, '
            '"pretrial_details": {"value": "30 дней", "confidence": 0.85}, '
            '"claim_response_deadline_status": {"value": "not_defin'
        )
        result = detector._parse_response(truncated)
        assert "pretrial_status" in result
        assert "pretrial_details" in result
        assert "claim_response_deadline_status" not in result

    def test_completely_broken_json_returns_empty(self):
        assert _make_detector()._parse_response("not json at all") == {}

    def test_empty_response_returns_empty(self):
        assert _make_detector()._parse_response("") == {}

    def test_flat_json_accepted_via_tolerant_parser(self):
        flat = json.dumps({"pretrial_status": {"value": "defined", "confidence": 0.9}})
        result = _make_detector()._parse_response(flat)
        assert "pretrial_status" in result


# ─── _build_prompt: compact_output tri-state ─────────────────────────────────

_MOCK_TEMPLATE = "{CHECK_META}\n{FIELDS_SCHEMA}\n{EXAMPLE_JSON}"


class TestBuildPromptCompactnessFooter:
    def test_footer_not_added_with_custom_prompt_auto_mode(self):
        detector = _make_detector()
        cfg = ExtractionConfig(
            enabled=True, mode="hybrid",
            fields=[_make_string_field("f1", allowed_values=["defined", "not_defined"])],
            llm_prompt_extraction="<role>Test</role>\n<context>{context}</context>",
        )
        check = MagicMock()
        check.extraction = cfg
        with patch("engine.detectors.extraction_llm_detector._load_prompt_template", return_value=_MOCK_TEMPLATE):
            prompt = detector._build_prompt(check, cfg, context_text="text")
        assert "краткое резюме" not in prompt
        assert "Не цитируй весь пункт" not in prompt

    def test_footer_added_with_fallback_prompt_auto_mode(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([_make_string_field("f1")])
        check = MagicMock()
        check.name = "Test"
        check.description = "Test description"
        check.extraction = cfg
        with patch("engine.detectors.extraction_llm_detector._load_prompt_template", return_value=_MOCK_TEMPLATE):
            prompt = detector._build_prompt(check, cfg, context_text="text")
        assert "краткое резюме" in prompt

    def test_footer_absent_end_of_prompt_custom_auto(self):
        detector = _make_detector()
        cfg = ExtractionConfig(
            enabled=True, mode="hybrid",
            fields=[_make_string_field("f1")],
            llm_prompt_extraction="<context>{context}</context>",
        )
        check = MagicMock()
        check.extraction = cfg
        with patch("engine.detectors.extraction_llm_detector._load_prompt_template", return_value=_MOCK_TEMPLATE):
            prompt = detector._build_prompt(check, cfg, context_text="text")
        assert "Не добавляй пояснений вне JSON-объекта." not in prompt

    def test_footer_added_compact_output_true_with_custom_prompt(self):
        detector = _make_detector()
        cfg = ExtractionConfig(
            enabled=True, mode="hybrid",
            fields=[_make_string_field("f1")],
            llm_prompt_extraction="<context>{context}</context>",
            compact_output=True,
        )
        check = MagicMock()
        check.extraction = cfg
        with patch("engine.detectors.extraction_llm_detector._load_prompt_template", return_value=_MOCK_TEMPLATE):
            prompt = detector._build_prompt(check, cfg, context_text="text")
        assert "краткое резюме" in prompt
        assert prompt.endswith("Не добавляй пояснений вне JSON-объекта.")

    def test_footer_not_added_compact_output_false(self):
        detector = _make_detector()
        cfg = ExtractionConfig(
            enabled=True, mode="hybrid",
            fields=[_make_string_field("f1")],
            compact_output=False,
        )
        check = MagicMock()
        check.name = "Test"
        check.description = "Test"
        check.extraction = cfg
        with patch("engine.detectors.extraction_llm_detector._load_prompt_template", return_value=_MOCK_TEMPLATE):
            prompt = detector._build_prompt(check, cfg, context_text="text")
        assert "краткое резюме" not in prompt

    def test_footer_added_compact_output_none_no_custom(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([_make_string_field("f1")])
        check = MagicMock()
        check.name = "Test"
        check.description = "Test"
        check.extraction = cfg
        with patch("engine.detectors.extraction_llm_detector._load_prompt_template", return_value=_MOCK_TEMPLATE):
            prompt = detector._build_prompt(check, cfg, context_text="text")
        assert "краткое резюме" in prompt


# ─── _normalize_fields: string length cap ────────────────────────────────────

class TestNormalizeFieldsStringLengthCap:
    def test_short_value_not_truncated(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([_make_string_field("details")])
        result = detector._normalize_fields({"details": {"value": "Краткое резюме.", "confidence": 0.9}}, cfg)
        assert result["details"]["value"] == "Краткое резюме."

    def test_value_exactly_at_limit_not_truncated(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([_make_string_field("details")])
        val = "А" * 500
        result = detector._normalize_fields({"details": {"value": val, "confidence": 0.9}}, cfg)
        assert result["details"]["value"] == val
        assert "…" not in result["details"]["value"]

    def test_long_value_is_truncated(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([_make_string_field("details")])
        result = detector._normalize_fields({"details": {"value": "Длинный текст. " * 100, "confidence": 0.9}}, cfg)
        assert len(result["details"]["value"]) <= 504
        assert result["details"]["value"].endswith("…")

    def test_non_string_value_not_affected_by_cap(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([ExtractionFieldConfig(name="amount", type=ExtractionFieldType.NUMBER, label="Amount")])
        result = detector._normalize_fields({"amount": {"value": 1000000, "confidence": 0.9}}, cfg)
        assert result["amount"]["value"] == 1000000

    def test_truncation_does_not_affect_confidence(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([_make_string_field("details")])
        result = detector._normalize_fields({"details": {"value": "Текст. " * 200, "confidence": 0.85}}, cfg)
        assert result["details"]["value"].endswith("…")
        assert result["details"]["confidence"] == pytest.approx(0.85)

    def test_unknown_fields_not_in_schema_are_ignored(self):
        detector = _make_detector()
        cfg = _make_extraction_cfg([_make_string_field("known_field")])
        result = detector._normalize_fields(
            {"known_field": {"value": "ok", "confidence": 0.9}, "unknown": {"value": "x", "confidence": 0.5}},
            cfg
        )
        assert "known_field" in result
        assert "unknown" not in result


# ─── Budget Invariant ─────────────────────────────────────────────────────────

class TestBudgetInvariant:
    def test_context_budget_uses_extraction_default_not_detection_default(self, monkeypatch):
        from engine.detectors import extraction_llm_detector as mod

        monkeypatch.setattr(mod.settings, "LLM_CONTEXT_LIMIT", 4000)
        monkeypatch.setattr(mod.settings, "LLM_MAX_TOKENS", 100)
        monkeypatch.setattr(mod.settings, "LLM_EXTRACTION_MAX_TOKENS", 1000)
        monkeypatch.setattr(mod.settings, "LLM_SAFETY_MARGIN_TOKENS", 500)

        detector = _make_detector()
        detector.client.call_with_retries.return_value = (
            None, {"error_type": "test", "error_message": "test", "llm_attempts": 1}
        )

        cfg = ExtractionConfig(
            enabled=True, mode="hybrid",
            fields=[_make_string_field("f1")],
            llm_prompt_extraction="<context>{context}</context>",
        )
        check = MagicMock()
        check.id = "budget_test"
        check.name = "Budget Test"
        check.description = "Test"
        check.extraction = cfg

        with patch(
            "engine.detectors.extraction_llm_detector._load_prompt_template",
            return_value=_MOCK_TEMPLATE,
        ), patch("engine.detectors.extraction_llm_detector.logger") as mock_logger:
            detector.extract_with_telemetry(check, "слово " * 10000)

        truncation_warnings = [
            c for c in mock_logger.warning.call_args_list
            if c.args and "контекст обрезан" in c.args[0]
        ]
        assert truncation_warnings
        assert truncation_warnings[0].kwargs["extraction_max_tokens"] == 1000
        call_kwargs = detector.client.call_with_retries.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1000

    def test_context_budget_uses_yaml_override(self, monkeypatch):
        from engine.detectors import extraction_llm_detector as mod

        monkeypatch.setattr(mod.settings, "LLM_CONTEXT_LIMIT", 4000)
        monkeypatch.setattr(mod.settings, "LLM_MAX_TOKENS", 100)
        monkeypatch.setattr(mod.settings, "LLM_EXTRACTION_MAX_TOKENS", 1000)
        monkeypatch.setattr(mod.settings, "LLM_SAFETY_MARGIN_TOKENS", 500)

        detector = _make_detector()
        detector.client.call_with_retries.return_value = (
            None, {"error_type": "test", "error_message": "test", "llm_attempts": 1}
        )

        cfg = ExtractionConfig(
            enabled=True, mode="hybrid",
            fields=[_make_string_field("f1")],
            llm_prompt_extraction="<context>{context}</context>",
            llm_max_tokens=2500,
        )
        check = MagicMock()
        check.id = "yaml_override_test"
        check.name = "YAML Override Test"
        check.description = "Test"
        check.extraction = cfg

        with patch(
            "engine.detectors.extraction_llm_detector._load_prompt_template",
            return_value=_MOCK_TEMPLATE,
        ), patch("engine.detectors.extraction_llm_detector.logger") as mock_logger:
            detector.extract_with_telemetry(check, "слово " * 10000)

        truncation_warnings = [
            c for c in mock_logger.warning.call_args_list
            if c.args and "контекст обрезан" in c.args[0]
        ]
        assert truncation_warnings
        assert truncation_warnings[0].kwargs["extraction_max_tokens"] == 2500
        call_kwargs = detector.client.call_with_retries.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2500
