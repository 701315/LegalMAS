# src/services/result_presentation_read_service.py

"""
Database-backed read-side integration for locale-specific result presentations.

This module:
- resolves the effective output locale using a strict 6-level chain;
- reads locale-specific presentation records in one batch query;
- delegates hash-safe overlay decisions to result_presentation_selection.py.

It does not generate translations, modify CheckResult rows, or update
CheckResultPresentation lifecycle state.
"""

from __future__ import annotations

import warnings
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n.result_locales import (
    get_default_output_locale,
    get_supported_result_locales,
    is_valid_result_locale,
)
from core.result_presentation_content import PRESENTATION_CONTENT_VERSION_V1
from db.repositories.check_result_presentation_repo import (
    CheckResultPresentationRepository,
)
from services.result_presentation_selection import apply_result_presentations
from services.tenant_locale_policy_service import (
    LocalePolicyViolationError,
    validate_locale_for_tenant,
)


async def _normalize_and_validate_fallback(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    value: str | None,
) -> str | None:
    """
    Validate fallback candidate against global registry and tenant policy.

    If invalid or disallowed, returns None (skips to next fallback level)
    without raising errors.
    """
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    try:
        return await validate_locale_for_tenant(db, tenant_id, normalized)
    except LocalePolicyViolationError:
        return None


def get_supported_output_locales() -> set[str]:
    """
    Return supported result output locales used for result presentations.
    """
    return set(get_supported_result_locales())


def get_supported_presentation_locales() -> set[str]:
    """
    [Deprecated] Use get_supported_output_locales instead.
    """
    warnings.warn(
        "get_supported_presentation_locales is deprecated, use get_supported_output_locales",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_supported_output_locales()


async def resolve_output_locale(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    explicit_locale: str | None = None,
    user_default_output_locale: str | None = None,
    user_ui_locale: str | None = None,
    deal_primary_language: str | None = None,
    run_analysis_language: str | None = None,
) -> str:
    """
    Resolve effective output locale with strict 6-level precedence & tenant validation.

    6-Level Chain:
    1. Explicit parameter (ValueError on validation/policy failure).
    2. User default output locale (skips if invalid).
    3. User UI locale (skips if invalid/isolated).
    4. Deal primary language (skips if invalid).
    5. Run analysis language (skips if invalid).
    6. System default output locale (safest fallback).
    """
    # Level 1: Explicit Request (Strict, raises ValueError on violation)
    if explicit_locale is not None:
        normalized_explicit = explicit_locale.strip().lower()
        try:
            return await validate_locale_for_tenant(db, tenant_id, normalized_explicit)
        except LocalePolicyViolationError as exc:
            raise ValueError(str(exc)) from exc

    # Level 2-5 Fallback Chain (Safe skips)
    candidates = [
        user_default_output_locale,
        user_ui_locale,
        deal_primary_language,
        run_analysis_language,
    ]

    for candidate in candidates:
        validated = await _normalize_and_validate_fallback(db, tenant_id, candidate)
        if validated is not None:
            return validated

    # Level 6: System Default (Always safe fallback)
    default_locale = get_default_output_locale()
    validated_default = await _normalize_and_validate_fallback(db, tenant_id, default_locale)
    if validated_default is not None:
        return validated_default

    return "en"


async def resolve_presentation_locale(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    explicit_locale: str | None = None,
    user_default_output_locale: str | None = None,
    user_ui_locale: str | None = None,
    deal_primary_language: str | None = None,
    run_analysis_language: str | None = None,
) -> str:
    """
    [Deprecated] Use resolve_output_locale instead.
    """
    warnings.warn(
        "resolve_presentation_locale is deprecated, use resolve_output_locale",
        DeprecationWarning,
        stacklevel=2,
    )
    return await resolve_output_locale(
        db=db,
        tenant_id=tenant_id,
        explicit_locale=explicit_locale,
        user_default_output_locale=user_default_output_locale,
        user_ui_locale=user_ui_locale,
        deal_primary_language=deal_primary_language,
        run_analysis_language=run_analysis_language,
    )


async def apply_presentations_for_read(
    *,
    session: AsyncSession,
    check_results: Sequence[Mapping[str, Any]],
    requested_locale: str,
    content_version: str = PRESENTATION_CONTENT_VERSION_V1,
) -> list[dict[str, Any]]:
    """
    Overlay locale-specific result presentations onto copied result dictionaries.
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


    