"""
Unit tests for post-translation validator (Sprint 3.5).
"""

from __future__ import annotations

import pytest
from engine.localization.validator import (
    validate_translation_response,
    GlossaryComplianceError,
    ValidationResult,
)


class TestValidateTranslationResponse:
    """Test core validation logic."""

    def test_valid_response_passes(self) -> None:
        """Valid JSON with correct keys passes validation."""
        response = '{"localized_check_name": "Test", "display_text": null, "review_message": null}'

        result = validate_translation_response(
            response_text=response,
            expected_keys={"localized_check_name", "display_text", "review_message"},
            glossary_terms=None,
            source_text=None,
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.glossary_violations) == 0

    def test_empty_response_raises(self) -> None:
        """Empty response raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            validate_translation_response(
                response_text="",
                expected_keys={"localized_check_name"},
            )

    def test_truncated_response_raises(self) -> None:
        """Response without closing brace raises ValueError (truncation detected BEFORE JSON parse)."""
        # No closing brace - truncation check catches this first
        with pytest.raises(ValueError, match="truncated"):
            validate_translation_response(
                response_text='{"localized_check_name": "Test"',
                expected_keys={"localized_check_name"},
            )

    def test_invalid_json_raises(self) -> None:
        """Malformed JSON (with closing brace) raises ValueError."""
        # Has closing brace but invalid JSON syntax - JSON parse catches this
        with pytest.raises(ValueError, match="not valid JSON"):
            validate_translation_response(
                response_text='{"localized_check_name": Test}',
                expected_keys={"localized_check_name"},
            )

    def test_extra_keys_hallucination_raises(self) -> None:
        """Extra keys in response raise ValueError (hallucination)."""
        response = '{"localized_check_name": "Test", "display_text": null, "review_message": null, "extra_key": "bad"}'

        with pytest.raises(ValueError, match="extra keys"):
            validate_translation_response(
                response_text=response,
                expected_keys={"localized_check_name", "display_text", "review_message"},
            )

    def test_missing_keys_raises(self) -> None:
        """Missing required keys raise ValueError."""
        response = '{"localized_check_name": "Test"}'

        with pytest.raises(ValueError, match="missing keys"):
            validate_translation_response(
                response_text=response,
                expected_keys={"localized_check_name", "display_text", "review_message"},
            )


class TestGlossaryCompliance:
    """Test glossary terminology validation."""

    def test_glossary_compliance_passes(self) -> None:
        """Translation using correct glossary terms passes."""
        response = '{"localized_check_name": "Contractual penalty detected", "display_text": null, "review_message": null}'
        source = "Обнаружена неустойка"

        result = validate_translation_response(
            response_text=response,
            expected_keys={"localized_check_name", "display_text", "review_message"},
            glossary_terms={"неустойка": "contractual penalty"},
            source_text=source,
        )

        assert result.is_valid is True
        assert len(result.glossary_violations) == 0

    def test_glossary_violation_detected(self) -> None:
        """Missing glossary term in translation raises GlossaryComplianceError."""
        response = '{"localized_check_name": "Fine detected", "display_text": null, "review_message": null}'
        source = "Обнаружена неустойка"

        result = validate_translation_response(
            response_text=response,
            expected_keys={"localized_check_name", "display_text", "review_message"},
            glossary_terms={"неустойка": "contractual penalty"},
            source_text=source,
        )

        assert result.is_valid is False
        assert len(result.glossary_violations) == 1
        violation = result.glossary_violations[0]
        assert violation.source_term == "неустойка"
        assert violation.expected_target == "contractual penalty"

    def test_glossary_not_checked_if_no_source_text(self) -> None:
        """Glossary check is skipped without source_text."""
        response = '{"localized_check_name": "Test", "display_text": null, "review_message": null}'

        result = validate_translation_response(
            response_text=response,
            expected_keys={"localized_check_name", "display_text", "review_message"},
            glossary_terms={"неустойка": "contractual penalty"},
            source_text=None,
        )

        # No violations detected because source_text is None
        assert len(result.glossary_violations) == 0

    def test_glossary_not_checked_if_no_glossary(self) -> None:
        """Glossary check is skipped without glossary_terms."""
        response = '{"localized_check_name": "Test", "display_text": null, "review_message": null}'
        source = "Обнаружена неустойка"

        result = validate_translation_response(
            response_text=response,
            expected_keys={"localized_check_name", "display_text", "review_message"},
            glossary_terms=None,
            source_text=source,
        )

        assert len(result.glossary_violations) == 0
