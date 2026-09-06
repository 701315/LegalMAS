"""
Database-backed read-side integration for locale-specific result presentations.

This module:
- resolves the effective presentation locale;
- reads locale-specific presentation records in one batch query;
- delegates hash-safe overlay decisions to result_presentation_selection.py.

It does not generate translations, modify CheckResult rows, or update
CheckResultPresentation lifecycle state.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n.ui_locales import (
    get_default_ui_locale,
    get_supported_ui_locales,
    is_valid_ui_locale,
)
from core.result_presentation_content import PRESENTATION_CONTENT_VERSION_V1
from db.repositories.check_result_presentation_repo import (
    CheckResultPresentationRepository,
)
from services.result_presentation_selection import apply_result_presentations


def _normalize_supported_locale(value: str | None) -> str | None:
    """
    Normalize one locale candidate and return it only when it is supported.

    Invalid persisted values are intentionally ignored on fallback paths:
    old JWTs or legacy Deal.primary_language values must not break review reads.
    """
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    if not is_valid_ui_locale(normalized):
        return None

    return normalized


def get_supported_presentation_locales() -> set[str]:
    """
    Return supported UI locales used for result presentations.
    """
    return set(get_supported_ui_locales())


def resolve_presentation_locale(
    *,
    explicit_locale: str | None,
    user_ui_locale: str | None,
    deal_primary_language: str | None,
) -> str:
    """
    Resolve locale with deterministic precedence.

    Precedence:
    1. explicit query parameter;
    2. CurrentUser.ui_locale;
    3. Deal.primary_language;
    4. configured default UI locale.

    Invalid explicit input is a client error. Invalid persisted fallbacks are
    skipped, because they can originate from legacy records or expired tokens.
    """
    if explicit_locale is not None:
        normalized_explicit = _normalize_supported_locale(explicit_locale)
        if normalized_explicit is None:
            supported = ", ".join(sorted(get_supported_presentation_locales()))
            raise ValueError(
                "presentation_locale must be one of the supported locales: "
                f"{supported}"
            )
        return normalized_explicit

    for candidate in (user_ui_locale, deal_primary_language):
        normalized_candidate = _normalize_supported_locale(candidate)
        if normalized_candidate is not None:
            return normalized_candidate

    default_locale = _normalize_supported_locale(get_default_ui_locale())
    if default_locale is not None:
        return default_locale

    return "en"


async def apply_presentations_for_read(
    *,
    session: AsyncSession,
    check_results: Sequence[Mapping[str, Any]],
    requested_locale: str,
    content_version: str = PRESENTATION_CONTENT_VERSION_V1,
) -> list[dict[str, Any]]:
    """
    Overlay locale-specific result presentations onto copied result dictionaries.

    The repository query is batch-based: one query for all canonical result IDs
    in the response. apply_result_presentations() still enforces source hash,
    locale, content version, and allowed lifecycle state before localized content
    can replace canonical content.
    """
    result_ids: list[uuid.UUID] = []

    for row in check_results:
        raw_id = row.get("id")
        if raw_id is None:
            continue

        try:
            result_ids.append(uuid.UUID(str(raw_id)))
        except (TypeError, ValueError, AttributeError):
            continue

    presentation_repo = CheckResultPresentationRepository(session)

    presentations_by_uuid = (
        await presentation_repo.list_by_result_ids_and_locale(
            check_result_ids=result_ids,
            locale=requested_locale,
            content_version=content_version,
        )
    )

    presentations_by_result_id = {
        str(result_id): presentation
        for result_id, presentation in presentations_by_uuid.items()
    }

    return apply_result_presentations(
        check_results=check_results,
        presentations_by_result_id=presentations_by_result_id,
        requested_locale=requested_locale,
        content_version=content_version,
    )
