from __future__ import annotations

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
