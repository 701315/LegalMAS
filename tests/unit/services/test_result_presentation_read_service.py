# tests/unit/services/test_result_presentation_read_service.py

from __future__ import annotations

from unittest.mock import patch
import pytest

from services.result_presentation_read_service import (
    resolve_presentation_locale,
)


def test_explicit_locale_has_highest_priority() -> None:
    assert resolve_presentation_locale(
        explicit_locale="ru",
        user_ui_locale="en",
        deal_primary_language="en",
    ) == "ru"


def test_explicit_locale_is_normalized() -> None:
    assert resolve_presentation_locale(
        explicit_locale=" RU ",
        user_ui_locale="en",
        deal_primary_language="en",
    ) == "ru"


def test_user_ui_locale_beats_deal_primary_language() -> None:
    assert resolve_presentation_locale(
        explicit_locale=None,
        user_ui_locale="ru",
        deal_primary_language="en",
    ) == "ru"


def test_deal_primary_language_is_used_when_user_locale_absent() -> None:
    assert resolve_presentation_locale(
        explicit_locale=None,
        user_ui_locale=None,
        deal_primary_language="ru",
    ) == "ru"


def test_invalid_persisted_locale_is_ignored() -> None:
    assert resolve_presentation_locale(
        explicit_locale=None,
        user_ui_locale="unsupported-locale",
        deal_primary_language="ru",
    ) == "ru"


def test_invalid_explicit_locale_is_rejected() -> None:
    with pytest.raises(ValueError, match="presentation_locale"):
        resolve_presentation_locale(
            explicit_locale="unsupported-locale",
            user_ui_locale="en",
            deal_primary_language="ru",
        )


def test_default_locale_is_used_when_no_candidate_exists() -> None:
    assert resolve_presentation_locale(
        explicit_locale=None,
        user_ui_locale=None,
        deal_primary_language=None,
    ) == "en"


def test_invariant_5_axis_separation_de_ui_skipped_for_results() -> None:
    """
    If 'de' is supported as a UI locale but NOT as a result locale,
    it must be ignored in the resolution fallback chain for results.
    """
    # Будем мокать реестр результатов так, что 'de' НЕ поддерживается,
    # а поддерживаются только 'en' и 'ru'.
    with patch("services.result_presentation_read_service.is_valid_result_locale") as mock_val, \
         patch("services.result_presentation_read_service.get_supported_result_locales", return_value={"en", "ru"}), \
         patch("services.result_presentation_read_service.get_default_output_locale", return_value="en"):
        
        # Симулируем, что "de" невалиден для результатов, а "ru" и "en" валидны
        mock_val.side_effect = lambda loc: loc in ("en", "ru")

        # Передаем 'de' как ui_locale (например, интерфейс пользователя на немецком).
        # Резолвер должен отбросить 'de' как невалидную локаль результатов
        # и упасть на 'ru' (deal_primary_language).
        resolved = resolve_presentation_locale(
            explicit_locale=None,
            user_ui_locale="de",
            deal_primary_language="ru",
        )
        assert resolved == "ru"


        