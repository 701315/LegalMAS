# src/db/repositories/tenant_locale_policy_repo.py

"""
Repository for TenantResultLocalePolicy CRUD operations.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.tenant_result_locale_policy import TenantResultLocalePolicy


class TenantLocalePolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_tenant_id(
        self,
        tenant_id: uuid.UUID,
    ) -> TenantResultLocalePolicy | None:
        """Return the locale policy for a tenant, or None if not configured."""
        stmt = select(TenantResultLocalePolicy).where(
            TenantResultLocalePolicy.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


        