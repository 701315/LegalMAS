# src/engine/checks/planning/chunks.py

"""
Подготовка safe_chunks для проверок: загрузка, скоупинг, санитизация.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from engine.checks.planning.scope import ScopeResolver
from engine.content.document_content_service import DocumentContentService

logger = get_logger(__name__)

# Лимиты
MAX_CHUNKS_PER_DOC = 2000
MAX_CHUNK_TEXT_CHARS = 20_000


class ChunksPreparer:
    """
    Собирает и санитизирует чанки для одного документа и набора checks.
    """

    def __init__(self, scope_resolver: ScopeResolver):
        self._scope = scope_resolver

    async def build_safe_chunks(
        self,
        session: AsyncSession,
        doc,
        checks: list[Any],
    ) -> list[dict]:
        """
        Собрать safe_chunks для одного документа и набора checks.

        Общий helper для:
        - batched _run_checks_for_document(...)
        - Celery-task run_single_check(...)
        """
        content_service = DocumentContentService(session=session)

        # Определяем уровни чанков из retrieval-конфигов checks
        all_levels: set[str] = set()
        for chk in checks:
            retr_cfg = getattr(chk, "retrieval", None)
            if retr_cfg and getattr(retr_cfg, "levels", None):
                try:
                    all_levels.update(str(lvl).lower() for lvl in retr_cfg.levels)
                except Exception:
                    pass

        if not all_levels:
            levels_for_doc = ["subclause", "section"]
        else:
            preferred_order = ["subclause", "clause", "section"]
            levels_for_doc = [
                lvl for lvl in preferred_order if lvl in all_levels
            ] or list(all_levels)

        chunks = await content_service.get_retrieval_chunks_for_checks(
            doc_id=doc.id,
            levels=levels_for_doc,
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
        )

        # Scope filtering
        include_primary, include_types = self._scope.resolve_scope_flags()
        chunks = self._scope.filter_chunks_by_scope(
            chunks,
            include_primary=include_primary,
            include_types=include_types,
        )

        # Truncation guard
        if len(chunks) > MAX_CHUNKS_PER_DOC:
            logger.warning(
                "ChunksPreparer: too many chunks, truncating",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "chunk_count": len(chunks),
                    "max_chunks": MAX_CHUNKS_PER_DOC,
                },
            )
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        # Text sanitization
        safe_chunks: list[dict] = []
        for ch in chunks:
            text = ch.get("text") or ""
            if len(text) > MAX_CHUNK_TEXT_CHARS:
                logger.warning(
                    "ChunksPreparer: chunk text truncated",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "chunk_id": ch.get("id"),
                        "orig_len": len(text),
                        "max_len": MAX_CHUNK_TEXT_CHARS,
                    },
                )
                text = text[:MAX_CHUNK_TEXT_CHARS]

            safe_chunks.append({
                "id": ch.get("id"),
                "text": text,
                "metadata": ch.get("metadata") or {},
            })

        if not safe_chunks:
            safe_chunks = [{
                "id": f"{doc.id}:empty",
                "text": "",
                "metadata": {"doc_id": str(doc.id)},
            }]

        return safe_chunks
    
    