"""
Repository for DocumentRunLanguageResolution database operations.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.document import DocumentRunLanguageResolution


class DocumentRunLanguageResolutionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_run_and_version(
        self,
        run_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> DocumentRunLanguageResolution | None:
        """Получить запись резолва для конкретного запуска и версии документа."""
        stmt = select(DocumentRunLanguageResolution).where(
            DocumentRunLanguageResolution.run_id == run_id,
            DocumentRunLanguageResolution.document_version_id == document_version_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def upsert_resolution(
        self,
        run_id: uuid.UUID,
        document_version_id: uuid.UUID,
        tenant_id: uuid.UUID,
        requested_language: str,
        available_languages: list[str],
        effective_language: str | None,
        resolution_status: str,
        reason_code: str | None = None,
        canonical_layout_ref: str | None = None,
        layout_primary_ref: str | None = None,
        layout_primary_sanitized_ref: str | None = None,
    ) -> DocumentRunLanguageResolution:
        """
        Создаёт или обновляет запись резолва (идемпотентно).
        """
        existing = await self.get_by_run_and_version(run_id, document_version_id)

        if existing:
            existing.tenant_id = tenant_id
            existing.requested_language = requested_language
            existing.available_languages = available_languages
            existing.effective_language = effective_language
            existing.resolution_status = resolution_status
            existing.reason_code = reason_code
            if canonical_layout_ref is not None:
                existing.canonical_layout_ref = canonical_layout_ref
            if layout_primary_ref is not None:
                existing.layout_primary_ref = layout_primary_ref
            if layout_primary_sanitized_ref is not None:
                existing.layout_primary_sanitized_ref = layout_primary_sanitized_ref
            await self.session.flush()
            return existing

        new_res = DocumentRunLanguageResolution(
            run_id=run_id,
            document_version_id=document_version_id,
            tenant_id=tenant_id,
            requested_language=requested_language,
            available_languages=available_languages,
            effective_language=effective_language,
            resolution_status=resolution_status,
            reason_code=reason_code,
            canonical_layout_ref=canonical_layout_ref,
            layout_primary_ref=layout_primary_ref,
            layout_primary_sanitized_ref=layout_primary_sanitized_ref,
        )
        self.session.add(new_res)
        await self.session.flush()
        return new_res
