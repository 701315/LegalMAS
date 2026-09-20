"""
Unit tests for glossary-aware prompt builder (Sprint 3.4).
"""

from __future__ import annotations

from services.result_presentation_translation_service import (
    build_result_presentation_translation_prompt,
    RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION,
)


class TestBuildResultPresentationTranslationPrompt:
    """Test prompt building with and without glossary injection."""

    def test_prompt_without_glossary_unchanged(self) -> None:
        """Verify backward compatibility: no glossary = no terminology section."""
        prompt = build_result_presentation_translation_prompt(
            source_locale="ru",
            target_locale="en",
            check_name="Change of Control",
            display_text="Detected change of control provision.",
            review_message=None,
            glossary_terms=None,
        )

        assert "TERMINOLOGY CONSTRAINTS" not in prompt
        assert "Change of Control" in prompt
        assert f"Prompt version: {RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION}" in prompt

    def test_prompt_with_empty_glossary_unchanged(self) -> None:
        """Empty glossary dict = no terminology section."""
        prompt = build_result_presentation_translation_prompt(
            source_locale="ru",
            target_locale="en",
            check_name="Test Check",
            display_text=None,
            review_message=None,
            glossary_terms={},
        )

        assert "TERMINOLOGY CONSTRAINTS" not in prompt

    def test_prompt_with_glossary_injects_terms(self) -> None:
        """Non-empty glossary injects terminology section with exact format."""
        glossary = {
            "неустойка": "contractual penalty",
            "устав": "charter",
        }

        prompt = build_result_presentation_translation_prompt(
            source_locale="ru",
            target_locale="en",
            check_name="Test Check",
            display_text=None,
            review_message=None,
            glossary_terms=glossary,
        )

        assert "TERMINOLOGY CONSTRAINTS — Use these exact translations:" in prompt
        assert '"неустойка" → "contractual penalty"' in prompt
        assert '"устав" → "charter"' in prompt
        assert "If a source term appears in the input, you MUST use the corresponding target term above." in prompt
        assert "Do not use synonyms, paraphrases, or alternative translations for these terms." in prompt

    def test_prompt_glossary_terms_sorted_alphabetically(self) -> None:
        """Glossary terms appear in sorted order for deterministic prompts."""
        glossary = {
            "задаток": "earnest money",
            "неустойка": "contractual penalty",
            "устав": "charter",
        }

        prompt = build_result_presentation_translation_prompt(
            source_locale="ru",
            target_locale="en",
            check_name="Test",
            display_text=None,
            review_message=None,
            glossary_terms=glossary,
        )

        # Find positions of terms in prompt
        pos_zadatok = prompt.find('"задаток"')
        pos_neustoyka = prompt.find('"неустойка"')
        # Alphabetically: задаток < неустойка < устав

        assert pos_zadatok < pos_neustoyka, "Glossary terms must be sorted alphabetically"
