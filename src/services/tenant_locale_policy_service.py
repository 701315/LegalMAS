# src/services/tenant_locale_policy_service.py

"""
Tenant locale policy validation service.

Enforces enterprise-level localization constraints when resolving
or requesting result presentation locales.

Invariant #5: This service operates on the OUTPUT locale axis,
completely independent from UI locales.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n.result_locales import (
    get_supported_result_locales,
    is_valid_result_locale,
)
from db.repositories.tenant_locale_policy_repo import TenantLocalePolicyRepository


class LocalePolicyViolationError(ValueError):
    """Raised when a requested locale violates tenant policy."""

    def __init__(self, message: str, *, reason: str, locale: str | None = None):
        super().__init__(message)
        self.reason = reason
        self.locale = locale


async def validate_locale_for_tenant(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    locale: str,
) -> str:
    """
    Validate that *locale* is allowed for the given tenant.

    Resolution order:
    1. Check against global result_locales.json registry.
    2. Fetch TenantResultLocalePolicy (if any).
    3. If policy exists and restrict_to_allowed is True,
       check locale against allowed_locales.

    Returns the normalized locale string on success.
    Raises LocalePolicyViolationError on failure.
    """
    normalized = locale.strip().lower()

    # Step 1: Global registry check
    if not is_valid_result_locale(normalized):
        supported = ", ".join(sorted(get_supported_result_locales()))
        raise LocalePolicyViolationError(
            f"Locale '{normalized}' is not supported. "
            f"Supported locales: {supported}",
            reason="unsupported_locale",
            locale=normalized,
        )

    # Step 2: Tenant policy check
    repo = TenantLocalePolicyRepository(db)
    policy = await repo.get_by_tenant_id(tenant_id)

    if policy is None:
        # No policy configured → all registry locales are allowed
        return normalized

    # Step 3: Policy enforcement
    if policy.restrict_to_allowed and policy.allowed_locales:
        allowed = {loc.strip().lower() for loc in policy.allowed_locales}
        if normalized not in allowed:
            raise LocalePolicyViolationError(
                f"Locale '{normalized}' is not allowed by tenant policy. "
                f"Allowed locales: {', '.join(sorted(allowed))}",
                reason="tenant_policy_restriction",
                locale=normalized,
            )

    return normalized


async def is_translation_allowed(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> bool:
    """
    Check whether LLM-based translation is enabled for the tenant.

    Returns True if:
    - No policy is configured (default: translations allowed), or
    - Policy exists and is_translation_enabled is True.
    """
    repo = TenantLocalePolicyRepository(db)
    policy = await repo.get_by_tenant_id(tenant_id)

    if policy is None:
        return True

    return policy.is_translation_enabled


    