# src/engine/content/document_content_service.py

"""
DocumentContentService v3: фасад над чанками и (legacy) clause tree + layout.

- Для retrieval/checks читаем готовые snapshot'ы чанков (CHUNKS v2).
- Clause tree + layout используем только как legacy-путь / для вспомогательных задач
  (header/snippet, on-the-fly materialization для старых документов).

Простыми словами:

- В MinIO есть два типа артефактов:
  1) layout (text layout) — список маленьких текстовых кусочков (elements);
  2) clause tree — структура документа (пункты, подпункты, их иерархия).

- Этот сервис:
  - читает clause tree и layout по ссылкам из последней DocumentVersion;
  - читает CHUNKS v2 snapshot'ы через ChunkCorpusReaderV2;
  - использует чистые helper'ы:
      * ClauseTreeBuilder — только для legacy header/snippet path;
      * chunking.* — summary и sized split;
      * chunk_ids.* — canonical chunk id generation;
  - отдаёт:
    * canonical clause chunks,
    * canonical subclause chunks,
    * hierarchical section/clause/subclause view,
    * RetrievalChunk adapters,
    * header + snippet для классификаторов.

Canonical contract (Sprint 3):
- canonical identity чанка / узла = effective_uid;
- raw_uid остаётся только display/reference field;
- scope обязателен как часть identity space;
- broken chunks без effective_uid не маскируются fallback id generation;
- retrieval adapters кладут effective_uid в legacy поле RetrievalChunk.clause_uid,
  чтобы downstream не терял canonical identity.

Этап 6 — semantic layer:
- get_legal_units() читает legal_units_v1.json из segment_meta["legal_units_ref"];
- get_evidence_bundle() строит EvidenceBundle по RetrievalProfile;
- оба метода опциональны: если артефакты отсутствуют, возвращают пустые результаты;
- существующий chunk контракт не ломается.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.document import DocumentVersion
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content._document_content_chunks import (
    build_canonical_chunk_payload,
    build_retrieval_chunk_from_canonical,
    join_chunk_texts,
    normalize_snapshot_chunk_metadata,
)
from engine.content._document_content_chunks import (
    build_retrieval_chunk_meta as build_retrieval_chunk_meta_impl,
)
from engine.content._document_content_layout import (
    build_legacy_snippet_from_leaf_chunks,
)
from engine.content._document_content_layout import (
    extract_snippet_from_layout as extract_snippet_from_layout_impl,
)
from engine.content._document_content_layout import (
    extract_title_and_preamble_from_layout as extract_title_and_preamble_from_layout_impl,
)
from engine.content._document_content_semantic import (
    build_no_legal_units_result,
    build_profile_not_found_result,
    load_legal_units_from_segments,
    restore_legal_units,
    serialize_primary_units_for_bundle,
)
from engine.content.chunk_canonicalization import add_summary, build_sized_chunks_from_leaf
from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2
from engine.content.clause_tree_builder import ClauseTreeBuilder
from engine.retrieval.models import RetrievalChunk
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


class ClauseTreeStorageClientProtocol:
    """
    Простейший протокол для клиента хранения, который умеет читать JSON
    по URI вида s3://bucket/path/to/file.json.

    Для непрофессионального программиста:
    - Это просто "договор" об интерфейсе.
    - Любой объект, у которого есть метод load_json(uri: str) -> dict,
      можно использовать как источник clause tree.
    """

    async def load_json(self, uri: str) -> dict[str, Any]:
        raise NotImplementedError


class ClauseTreeStorageClient(ClauseTreeStorageClientProtocol):
    """
    Адаптер поверх ArtifactStore, реализующий load_json(uri).

    ArtifactStore сам знает, как читать JSON из MinIO.
    Этот класс просто оборачивает синхронный вызов в асинхронный,
    чтобы удобнее использовать его в async-коде.
    """

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or ArtifactStore()

    async def load_json(self, uri: str) -> dict[str, Any]:
        from anyio.to_thread import run_sync

        def _get() -> dict[str, Any]:
            return self.store.get_json(uri)

        return await run_sync(_get)


class LayoutStorageClient:
    """
    Простой клиент для чтения layout JSON (raw или sanitized) из MinIO
    через ArtifactStore.

    Формат layout (см. build_text_layout_raw):
      {
        "elements": [
          {
            "element_id": str,
            "type": "heading" | "text" | "listitem",
            "text": str,
            "page": int,
            "bbox": [x0, top, x1, bottom],
            "confidence": float,
            "clause_uid": null | str,  # legacy linkage field, опционально
          },
          ...
        ],
        "tables": [...],
        "metadata": {...}
      }
    """

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or ArtifactStore()

    async def load_json(self, uri: str) -> dict[str, Any]:
        from anyio.to_thread import run_sync

        def _get() -> dict[str, Any]:
            return self.store.get_json(uri)

        return await run_sync(_get)


class DocumentContentService:
    """
    Сервис доступа к содержимому документа (структура + текст).

    Важно:
    - Сервис работает как "адаптер" поверх:
        * AsyncSession (через DocumentVersionRepository),
        * ArtifactStore (через ClauseTreeStorageClient и LayoutStorageClient).
    - Вся сложная логика вынесена в отдельные модули:
        * ClauseTreeBuilder — legacy helper для clause tree + layout;
        * ChunkCorpusReaderV2 — чтение snapshot corpus v2;
        * chunking.* — summary и sized split.
    - Никаких глобальных синглтонов и кэшей здесь нет.
      Каждый воркер создаёт этот сервис в рамках одного UnitOfWork (db_uow).

    Этап 6 — semantic layer:
    - get_legal_units() даёт доступ к legal_units_v1.json;
    - get_evidence_bundle() строит отобранный набор units для конкретного check.
    """

    def __init__(
        self,
        session: AsyncSession,
        storage_client: ClauseTreeStorageClientProtocol | None = None,
        layout_client: LayoutStorageClient | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.session = session
        self.versions = DocumentVersionRepository(session)
        self.documents = DocumentRepository(session)

        # Один ArtifactStore на весь сервис.
        self._artifact_store = artifact_store or ArtifactStore()

        self.storage = storage_client or ClauseTreeStorageClient(self._artifact_store)
        self.layout_storage = layout_client or LayoutStorageClient(self._artifact_store)

    # -------------------------------------------------------------------------
    # Внутренние helpers: загрузка последней версии, clause tree и layout
    # -------------------------------------------------------------------------

    async def _get_latest_version(self, doc_id: uuid.UUID) -> DocumentVersion | None:
        """
        Получить последнюю версию документа (по version_num).
        Если версий нет, вернёт None.
        """
        return await self.versions.get_latest(doc_id)

    async def _load_clause_tree(self, version: DocumentVersion) -> dict[str, Any] | None:
        """
        Legacy-путь для clause tree.

        Используется только для:
        - старых документов без CHUNKS v2 snapshot'ов;
        - вспомогательных задач (header/snippet, debug).
        """
        if not version.clause_tree_ref:
            return None
        return await self.storage.load_json(version.clause_tree_ref)

    async def _load_layout(self, version: DocumentVersion) -> dict[str, Any] | None:
        """
        Загрузить рабочий layout документа по единому контракту пайплайна.

        Приоритет:
        1) layout_primary_sanitized_ref — основной source of truth после PII;
        2) layout_primary_ref — recovery fallback для случаев, когда PII ещё не выполнен.
        """
        layout_ref = getattr(version, "layout_primary_sanitized_ref", None) or getattr(
            version, "layout_primary_ref", None
        )
        if not layout_ref:
            return None
        return await self.layout_storage.load_json(layout_ref)

    # -------------------------------------------------------------------------
    # Вспомогательные helpers
    # -------------------------------------------------------------------------

    def _build_retrieval_chunk_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        """
        Сформировать meta для RetrievalChunk, сохранив canonical поля и
        downstream-полезные атрибуты, но не дублируя top-level RetrievalChunk fields.
        """
        return build_retrieval_chunk_meta_impl(meta)

    async def _load_chunks_from_snapshot(
        self,
        doc_id: uuid.UUID,
        levels: list[str],
    ) -> list[dict[str, Any]]:
        """
        Прочитать чанки из сохранённых v2 snapshot'ов.

        ВАЖНО:
        - Используется только CHUNKS v2 (file manifest + segment snapshots).
        - Legacy v1 chunk snapshot больше не читается.
        - Если v2-артефакты отсутствуют, невалидны или reader падает,
          возвращаем пустой список.
        """
        v2_reader = ChunkCorpusReaderV2(
            session=self.session,
            artifact_store=self._artifact_store,
        )

        try:
            v2_chunks = await v2_reader.load(doc_id=doc_id, levels=levels)
        except Exception as e:
            logger.warning(
                "DocumentContentService._load_chunks_from_snapshot: v2 reader failed",
                extra={
                    "doc_id": str(doc_id),
                    "levels": levels,
                    "error": str(e),
                },
            )
            return []

        return v2_chunks or []

    # -------------------------------------------------------------------------
    # Публичные методы — chunks
    # -------------------------------------------------------------------------

    async def get_title_and_preamble(
        self,
        doc_id: uuid.UUID,
        max_pages: int = 2,
        max_length: int = 1500,
    ) -> str | None:
        """
        Извлечь шапку документа (title + преамбула) напрямую из layout.

        Простыми словами:
        - Берём layout последней версии документа.
        - Сканируем первые несколько страниц.
        - Для коротких документов (<= 4 страниц) читаем до 2 страниц шапки.
        - Для более длинных документов читаем до 3 страниц шапки.
        - Собираем текст сверху вниз, пока не встретим первое крупное
          структурное разделение (оглавление или раздел уровня "1. DEFINITIONS").
        - Возвращаем один текстовый блок для L2/L4 и фронта.
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            return None

        layout = await self._load_layout(version)
        if not layout:
            return None

        return extract_title_and_preamble_from_layout_impl(
            layout,
            max_pages=max_pages,
            max_length=max_length,
        )

    async def get_snippet_from_layout(
        self,
        doc_id: uuid.UUID,
        skip_pages: int = 2,
        max_length: int = 1500,
        min_element_len: int = 40,
    ) -> str | None:
        """
        Извлечь сниппет тела документа напрямую из layout (v2-артефакт).

        Простыми словами:
        - Берём layout последней версии документа.
        - Для коротких документов (<= 4 страниц) пропускаем 1 страницу.
        - Для более длинных документов пропускаем 3 страницы.
        - Собираем текст следующих страниц, отбрасывая слишком короткие элементы
          (колонтитулы, номера страниц и т.п.).
        - Возвращаем один текстовый блок для L3 (эмбеддинги) и L4 (LLM).
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            logger.warning(
                "get_snippet_from_layout: no latest version",
                extra={"doc_id": str(doc_id)},
            )
            return None

        layout = await self._load_layout(version)
        if not layout:
            logger.warning(
                "get_snippet_from_layout: layout not available "
                "(layout_primary_sanitized_ref and layout_primary_ref are both empty)",
                extra={"doc_id": str(doc_id)},
            )
            return None

        elements = layout.get("elements") or []
        if not elements:
            return None

        snippet, total_pages, effective_skip_pages = extract_snippet_from_layout_impl(
            layout,
            skip_pages=skip_pages,
            max_length=max_length,
            min_element_len=min_element_len,
        )

        if not snippet:
            logger.info(
                "get_snippet_from_layout: no body elements found after effective_skip_pages",
                extra={
                    "doc_id": str(doc_id),
                    "effective_skip_pages": effective_skip_pages,
                    "total_pages": total_pages,
                },
            )
            return None

        return snippet or None

    async def get_chunks(
        self,
        doc_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """
        Вернуть canonical clause chunks из CHUNKS v2 snapshot.

        ВАЖНО:
        - Источник истины: snapshot'ы chunk corpus v2.
        - Legacy on-the-fly clause tree/layout path здесь не используется.
        - На выходе canonical metadata shape для clause chunks.
        - Chunk без effective_uid считается broken и пропускается.
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            logger.warning(
                "DocumentContentService.get_chunks: no latest version, returning empty list",
                extra={"doc_id": str(doc_id)},
            )
            return []

        manifest_ref = getattr(version, "chunks_manifest_v2_ref", None)
        if not manifest_ref:
            logger.warning(
                "DocumentContentService.get_chunks: chunks_manifest_v2_ref is not set, returning empty list",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                },
            )
            return []

        snapshot_chunks = await self._load_chunks_from_snapshot(doc_id, ["clause"])
        if not snapshot_chunks:
            logger.warning(
                "DocumentContentService.get_chunks: snapshot returned no clause chunks",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                },
            )
            return []

        canonical_chunks: list[dict[str, Any]] = []

        for ch in snapshot_chunks:
            text = (ch.get("text") or "").strip()
            if not text:
                continue

            meta = dict(ch.get("metadata") or {})
            effective_uid = meta.get("effective_uid")
            raw_uid = meta.get("raw_uid")

            if not effective_uid:
                logger.warning(
                    "DocumentContentService.get_chunks: snapshot clause chunk missing effective_uid, skipping chunk",
                    extra={
                        "doc_id": str(doc_id),
                        "chunk_id": ch.get("id"),
                        "raw_uid": raw_uid,
                        "scope": meta.get("scope"),
                        "level": meta.get("level"),
                        "title": meta.get("title"),
                    },
                )
                continue

            normalized_meta = normalize_snapshot_chunk_metadata(
                doc_id=doc_id,
                text=text,
                meta=meta,
                chunk_kind="clause",
            )

            canonical_chunks.append(
                build_canonical_chunk_payload(
                    chunk_id=ch.get("id"),
                    text=text,
                    meta=normalized_meta,
                )
            )

        return canonical_chunks

    async def get_header_and_snippet(
        self,
        doc_id: uuid.UUID,
        max_snippet_len: int = 1500,
        max_leaf_clauses: int = 3,
    ) -> tuple[str | None, str | None]:
        """
        Вернуть:
        - header_text: заголовки верхнего уровня / шапка документа —
          для L2 классификатора;
        - snippet_text: текст первых нескольких листовых клауз —
          для L3 (эмбеддинги) и L4 (LLM).

        ВАЖНО:
        - Для v2-документов без clause_tree_ref: читаем header/snippet
          напрямую из layout.
        - Для legacy v1 документов: snippet собирается по clause tree + layout.
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            return None, None

        tree = await self._load_clause_tree(version)
        layout = await self._load_layout(version)

        if not layout:
            logger.warning(
                "get_header_and_snippet: layout is not available, returning empty header/snippet",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "clause_tree_ref": getattr(version, "clause_tree_ref", None),
                    "layout_primary_ref": getattr(version, "layout_primary_ref", None),
                    "layout_primary_sanitized_ref": getattr(
                        version, "layout_primary_sanitized_ref", None
                    ),
                },
            )
            return None, None

        if not tree:
            logger.info(
                "get_header_and_snippet: using layout-only path",
                extra={"doc_id": str(doc_id)},
            )
            header_text = await self.get_title_and_preamble(doc_id)
            snippet_text = await self.get_snippet_from_layout(doc_id)
            return header_text, snippet_text

        header_text = await self.get_title_and_preamble(doc_id)

        leaf_result = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=doc_id,
            tree=tree,
            layout=layout,
        )
        leaf_chunks_all = leaf_result.chunks

        if not leaf_chunks_all:
            return header_text, None

        snippet_text = build_legacy_snippet_from_leaf_chunks(
            leaf_chunks_all,
            max_snippet_len=max_snippet_len,
            max_leaf_clauses=max_leaf_clauses,
        )

        return header_text, (snippet_text or None)

    async def _get_clause_chunks_as_retrieval(
        self,
        doc_id: uuid.UUID,
    ) -> list[RetrievalChunk]:
        """
        Внутренний адаптер: canonical clause chunks -> RetrievalChunk.

        ВАЖНО:
        - RetrievalChunk здесь остаётся compatibility view.
        - Источником истины являются canonical dict chunks из get_chunks().
        - RetrievalChunk.clause_uid заполняется effective_uid, а не raw_uid,
          чтобы downstream не терял canonical identity.
        """
        raw_chunks = await self.get_chunks(doc_id)

        retrieval_chunks: list[RetrievalChunk] = []
        for ch in raw_chunks:
            text = (ch.get("text") or "").strip()
            meta = ch.get("metadata") or {}
            if not text:
                continue

            effective_uid = meta.get("effective_uid")

            if not effective_uid:
                logger.warning(
                    "DocumentContentService._get_clause_chunks_as_retrieval: chunk missing effective_uid, skipping",
                    extra={
                        "doc_id": str(doc_id),
                        "chunk_id": ch.get("id"),
                        "raw_uid": meta.get("raw_uid"),
                        "scope": meta.get("scope"),
                        "level": meta.get("level"),
                    },
                )
                continue

            retrieval_chunk = build_retrieval_chunk_from_canonical(
                chunk=ch,
                doc_id=doc_id,
                default_kind="clause",
            )
            if retrieval_chunk is not None:
                retrieval_chunks.append(retrieval_chunk)

        return retrieval_chunks

    async def _get_sized_chunks_as_retrieval(
        self,
        doc_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> list[RetrievalChunk]:
        """
        Внутренний адаптер: canonical subclause chunks -> RetrievalChunk.

        ВАЖНО:
        - kind читается из canonical metadata, а не вычисляется из id.
        - get_sized_chunks() возвращает только subclause chunks.
        - RetrievalChunk.clause_uid заполняется effective_uid.
        """
        raw_chunks = await self.get_sized_chunks(
            doc_id=doc_id,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )

        retrieval_chunks: list[RetrievalChunk] = []
        for ch in raw_chunks:
            text = (ch.get("text") or "").strip()
            meta = ch.get("metadata") or {}
            if not text:
                continue

            effective_uid = meta.get("effective_uid")

            if not effective_uid:
                logger.warning(
                    "DocumentContentService._get_sized_chunks_as_retrieval: chunk missing effective_uid, skipping",
                    extra={
                        "doc_id": str(doc_id),
                        "chunk_id": ch.get("id"),
                        "raw_uid": meta.get("raw_uid"),
                        "scope": meta.get("scope"),
                        "level": meta.get("level"),
                        "subchunk_index": meta.get("subchunk_index"),
                    },
                )
                continue

            retrieval_chunk = build_retrieval_chunk_from_canonical(
                chunk=ch,
                doc_id=doc_id,
                default_kind="subclause",
            )
            if retrieval_chunk is not None:
                retrieval_chunks.append(retrieval_chunk)

        return retrieval_chunks

    async def get_sized_chunks(
        self,
        doc_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> list[dict[str, Any]]:
        """
        Построить canonical subclause chunks из canonical clause chunks.

        ВАЖНО:
        - На выходе всегда chunk_kind="subclause".
        - Даже если исходная clause не была реально разбита, она всё равно
          представляется как subclause с subchunk_index=0, subchunk_count=1.
        - Base clause chunk без effective_uid считается broken и пропускается.
        - Реальная логика split/metadata/fallback живёт в
          chunk_canonicalization.build_sized_chunks_from_leaf().
        """
        base_chunks = await self.get_chunks(doc_id)

        sized = build_sized_chunks_from_leaf(
            doc_id=doc_id,
            leaf_chunks=base_chunks,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
            total_pages=None,
        )

        sized = add_summary(sized)

        if not sized:
            logger.warning(
                "DocumentContentService.get_sized_chunks: no sized chunks built, returning empty list",
                extra={"doc_id": str(doc_id)},
            )
            return []

        return sized

    async def get_hierarchical_chunks(
        self,
        doc_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Вернуть многоуровневые чанки по документу.

        ВАЖНО:
        - Источник section/clause/subclause: CHUNKS v2 snapshot.
        - Если clause snapshot отсутствует, clause можно взять из get_chunks().
        - Если subclause snapshot отсутствует, subclause можно достроить из clause
          через get_sized_chunks().
        - Broken snapshot chunks без effective_uid пропускаются.
        """
        snapshot_chunks = await self._load_chunks_from_snapshot(
            doc_id,
            ["section", "clause", "subclause"],
        )

        section_chunks: list[dict[str, Any]] = []
        clause_chunks: list[dict[str, Any]] = []
        subclause_chunks: list[dict[str, Any]] = []

        for ch in snapshot_chunks:
            text = (ch.get("text") or "").strip()
            if not text:
                continue

            meta = dict(ch.get("metadata") or {})
            kind = str(meta.get("chunk_kind") or "").strip().lower()
            effective_uid = meta.get("effective_uid")

            if not effective_uid:
                logger.warning(
                    "DocumentContentService.get_hierarchical_chunks: snapshot chunk missing effective_uid, skipping",
                    extra={
                        "doc_id": str(doc_id),
                        "chunk_id": ch.get("id"),
                        "chunk_kind": kind,
                        "raw_uid": meta.get("raw_uid"),
                        "scope": meta.get("scope"),
                    },
                )
                continue

            normalized_meta = normalize_snapshot_chunk_metadata(
                doc_id=doc_id,
                text=text,
                meta=meta,
            )
            normalized = build_canonical_chunk_payload(
                chunk_id=ch.get("id"),
                text=text,
                meta=normalized_meta,
            )

            if kind == "section":
                normalized_meta["chunk_kind"] = "section"
                section_chunks.append(normalized)
            elif kind == "clause":
                normalized_meta["chunk_kind"] = "clause"
                clause_chunks.append(normalized)
            elif kind == "subclause":
                normalized_meta["chunk_kind"] = "subclause"
                subclause_chunks.append(normalized)

        if not clause_chunks:
            clause_chunks = await self.get_chunks(doc_id)

        if not subclause_chunks:
            subclause_chunks = await self.get_sized_chunks(
                doc_id=doc_id,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
            )

        return {
            "section": section_chunks,
            "clause": clause_chunks,
            "subclause": subclause_chunks,
        }

    async def get_retrieval_chunks_for_checks(
        self,
        doc_id: uuid.UUID,
        levels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Удобный фасад для CheckRunner: вернуть плоский список чанков для checks.

        По умолчанию:
        - subclause: нормализованные под-чанки,
        - section: крупные разделы.

        ВАЖНО:
        - В V2_ONLY режиме читаем чанки только из CHUNKS v2 snapshot'ов.
        - Если snapshot отсутствует или повреждён, возвращаем пустой список.
        - On-the-fly legacy fallback через clause tree/layout не используется.
        - Broken chunks без effective_uid фильтруются.
        """
        if levels is None:
            levels = ["subclause", "section"]

        levels = [lvl.strip().lower() for lvl in levels if isinstance(lvl, str) and lvl.strip()]
        levels = list(dict.fromkeys(levels))

        if not levels:
            return []

        version = await self._get_latest_version(doc_id)
        if not version:
            logger.warning(
                "get_retrieval_chunks_for_checks: no latest version found",
                extra={"doc_id": str(doc_id), "levels": levels},
            )
            return []

        manifest_ref = getattr(version, "chunks_manifest_v2_ref", None)
        if not manifest_ref:
            logger.warning(
                "get_retrieval_chunks_for_checks: chunks_manifest_v2_ref is not set. "
                "Document was processed by legacy pipeline or chunking stage not completed. "
                "Check will run on empty corpus.",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "levels": levels,
                },
            )
            return []

        snapshot_chunks = await self._load_chunks_from_snapshot(doc_id, levels)

        if not snapshot_chunks:
            logger.warning(
                "get_retrieval_chunks_for_checks: manifest exists but snapshot returned "
                "no chunks for requested levels. Check will run on empty corpus.",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "levels": levels,
                },
            )
            return []

        normalized_chunks: list[dict[str, Any]] = []
        for ch in snapshot_chunks:
            meta = ch.get("metadata") or {}
            if not meta.get("effective_uid"):
                logger.warning(
                    "get_retrieval_chunks_for_checks: chunk missing effective_uid, skipping",
                    extra={
                        "doc_id": str(doc_id),
                        "chunk_id": ch.get("id"),
                        "chunk_kind": meta.get("chunk_kind"),
                        "raw_uid": meta.get("raw_uid"),
                        "scope": meta.get("scope"),
                    },
                )
                continue
            normalized_chunks.append(ch)

        return normalized_chunks

    async def get_segment_text(
        self,
        *,
        document_version_id: uuid.UUID,
        segment_id: str,
        levels: list[str] | None = None,
        max_chars: int = 8000,
    ) -> str | None:
        """
        Вернуть текст одного логического сегмента по document_version_id и segment_id.

        Для непрофессионального программиста:
        - Берём только чанки этого сегмента из CHUNKS v2 snapshot'ов;
        - Склеиваем текст в один блок, с верхним лимитом max_chars;
        - Не трогаем clause tree / layout напрямую, вся логика в ChunkCorpusReaderV2.
        """
        if levels is None:
            levels = ["clause", "subclause"]

        normalized_levels = [
            lvl.strip().lower() for lvl in levels if isinstance(lvl, str) and lvl.strip()
        ]
        normalized_levels = list(dict.fromkeys(normalized_levels))

        if "subclause" in normalized_levels and "clause" in normalized_levels:
            normalized_levels = [lvl for lvl in normalized_levels if lvl != "clause"]

        if not normalized_levels:
            return None

        if max_chars <= 0:
            return None

        reader = ChunkCorpusReaderV2(
            session=self.session,
            artifact_store=self._artifact_store,
        )

        version = await self.versions.get_by_id(document_version_id)
        if not version:
            logger.warning(
                "DocumentContentService.get_segment_text: version not found",
                extra={
                    "document_version_id": str(document_version_id),
                    "segment_id": segment_id,
                },
            )
            return None

        doc_id = version.document_id

        try:
            chunks = await reader.load_segment(
                doc_id=doc_id,
                segment_id=segment_id,
                levels=normalized_levels,
                version_id=document_version_id,
            )
        except Exception as e:
            logger.warning(
                "DocumentContentService.get_segment_text: failed to load segment chunks",
                extra={
                    "document_id": str(doc_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment_id,
                    "levels": normalized_levels,
                    "error": str(e),
                },
            )
            return None

        if not chunks:
            logger.info(
                "DocumentContentService.get_segment_text: no chunks for segment",
                extra={
                    "document_id": str(doc_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment_id,
                    "levels": normalized_levels,
                },
            )
            return None

        return join_chunk_texts(chunks, max_chars)

    # -------------------------------------------------------------------------
    # Публичные методы — Этап 6: semantic layer (legal units + evidence bundles)
    # -------------------------------------------------------------------------

    async def get_legal_units(
        self,
        doc_id: uuid.UUID,
        *,
        primary_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Вернуть список legal units из legal_units_v1.json.

        Для непрофессионального программиста:
        - legal_units_v1.json создаётся при chunking (Этап 5, dual-write).
        - Ссылка хранится в DocumentSegment.segment_meta["legal_units_ref"].
        - Каждый unit — это dict с полями: unit_id, title, unit_type,
          clause_function, topic_tags, citability, cross_refs и т.д.
        - Если артефакт отсутствует (старый документ / dual-write не выполнен)
          — возвращаем пустой список без ошибки.

        Параметры:
        - doc_id:       UUID документа
        - primary_only: если True, берём units только из primary сегмента;
                        если False — из всех сегментов.

        Возвращает:
        - Список dict-ов из LegalUnit.to_dict() в порядке page_start.
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            logger.warning(
                "DocumentContentService.get_legal_units: no latest version",
                extra={"doc_id": str(doc_id)},
            )
            return []

        seg_repo = DocumentSegmentRepository(self.session)
        segments = await seg_repo.list_by_version(version.id)

        if not segments:
            logger.warning(
                "DocumentContentService.get_legal_units: no segments found",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                },
            )
            return []

        return await load_legal_units_from_segments(
            segments=segments,
            artifact_store=self._artifact_store,
            doc_id=doc_id,
            primary_only=primary_only,
            logger=logger,
        )

    async def get_evidence_bundle(
        self,
        doc_id: uuid.UUID,
        profile_id: str,
        *,
        primary_only: bool = True,
    ) -> dict[str, Any]:
        """
        Построить EvidenceBundle для конкретного check по profile_id.

        Для непрофессионального программиста:
        - Детектор вызывает этот метод с именем профиля, например
          "governing_law_check" или "liability_cap_check".
        - Метод читает legal units, восстанавливает LegalUnit объекты,
          и строит EvidenceBundle через EvidenceBundleBuilder.
        - EvidenceBundle содержит отобранные primary + supporting units
          которые релевантны для данного check.
        - Если legal units недоступны или profile не найден —
          возвращает пустой bundle dict без ошибки.

        Параметры:
        - doc_id:       UUID документа
        - profile_id:   ID retrieval profile ("governing_law_check" и т.д.)
        - primary_only: читать units только из primary сегмента

        Возвращает:
        - dict из EvidenceBundle.to_dict() + поле "units" с текстами primary units.
        """
        # Импортируем здесь чтобы не создавать circular dependency на уровне модуля
        from playbook.retrieval_profiles import get_profile

        from engine.content.evidence_bundle_builder import EvidenceBundleBuilder

        profile = get_profile(profile_id)
        if profile is None:
            logger.warning(
                "DocumentContentService.get_evidence_bundle: profile not found",
                extra={
                    "doc_id": str(doc_id),
                    "profile_id": profile_id,
                },
            )
            return build_profile_not_found_result(profile_id)

        units_raw = await self.get_legal_units(doc_id, primary_only=primary_only)

        if not units_raw:
            logger.info(
                "DocumentContentService.get_evidence_bundle: no legal units available",
                extra={
                    "doc_id": str(doc_id),
                    "profile_id": profile_id,
                },
            )
            return build_no_legal_units_result(
                query_topic=profile.query_topic,
                required_topics=list(profile.required_topics),
            )

        legal_units = restore_legal_units(
            units_raw=units_raw,
            doc_id=doc_id,
            logger=logger,
        )

        builder = EvidenceBundleBuilder()
        bundle = builder.build(units=legal_units, profile=profile)

        logger.info(
            "DocumentContentService.get_evidence_bundle: bundle built",
            extra={
                "doc_id": str(doc_id),
                "profile_id": profile_id,
                "query_topic": profile.query_topic,
                "primary_count": len(bundle.primary_units),
                "supporting_count": len(bundle.supporting_units),
                "confidence": bundle.confidence,
                "missing_topics": bundle.missing_topics,
            },
        )

        result = bundle.to_dict()
        result["units"] = serialize_primary_units_for_bundle(bundle.primary_units)
        return result
