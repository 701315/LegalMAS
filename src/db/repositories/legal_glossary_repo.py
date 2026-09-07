"""
Repository for LegalGlossary CRUD operations (Sprint 3.2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.legal_glossary import LegalGlossary


class LegalGlossaryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_terms(
        self,
        tenant_id: uuid.UUID | None,
        source_locale: str,
        target_locale: str,
    ) -> list[LegalGlossary]:
        """
        Fetch active glossary terms for a specific locale pair.

        Rules:
        1. If tenant_id is provided, fetches BOTH platform-wide terms (tenant_id IS NULL)
           and tenant-specific overrides (tenant_id == target_tenant).
        2. If tenant_id is None, fetches ONLY platform-wide terms.
        3. Only active terms (is_active = True) are returned.
        """
        src = source_locale.strip().lower()
        tgt = target_locale.strip().lower()

        # Base conditions: active and matching locales
        conditions = [
            LegalGlossary.source_locale == src,
            LegalGlossary.target_locale == tgt,
            LegalGlossary.is_active == True,
        ]

        # Multi-tenancy filter
        if tenant_id is not None:
            conditions.append(
                or_(
                    LegalGlossary.tenant_id == tenant_id,
                    LegalGlossary.tenant_id.is_(None),
                )
            )
        else:
            conditions.append(LegalGlossary.tenant_id.is_(None))

        stmt = select(LegalGlossary).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
