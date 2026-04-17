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


# Лимиты — максимальное число чанков и максимальный размер текста одного чанка
MAX_CHUNKS_PER_DOC = 2000
MAX_CHUNK_TEXT_CHARS = 20_000



class ChunksPreparer:
    """
    Собирает и санитизирует чанки для одного документа и набора checks.

    Простыми словами:
    - Получает список чанков документа из хранилища (MinIO).
    - Отфильтровывает чанки по scope (первичный сегмент, тип документа).
    - Обрезает слишком длинные тексты и слишком большие списки.
    - Возвращает "безопасный" список чанков, готовый для передачи в LLM.
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


        # Определяем уровни чанков из retrieval-конфигов checks.
        # Каждый check в YAML может указать нужные уровни: section / clause / subclause.
        # Собираем объединение всех уровней по всем checks в текущем наборе.
        all_levels: set[str] = set()
        for chk in checks:
            retr_cfg = getattr(chk, "retrieval", None)
            if retr_cfg and getattr(retr_cfg, "levels", None):
                try:
                    all_levels.update(str(lvl).lower() for lvl in retr_cfg.levels)
                except Exception:
                    pass


        # Если ни один check не указал уровни — используем безопасный default.
        # Порядок preferred_order важен: сначала самые мелкие (subclause),
        # потом крупнее (clause, section) — так LLM получает наиболее точный контекст.
        if not all_levels:
            levels_for_doc = ["subclause", "section"]
        else:
            preferred_order = ["subclause", "clause", "section"]
            levels_for_doc = [
                lvl for lvl in preferred_order if lvl in all_levels
            ] or list(all_levels)


        # Запрашиваем готовые чанки из V2-snapshot'ов.
        #
        # ВАЖНО: get_retrieval_chunks_for_checks принимает только doc_id и levels.
        # Параметры target_tokens / max_tokens / overlap_ratio здесь НЕ нужны —
        # нарезка чанков произошла один раз на этапе CHUNKING в SegmentChunkBuilderV2.
        # Здесь мы только ЧИТАЕМ уже готовые чанки из MinIO.
        chunks = await content_service.get_retrieval_chunks_for_checks(
            doc_id=doc.id,
            levels=levels_for_doc,
        )


        # Фильтрация по scope: оставляем только чанки из нужных сегментов
        # (например, только из первичного документа, без приложений).
        include_primary, include_types = self._scope.resolve_scope_flags()
        chunks = self._scope.filter_chunks_by_scope(
            chunks,
            include_primary=include_primary,
            include_types=include_types,
        )


        # Защита от аномально большого числа чанков.
        # Если документ содержит больше MAX_CHUNKS_PER_DOC чанков —
        # берём только первые, остальные отбрасываем с предупреждением в лог.
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


        # Санитизация текста: если текст одного чанка слишком длинный —
        # обрезаем до MAX_CHUNK_TEXT_CHARS символов.
        # Это защита от случаев, когда в snapshot попал аномально большой чанк.
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
            logger.warning(
                "ChunksPreparer: no chunks after filtering, returning empty list",
                extra={"doc_id": str(getattr(doc, "id", None))},
            )

        return safe_chunks
    
    
    