# tests/unit/core/test_result_locales.py

"""Unit tests for result output locale registry."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.i18n.result_locales import (
    get_default_output_locale,
    get_default_output_policy,
    get_supported_result_locales,
    get_supported_source_locales,
    is_translation_pair_supported,
    is_valid_result_locale,
    get_all_result_locale_details,
    _load_config,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset module-level cache before each test."""
    import core.i18n.result_locales as mod

    mod._cached_config = None
    yield
    mod._cached_config = None


class TestGetDefaultOutputLocale:
    def test_returns_en_from_real_config(self):
        assert get_default_output_locale() == "en"

    def test_fallback_when_file_missing(self):
        import core.i18n.result_locales as mod

        mod._cached_config = None
        with patch.object(mod, "SHARED_CONFIG_PATH", Path("/nonexistent")):
            mod._cached_config = None
            assert get_default_output_locale() == "en"


class TestGetDefaultOutputPolicy:
    def test_returns_match_analysis_language(self):
        assert get_default_output_policy() == "match_analysis_language"


class TestGetSupportedResultLocales:
    def test_contains_en_and_ru(self):
        locales = get_supported_result_locales()
        assert "en" in locales
        assert "ru" in locales

    def test_excludes_disabled(self):
        import core.i18n.result_locales as mod

        mod._cached_config = {
            "locales": [
                {"code": "en", "status": "supported"},
                {"code": "de", "status": "disabled"},
            ]
        }
        assert "de" not in get_supported_result_locales()

    def test_includes_beta(self):
        import core.i18n.result_locales as mod

        mod._cached_config = {
            "locales": [
                {"code": "en", "status": "supported"},
                {"code": "de", "status": "beta"},
            ]
        }
        assert "de" in get_supported_result_locales()


class TestIsValidResultLocale:
    def test_none_is_valid(self):
        assert is_valid_result_locale(None) is True

    def test_empty_is_valid(self):
        assert is_valid_result_locale("") is True

    def test_supported_is_valid(self):
        assert is_valid_result_locale("en") is True
        assert is_valid_result_locale("ru") is True

    def test_unsupported_is_invalid(self):
        assert is_valid_result_locale("de") is False

    def test_case_insensitive(self):
        assert is_valid_result_locale("EN") is True
        assert is_valid_result_locale("Ru") is True


class TestGetSupportedSourceLocales:
    def test_en_supports_ru_source(self):
        sources = get_supported_source_locales("en")
        assert "ru" in sources

    def test_ru_supports_en_source(self):
        sources = get_supported_source_locales("ru")
        assert "en" in sources

    def test_unknown_target_returns_empty(self):
        assert get_supported_source_locales("xx") == set()


class TestIsTranslationPairSupported:
    def test_ru_to_en(self):
        assert is_translation_pair_supported("ru", "en") is True

    def test_en_to_ru(self):
        assert is_translation_pair_supported("en", "ru") is True

    def test_empty_source(self):
        assert is_translation_pair_supported("", "en") is False

    def test_unknown_pair(self):
        assert is_translation_pair_supported("de", "en") is False


class TestGetAllResultLocaleDetails:
    def test_returns_list(self):
        details = get_all_result_locale_details()
        assert isinstance(details, list)
        assert len(details) >= 2

    def test_has_translation_field(self):
        details = get_all_result_locale_details()
        for d in details:
            assert "translation" in d
            assert "supported_source_locales" in d["translation"]


            