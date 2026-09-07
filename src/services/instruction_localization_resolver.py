"""
Instruction Localization Resolver (Sprint 4.4).

Resolves localized labels for static DD Grid entities (enum values,
system headers, column labels) from the database.

Resolution priority:
  1. Tenant-specific override  (tenant_id = :tid, is_active = true)
  2. Platform-wide default     (tenant_id IS NULL, is_active = true)
  3. Caller-provided fallback  (canonical from YAML or hardcoded default)

Performance:
  - Single SELECT per (tenant_id, locale) pair on first access.
  - All subsequent lookups are O(1) dict hits.
  - Designed to be instantiated once per API request and passed
    into the DD Grid builder as a plain dict.

Scalability:
  - Adding a new language: INSERT rows with new locale → no code change.
  - Tenant override: INSERT row with tenant_id → takes precedence.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.instruction_presentation_localization import (
    InstructionPresentationLocalization,
)

logger = get_logger(__name__)


class InstructionLocalizationResolver:
    """
    Async resolver with per-request caching.

    Usage in deal_review_service.py:
        resolver = InstructionLocalizationResolver(
            db=session, tenant_id=run.tenant_id, locale="en"
        )
        loc_map = await resolver.load_all()
        grid = build_dd_grid_v1_response(..., localization_map=loc_map)
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        tenant_id: uuid.UUID | None,
        locale: str,
    ) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._locale = locale.strip().lower()
        self._cache: dict[str, str] | None = None

    async def load_all(self) -> dict[str, str]:
        """
        Load all active localizations for (tenant, locale) into memory.

        Returns a flat dict: {instruction_key: label}.
        Tenant-specific entries override platform-wide ones.
        """
        if self._cache is not None:
            return self._cache

        # Build query: platform-wide OR tenant-specific
        conditions = [
            InstructionPresentationLocalization.locale == self._locale,
            InstructionPresentationLocalization.is_active.is_(True),
        ]

        if self._tenant_id is not None:
            conditions.append(
                or_(
                    InstructionPresentationLocalization.tenant_id.is_(None),
                    InstructionPresentationLocalization.tenant_id == self._tenant_id,
                )
            )
        else:
            conditions.append(
                InstructionPresentationLocalization.tenant_id.is_(None)
            )

        stmt = select(InstructionPresentationLocalization).where(
            and_(*conditions)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        # Two-pass merge: platform-wide first, then tenant overrides
        platform: dict[str, str] = {}
        tenant: dict[str, str] = {}

        for row in rows:
            if row.tenant_id is None:
                platform[row.instruction_key] = row.label
            else:
                tenant[row.instruction_key] = row.label

        # Tenant overrides platform
        merged = {**platform, **tenant}
        self._cache = merged

        logger.debug(
            "Localization cache loaded.",
            locale=self._locale,
            tenant_id=str(self._tenant_id) if self._tenant_id else "platform",
            platform_count=len(platform),
            tenant_count=len(tenant),
        )

        return self._cache

    async def resolve(self, key: str, fallback: str | None = None) -> str:
        """
        Resolve a single key. Returns fallback (or key itself) if not found.
        """
        cache = await self.load_all()
        return cache.get(key, fallback if fallback is not None else key)

    async def resolve_many(
        self, keys: list[str], fallback_map: dict[str, str] | None = None
    ) -> dict[str, str]:
        """
        Resolve multiple keys at once. Efficient for batch operations.

        fallback_map: optional dict of {key: canonical_label} to use
        when DB has no entry for a key.
        """
        cache = await self.load_all()
        fb = fallback_map or {}
        return {k: cache.get(k, fb.get(k, k)) for k in keys}


        