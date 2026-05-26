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
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.document import DocumentVersion
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2
from core.logging import get_logger
from db.models.document import DocumentVersion
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2
from engine.content.chunk_canonicalization import add_summary, build_sized_chunks_from_leaf
from engine.content.chunking import build_chunk_summary
from engine.content.clause_tree_builder import ClauseTreeBuilder
from engine.retrieval.models import RetrievalChunk
from engine.retrieval.tokenization import count_tokens
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

    async def _get_latest_version(self, doc_id: uuid.UUID) -> Optional[DocumentVersion]:
        """
        Получить последнюю версию документа (по version_num).
        Если версий нет, вернёт None.
        """
        return await self.versions.get_latest(doc_id)

    async def _load_clause_tree(self, version: DocumentVersion) -> Optional[Dict[str, Any]]:
        """
        Legacy-путь для clause tree.

        Используется только для:
        - старых документов без CHUNKS v2 snapshot'ов;
        - вспомогательных задач (header/snippet, debug).
        """
        if not version.clause_tree_ref:
            return None
        return await self.storage.load_json(version.clause_tree_ref)

    async def _load_layout(self, version: DocumentVersion) -> Optional[Dict[str, Any]]:
        """
        Загрузить рабочий layout документа по единому контракту пайплайна.

        Приоритет:
        1) layout_primary_sanitized_ref — основной source of truth после PII;
        2) layout_primary_ref — recovery fallback для случаев, когда PII ещё не выполнен.
        """
        layout_ref = (
            getattr(version, "layout_primary_sanitized_ref", None)
            or getattr(version, "layout_primary_ref", None)
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
        excluded = {
            "doc_id",
            "chunk_kind",
            "node_kind",
            "level",
            "path_titles",
            "start_page",
            "end_page",
            "element_ids",
            "token_count",
            "summary",
        }
        return {k: v for k, v in meta.items() if k not in excluded}

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
    # Публичные методы
    # -------------------------------------------------------------------------

    async def get_title_and_preamble(
        self,
        doc_id: uuid.UUID,
        max_pages: int = 2,
        max_length: int = 1500,
    ) -> Optional[str]:
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

        elements = layout.get("elements") or []
        if not elements:
            return None

        layout_meta = layout.get("metadata") or {}
        total_pages: int | None = None
        for key in ("page_count", "pages", "num_pages", "total_pages"):
            value = layout_meta.get(key)
            if isinstance(value, int) and value > 0:
                total_pages = value
                break

        effective_max_pages = max_pages
        if total_pages is not None:
            effective_max_pages = 2 if total_pages <= 4 else 3

        header_elements: List[Dict[str, Any]] = []
        for el in elements:
            page = el.get("page")
            if not isinstance(page, int) or page > effective_max_pages:
                continue

            text = (el.get("text") or "").strip()
            if not text:
                continue

            upper = text.upper()

            if "TABLE OF CONTENTS" in upper or "СОДЕРЖАНИЕ" in upper:
                break

            if re.match(r"^\d{1,2}(\.\d{1,2})*\.\s+.+", text):
                break

            header_elements.append(el)

        if not header_elements:
            return None

        parts: List[str] = []
        for el in header_elements:
            t = (el.get("text") or "").strip()
            if t:
                parts.append(t)

        full = "\n".join(parts).strip()
        if not full:
            return None

        if len(full) > max_length:
            full = full[:max_length]

        return full or None

    async def get_snippet_from_layout(
        self,
        doc_id: uuid.UUID,
        skip_pages: int = 2,
        max_length: int = 1500,
        min_element_len: int = 40,
    ) -> Optional[str]:
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

        layout_meta = layout.get("metadata") or {}
        total_pages: int | None = None
        for key in ("page_count", "pages", "num_pages", "total_pages"):
            value = layout_meta.get(key)
            if isinstance(value, int) and value > 0:
                total_pages = value
                break

        if total_pages is not None:
            effective_skip_pages = 1 if total_pages <= 4 else 3
            effective_skip_pages = min(effective_skip_pages, max(0, total_pages - 1))
        else:
            effective_skip_pages = skip_pages

        parts: List[str] = []
        total_len = 0

        for el in elements:
            page = el.get("page")
            if isinstance(page, int) and page <= effective_skip_pages:
                continue

            text = (el.get("text") or "").strip()
            if len(text) < min_element_len:
                continue

            parts.append(text)
            total_len += len(text)

            if total_len >= max_length:
                break

        if not parts:
            logger.info(
                "get_snippet_from_layout: no body elements found after effective_skip_pages",
                extra={
                    "doc_id": str(doc_id),
                    "effective_skip_pages": effective_skip_pages,
                    "total_pages": total_pages,
                },
            )
            return None

        snippet = "\n\n".join(parts).strip()
        if len(snippet) > max_length:
            snippet = snippet[:max_length]

        return snippet or None

    async def get_chunks(
        self,
        doc_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
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

        canonical_chunks: List[Dict[str, Any]] = []

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

            meta["doc_id"] = meta.get("doc_id") or str(doc_id)
            meta["chunk_kind"] = "clause"
            meta["token_count"] = meta.get("token_count") or count_tokens(text)

            if "path_titles" in meta:
                meta["path_titles"] = list(meta.get("path_titles") or [])
            if "element_ids" in meta:
                meta["element_ids"] = [str(e) for e in meta.get("element_ids") or []]

            if not meta.get("summary"):
                summary = build_chunk_summary(
                    list(meta.get("path_titles") or []),
                    text,
                )
                if summary:
                    meta["summary"] = summary

            canonical_chunks.append(
                {
                    "id": ch.get("id"),
                    "text": text,
                    "metadata": meta,
                }
            )

        return canonical_chunks

    async def get_header_and_snippet(
        self,
        doc_id: uuid.UUID,
        max_snippet_len: int = 1500,
        max_leaf_clauses: int = 3,
    ) -> Tuple[Optional[str], Optional[str]]:
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

        MIN_CLAUSE_LEN = 80
        EXTRA_CLAUSES = 5

        first_two_len = sum(len(ch.get("text") or "") for ch in leaf_chunks_all[:2])
        if first_two_len < MIN_CLAUSE_LEN:
            leaf_chunks = leaf_chunks_all[:EXTRA_CLAUSES]
        else:
            leaf_chunks = leaf_chunks_all[:max_leaf_clauses]

        texts_for_snippet: List[str] = []
        for ch in leaf_chunks:
            text = (ch.get("text") or "").strip()
            if text:
                texts_for_snippet.append(text)

        snippet_text = "\n\n".join(texts_for_snippet).strip()

        if snippet_text and len(snippet_text) > max_snippet_len:
            snippet_text = snippet_text[:max_snippet_len]
            snippet_text = snippet_text.rsplit(" ", 1)[0].strip()

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
            chunk_kind = meta.get("chunk_kind") or "clause"

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

            rc = RetrievalChunk(
                id=str(ch.get("id")),
                doc_id=meta.get("doc_id") or str(doc_id),
                kind=chunk_kind,
                clause_uid=effective_uid,
                level=meta.get("level"),
                text=text,
                token_count=meta.get("token_count") or count_tokens(text),
                path_titles=list(meta.get("path_titles") or []),
                start_page=meta.get("start_page"),
                end_page=meta.get("end_page"),
                element_ids=[str(e) for e in meta.get("element_ids") or []],
                summary=meta.get("summary"),
                meta=self._build_retrieval_chunk_meta(meta),
            )
            retrieval_chunks.append(rc)

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
            chunk_kind = meta.get("chunk_kind") or "subclause"

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

            rc = RetrievalChunk(
                id=str(ch.get("id")),
                doc_id=meta.get("doc_id") or str(doc_id),
                kind=chunk_kind,
                clause_uid=effective_uid,
                level=meta.get("level"),
                text=text,
                token_count=meta.get("token_count") or count_tokens(text),
                path_titles=list(meta.get("path_titles") or []),
                start_page=meta.get("start_page"),
                end_page=meta.get("end_page"),
                element_ids=[str(e) for e in meta.get("element_ids") or []],
                summary=meta.get("summary"),
                meta=self._build_retrieval_chunk_meta(meta),
            )
            retrieval_chunks.append(rc)

        return retrieval_chunks

    async def get_sized_chunks(
        self,
        doc_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> List[Dict[str, Any]]:
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
    ) -> Dict[str, List[Dict[str, Any]]]:
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

        section_chunks: List[Dict[str, Any]] = []
        clause_chunks: List[Dict[str, Any]] = []
        subclause_chunks: List[Dict[str, Any]] = []

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

            meta["doc_id"] = meta.get("doc_id") or str(doc_id)
            meta["token_count"] = meta.get("token_count") or count_tokens(text)

            if "path_titles" in meta:
                meta["path_titles"] = list(meta.get("path_titles") or [])
            if "element_ids" in meta:
                meta["element_ids"] = [str(e) for e in meta.get("element_ids") or []]

            if not meta.get("summary"):
                summary = build_chunk_summary(
                    list(meta.get("path_titles") or []),
                    text,
                )
                if summary:
                    meta["summary"] = summary

            normalized = {
                "id": ch.get("id"),
                "text": text,
                "metadata": meta,
            }

            if kind == "section":
                meta["chunk_kind"] = "section"
                section_chunks.append(normalized)
            elif kind == "clause":
                meta["chunk_kind"] = "clause"
                clause_chunks.append(normalized)
            elif kind == "subclause":
                meta["chunk_kind"] = "subclause"
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

        levels = [
            lvl.strip().lower()
            for lvl in levels
            if isinstance(lvl, str) and lvl.strip()
        ]
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
            lvl.strip().lower()
            for lvl in levels
            if isinstance(lvl, str) and lvl.strip()
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

        parts: list[str] = []
        total_len = 0
        separator = "\n\n"

        for ch in chunks:
            text = (ch.get("text") or "").strip()
            if not text:
                continue

            sep_len = len(separator) if parts else 0
            remaining = max_chars - total_len - sep_len
            if remaining <= 0:
                break

            if len(text) > remaining:
                text = text[:remaining].rstrip()

            if not text:
                break

            if parts:
                total_len += len(separator)

            parts.append(text)
            total_len += len(text)

        if not parts:
            return None

        segment_text = separator.join(parts).strip()
        return segment_text or None
