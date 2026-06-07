# src/engine/checks/planning/chunks.py

"""
Подготовка safe_chunks для проверок: загрузка, скоупинг, санитизация.

P8.8d:
- Retrieval truth переключён на legal_unit-based corpus.
- Основной retrieval набор для checks:
    * legal_unit — exact legal units,
    * section    — крупный контекстный слой.
- Legacy level `subclause` больше не считается retrieval truth.
  Если старый retrieval-config всё ещё просит `subclause`,
  он автоматически нормализуется в `legal_unit`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from engine.checks.planning.scope import ScopeResolver
from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2
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

    В multi-document режиме умеет строить корпус для одного сегмента:
    - Загружает только чанки нужного сегмента через ChunkCorpusReaderV2.load_segment.
    - Каждый чанк уже содержит metadata["segment_id"] — проставляется в reader'е.
    - Возвращает реальные нарезанные чанки, не synthetic-заглушку.
    """

    def __init__(self, scope_resolver: ScopeResolver):
        self._scope = scope_resolver

    # ──────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ──────────────────────────────────────────────────────────────

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
        levels_for_doc = self._resolve_levels(checks, default=["legal_unit", "section"])

        # Запрашиваем retrieval-visible corpus из V2 snapshot'ов.
        # После P8.8d retrieval truth = legal_unit + section.
        # Нарезка / materialization произошла один раз на этапе CHUNKING —
        # здесь мы только ЧИТАЕМ готовый corpus.
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

        safe_chunks = self._sanitize_chunks(chunks, doc=doc)

        if not safe_chunks:
            logger.warning(
                "ChunksPreparer: no chunks after filtering, returning empty list",
                extra={"doc_id": str(getattr(doc, "id", None))},
            )

        return safe_chunks

    async def build_safe_chunks_for_segment(
        self,
        session: AsyncSession,
        doc,
        checks: list[Any],
        segment_id: str,
        max_chars: int = MAX_CHUNK_TEXT_CHARS,
    ) -> list[dict]:
        """
        Собрать safe_chunks для одного логического документа-сегмента.

        Для непрофессионального программиста:
        - В multi-document режиме один физический файл содержит несколько
          логических документов-сегментов.
        - Этот метод загружает реальные чанки только нужного сегмента через
          ChunkCorpusReaderV2.load_segment — те же нарезанные чанки, что
          были записаны в snapshot на этапе CHUNKING.
        - Каждый чанк уже содержит metadata["segment_id"] — reader проставляет
          его автоматически, мы только проверяем что он там есть.
        - Фильтрация по segment_id здесь не нужна: load_segment возвращает
          только чанки запрошенного сегмента.

        Отличие от предыдущей реализации (synthetic chunk):
        - Раньше мы брали весь текст сегмента одним куском через get_segment_text.
        - Теперь читаем реальные нарезанные чанки — это корректный уровень
          детализации для LLM и rules-checker.
        """
        if not segment_id:
            logger.warning(
                "ChunksPreparer: build_safe_chunks_for_segment called without segment_id",
                extra={"doc_id": str(getattr(doc, "id", None))},
            )
            return []

        levels_for_segment = self._resolve_levels(checks, default=["legal_unit", "section"])

        # Загружаем чанки только этого сегмента через ChunkCorpusReaderV2.
        # Он сам находит последнюю версию документа и читает нужный snapshot из MinIO.
        reader = ChunkCorpusReaderV2(session=session)
        chunks = await reader.load_segment(
            doc_id=doc.id,
            segment_id=segment_id,
            levels=levels_for_segment,
        )

        if not chunks:
            logger.warning(
                "ChunksPreparer: no chunks for segment, returning empty list",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "segment_id": segment_id,
                    "levels": levels_for_segment,
                },
            )
            return []

        # Защита от аномально большого числа чанков одного сегмента.
        if len(chunks) > MAX_CHUNKS_PER_DOC:
            logger.warning(
                "ChunksPreparer: too many segment chunks, truncating",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "segment_id": segment_id,
                    "chunk_count": len(chunks),
                    "max_chunks": MAX_CHUNKS_PER_DOC,
                },
            )
            chunks = chunks[:MAX_CHUNKS_PER_DOC]

        safe_chunks = self._sanitize_chunks(chunks, doc=doc, max_chars=max_chars)

        if not safe_chunks:
            logger.warning(
                "ChunksPreparer: all segment chunks empty after sanitization",
                extra={
                    "doc_id": str(getattr(doc, "id", None)),
                    "segment_id": segment_id,
                },
            )

        return safe_chunks

    # ──────────────────────────────────────────────────────────────
    # ВНУТРЕННИЕ МЕТОДЫ
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_levels(
        checks: list[Any],
        default: list[str],
    ) -> list[str]:
        """
        Определить нужные уровни чанков из retrieval-конфигов checks.

        Для непрофессионального программиста:
        - Каждый check в YAML может указать нужные уровни chunk corpus.
        - После P8.8d основной retrieval substrate = legal_unit.
        - Legacy значение `subclause` автоматически алиасится в `legal_unit`.
        - Если ни один check не указал уровни — используем default.
        - Порядок preferred_order важен: сначала точный retrieval слой
          (legal_unit), затем более крупный контекст (section), затем
          canonical fallback layers если они явно запрошены.
        """
        alias_map = {
            "subclause": "legal_unit",
        }

        all_levels: set[str] = set()

        for chk in checks:
            retr_cfg = getattr(chk, "retrieval", None)
            if retr_cfg and getattr(retr_cfg, "levels", None):
                try:
                    for lvl in retr_cfg.levels:
                        normalized = str(lvl).strip().lower()
                        if not normalized:
                            continue
                        normalized = alias_map.get(normalized, normalized)
                        all_levels.add(normalized)
                except Exception:
                    pass

        if not all_levels:
            return default

        preferred_order = ["legal_unit", "section", "clause", "subclause"]
        return [lvl for lvl in preferred_order if lvl in all_levels] or list(all_levels)

    @staticmethod
    def _sanitize_chunks(
        chunks: list[dict],
        doc,
        max_chars: int = MAX_CHUNK_TEXT_CHARS,
    ) -> list[dict]:
        """
        Санитизировать список чанков: обрезать длинные тексты, нормализовать структуру.

        Для непрофессионального программиста:
        - Берём сырые чанки из MinIO и приводим их к единому безопасному формату.
        - Если текст одного чанка слишком длинный — обрезаем до max_chars символов.
          Это защита от аномально больших чанков в snapshot'е.
        - Возвращаем список словарей с ключами: id, text, metadata.
          Именно такой формат ожидает CheckExecutor.
        """
        safe: list[dict] = []
        doc_id_str = str(getattr(doc, "id", None))

        for ch in chunks:
            text = (ch.get("text") or "").strip()

            # Пустые чанки пропускаем — они не несут информации для LLM.
            if not text:
                continue

            if len(text) > max_chars:
                logger.warning(
                    "ChunksPreparer: chunk text truncated",
                    extra={
                        "doc_id": doc_id_str,
                        "chunk_id": ch.get("id"),
                        "orig_len": len(text),
                        "max_len": max_chars,
                    },
                )
                text = text[:max_chars]

            metadata = ch.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}

            # Диагностика: чанки без effective_uid не будут правильно
            # идентифицированы в executor.py и citation_resolver.
            # Это может быть старый чанк без Sprint 3 canonical identity.
            if not metadata.get("effective_uid"):
                logger.debug(
                    "ChunksPreparer: chunk missing effective_uid in metadata",
                    extra={
                        "doc_id": doc_id_str,
                        "chunk_id": ch.get("id"),
                        "chunk_kind": metadata.get("chunk_kind"),
                        "raw_uid": metadata.get("raw_uid"),
                    },
                )

            safe.append(
                {
                    "id": ch.get("id"),
                    "text": text,
                    "metadata": metadata,
                }
            )

        return safe
