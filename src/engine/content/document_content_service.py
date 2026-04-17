# src/engine/content/document_content_service.py

"""
DocumentContentService v3: фасад над чанками и (legacy) clause tree + layout.


- Для checks читаем готовые snapshot'ы чанков (CHUNKS v2).
- Clause tree + layout используем как legacy‑путь / для вспомогательных задач
  (header/snippet, on-the-fly построение чанков).
- Clause tree + layout используем как fallback / для вспомогательных задач
  (header/snippet, on-the-fly построение чанков).


Простыми словами:


- В MinIO есть два типа артефактов:
  1) layout (text layout) — список маленьких текстовых кусочков (elements);
  2) clause tree — структура документа (пункты, подпункты, их иерархия).


- Этот сервис:
  - читает clause tree и layout по ссылкам из последней DocumentVersion;
  - передаёт их в чистые helper'ы:
      * ClauseTreeBuilder — строит клауза-чанки;
      * chunking.* — режет текст на под-чанки, строит section-чанки, summary;
  - отдаёт:
    * чанки по листовым клаузам (для проверок/LLM/эмбеддингов),
    * sized-чанки (под-чанки нормированного размера),
    * иерархию section/clause/subclause,
    * header + snippet для классификаторов.


- Сервис НИЧЕГО не кэширует между задачами Celery:
  - на каждый вызов ему дают свежую AsyncSession,
  - он сам читает нужные JSON из MinIO.
"""


from __future__ import annotations


import uuid
from typing import Any, Dict, List, Optional, Tuple


from sqlalchemy.ext.asyncio import AsyncSession


from db.models.document import DocumentVersion
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from storage.artifact_store import ArtifactStore


from engine.retrieval.tokenization import count_tokens
from engine.retrieval.models import RetrievalChunk
from engine.content.clause_tree_builder import ClauseTreeBuilder
from engine.content.chunking import (
    build_chunk_summary,
    build_section_chunks_from_clauses,
    split_text_to_sized_chunks,
)
from core.logging import get_logger
from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2


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
            "clause_uid": null | str,
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
        * ClauseTreeBuilder — обход clause tree;
        * chunking.* — сплит текста и иерархия чанков.
    - Никаких глобальных синглтонов и кэшей здесь нет.
      Каждый воркер создаёт этот сервис в рамках одного UnitOfWork (db_uow).
    """


    def __init__(
        self,
        session: AsyncSession,
        storage_client: ClauseTreeStorageClientProtocol | None = None,
        layout_client: LayoutStorageClient | None = None,
    ) -> None:
        self.session = session
        self.versions = DocumentVersionRepository(session)
        self.documents = DocumentRepository(session)
        self.storage = storage_client or ClauseTreeStorageClient()
        self.layout_storage = layout_client or LayoutStorageClient()
        # Внутренний ArtifactStore для чтения v2 snapshot'ов чанков.
        self._artifact_store = ArtifactStore()


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
        ВАЖНО:
        - Это legacy-путь (CHUNKS v1), используется для:
        * документов без готовых snapshot'ов чанков;
        * вспомогательных задач (debug, header/snippet и т.п.).
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
    # Вспомогательный расчёт position_ratio
    # -------------------------------------------------------------------------


    def _calc_position_ratio(
        self,
        start_page: int | None,
        end_page: int | None,
        total_pages: int | None,
    ) -> float | None:
        """
        Посчитать нормализованную позицию чанка в документе.


        Для непрофессионального программиста:
        - Если знаем страницу(ы) чанка и общее число страниц,
          считаем "середину" чанка и делим на длину документа.
        - Получаем число от 0.0 до 1.0:
            ~0.0  — начало документа,
            ~0.5  — середина,
            ~1.0  — конец.
        """
        if not total_pages or total_pages <= 0:
            return None


        if start_page is None and end_page is None:
            return None


        s = start_page if isinstance(start_page, int) else end_page
        e = end_page if isinstance(end_page, int) else start_page
        if s is None or e is None:
            return None


        mid = (s + e) / 2.0
        ratio = mid / float(total_pages)
        if ratio < 0.0:
            return 0.0
        if ratio > 1.0:
            return 1.0
        return ratio


    # -------------------------------------------------------------------------
    # Внутренний helper: загрузка чанков из snapshot'а (legacy + v2)
    # -------------------------------------------------------------------------


    async def _load_chunks_from_snapshot(
        self,
        doc_id: uuid.UUID,
        levels: list[str],
    ) -> list[dict[str, Any]]:
        """
        Прочитать чанки из сохранённых v2 snapshot'ов.


        ВАЖНО:
        - Используется только CHUNKS v2
        (file manifest + segment snapshots).
        - Legacy v1 chunk snapshot (исторический путь, оставлен только для контекста миграции)
        больше не читается.
        - Если v2-артефакты отсутствуют, невалидны или reader
        падает, возвращаем пустой список.
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
        - Сканируем первые несколько страниц (обычно 1–2).
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


        # Фильтруем только первые max_pages страниц
        header_elements: List[Dict[str, Any]] = []
        for el in elements:
            page = el.get("page")
            if not isinstance(page, int) or page > max_pages:
                continue


            text = (el.get("text") or "").strip()
            if not text:
                continue


            upper = text.upper()


            # Стоп‑сигналы: оглавление или явный крупный раздел
            if "TABLE OF CONTENTS" in upper or "СОДЕРЖАНИЕ" in upper:
                break


            # Примитивная эвристика: если строка похожа на раздел 1./1.1 и т.п.,
            # считаем, что шапка закончилась.
            import re


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
        - Берём layout последней версии документа (layout_primary_sanitized_ref
          или layout_primary_ref — единственный source of truth в v2).
        - Пропускаем первые skip_pages страниц: там обычно шапка, реквизиты,
          оглавление — то, что уже отдаёт get_title_and_preamble().
        - Собираем текст со следующих страниц, отбрасывая слишком короткие
          элементы (колонтитулы, номера страниц и т.п.).
        - Возвращаем один текстовый блок для L3 (эмбеддинги) и L4 (LLM).

        Почему не clause tree:
        - clause tree — legacy-артефакт (CHUNKS v1), может отсутствовать
          у новых документов, обработанных пайплайном v2.
        - layout всегда присутствует после Stage 3 (extract), поэтому
          этот метод надёжно работает для всех документов.

        Параметры:
        - skip_pages     : сколько первых страниц пропустить (шапка документа).
        - max_length     : максимальная длина сниппета в символах.
        - min_element_len: минимальная длина элемента, чтобы включить его
                           в сниппет (отсекает колонтитулы / номера страниц).
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

        parts: List[str] = []
        total_len = 0

        for el in elements:
            # Пропускаем шапочные страницы — их уже даёт get_title_and_preamble().
            page = el.get("page")
            if isinstance(page, int) and page <= skip_pages:
                continue

            text = (el.get("text") or "").strip()

            # Отсекаем слишком короткие строки: колонтитулы, номера страниц,
            # одиночные буквы и т.п.
            if len(text) < min_element_len:
                continue

            parts.append(text)
            total_len += len(text)

            # Как только накопили достаточно текста — останавливаемся,
            # чтобы не передавать в LLM/эмбеддинги лишнее.
            if total_len >= max_length:
                break

        if not parts:
            logger.info(
                "get_snippet_from_layout: no body elements found after skip_pages",
                extra={"doc_id": str(doc_id), "skip_pages": skip_pages},
            )
            return None

        snippet = "\n\n".join(parts).strip()

        # Финальная обрезка на случай, если последний элемент немного
        # превысил лимит.
        if len(snippet) > max_length:
            snippet = snippet[:max_length]

        return snippet or None


    async def get_chunks(self, doc_id: uuid.UUID) -> List[Dict[str, Any]]:
        """
        Построить чанки для Retrieval/Checks:


        - один чанк на каждую листовую клаузу в clause tree;
        - текст чанка — реальный текст клаузы, собранный по element_ids
          из layout (sanitized/raw);
        - если clause tree отсутствует или layout недоступен, вернуть один
          "пустой" чанк, чтобы пайплайн не падал.


        ВАЖНО:
        - Это legacy-путь (CHUNKS v1), используется для:
        * документов без готовых snapshot'ов чанков;
        * вспомогательных задач (debug, header/snippet и т.п.).


        Для непрофессионального программиста:
        - "чанк" = кусок текста договора, обычно один пункт,
          который дальше анализируют на риски.
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            logger.warning(
                "DocumentContentService.get_chunks: no latest version, returning empty list",
                extra={"doc_id": str(doc_id)},
            )
            return []


        tree = await self._load_clause_tree(version)
        layout = await self._load_layout(version)


        if not tree or not layout:
            logger.warning(
                "DocumentContentService.get_chunks: missing clause tree or layout, returning empty list",
                extra={
                    "doc_id": str(doc_id),
                    "has_tree": bool(tree),
                    "has_layout": bool(layout),
                    "clause_tree_ref": getattr(version, "clause_tree_ref", None),
                    "layout_primary_ref": getattr(version, "layout_primary_ref", None),
                    "layout_primary_sanitized_ref": getattr(
                        version, "layout_primary_sanitized_ref", None
                    ),
                },
            )
            return []


        leaf_chunks = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=doc_id,
            tree=tree,
            layout=layout,
        )


        if not leaf_chunks:
            logger.warning(
                "DocumentContentService.get_chunks: clause tree produced no leaf chunks, returning empty list",
                extra={
                    "doc_id": str(doc_id),
                    "clause_tree_ref": getattr(version, "clause_tree_ref", None),
                    "layout_primary_ref": getattr(version, "layout_primary_ref", None),
                    "layout_primary_sanitized_ref": getattr(
                        version, "layout_primary_sanitized_ref", None
                    ),
                },
            )
            return []


        # Пытаемся достать общее число страниц из layout.metadata
        total_pages: int | None = None
        layout_meta = layout.get("metadata") or {}
        # возможные ключи: page_count, pages и т.п.
        for key in ("page_count", "pages", "num_pages", "total_pages"):
            value = layout_meta.get(key)
            if isinstance(value, int) and value > 0:
                total_pages = value
                break


        # Пробрасываем информацию о language_filter / degraded из layout в метаданные чанков.
        lf_meta = (layout_meta.get("language_filter") or {}) if isinstance(layout_meta, dict) else {}
        lf_degraded = lf_meta.get("degraded")
        lf_reason = lf_meta.get("degraded_reason")
        lf_target_lang = lf_meta.get("target_language")


        if lf_degraded is not None or lf_target_lang:
            for ch in leaf_chunks:
                meta = ch.get("metadata") or {}
                lf = dict(meta.get("language_filter") or {})
                if lf_target_lang is not None and "target_language" not in lf:
                    lf["target_language"] = lf_target_lang
                if lf_degraded is not None and "degraded" not in lf:
                    lf["degraded"] = bool(lf_degraded)
                if lf_reason is not None and "degraded_reason" not in lf:
                    lf["degraded_reason"] = lf_reason
                if lf:
                    meta["language_filter"] = lf
                    ch["metadata"] = meta


        # Добавляем position_ratio для каждого листового чанка (если можем)
        if total_pages:
            for ch in leaf_chunks:
                meta = ch.get("metadata") or {}
                start_page = meta.get("start_page")
                end_page = meta.get("end_page")
                pos = self._calc_position_ratio(start_page, end_page, total_pages)
                if pos is not None:
                    meta["position_ratio"] = pos
                    ch["metadata"] = meta


        return leaf_chunks


    async def get_header_and_snippet(
        self,
        doc_id: uuid.UUID,
        max_snippet_len: int = 1500,
        max_leaf_clauses: int = 3,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Вернуть:


        - header_text: заголовки верхнего уровня (обычно level 1) —
          для L2 классификатора;
        - snippet_text: текст первых нескольких листовых клауз —
          для L3 (эмбеддинги) и L4 (LLM).


        ВАЖНО:
        - Это legacy-путь (CHUNKS v1), используется для:
        * документов без готовых snapshot'ов чанков;
        * вспомогательных задач (debug, header/snippet и т.п.).


        Важно:
        - snippet собирается по тем же правилам, что и чанки:
          по element_ids из clause tree, через layout.
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            return None, None


        tree = await self._load_clause_tree(version)
        layout = await self._load_layout(version)


        if not tree or not layout:
            return None, None


        # Header: нормализованная шапка (title + преамбула) из layout.
        header_text = await self.get_title_and_preamble(doc_id)


        # Листовые клаузы — используем тот же ClauseTreeBuilder.
        leaf_chunks = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=doc_id,
            tree=tree,
            layout=layout,
        )


        if not leaf_chunks:
            return header_text, None


        # Берём первые max_leaf_clauses клауз.
        leaf_chunks = leaf_chunks[:max_leaf_clauses]


        # --- Микрополитика длины сниппета ---
        MIN_CLAUSE_LEN = 80      # минимум символов для "осмысленной" клаузы
        EXTRA_CLAUSES = 5        # сколько максимум клауз можно взять в сниппет


        # Посчитаем суммарную длину первых двух клауз
        first_two = leaf_chunks[:2]
        first_two_len = sum(len(ch.get("text") or "") for ch in first_two)


        # Если короткие — расширяем окно до EXTRA_CLAUSES (если они есть)
        if first_two_len < MIN_CLAUSE_LEN:
            extra_leaf_chunks = leaf_chunks
            if len(extra_leaf_chunks) < EXTRA_CLAUSES:
                pass
            leaf_chunks = extra_leaf_chunks[:EXTRA_CLAUSES]


        # Собираем текст сниппета: клаузы разделяем двойным переводом строки,
        # чтобы модель видела границы пунктов.
        texts_for_snippet: List[str] = []
        for ch in leaf_chunks:
            text = (ch.get("text") or "").strip()
            if text:
                texts_for_snippet.append(text)


        snippet_text = "\n\n".join(texts_for_snippet).strip()


        if snippet_text and len(snippet_text) > max_snippet_len:
            snippet_text = snippet_text[:max_snippet_len]


        return header_text, (snippet_text or None)


    async def _get_clause_chunks_as_retrieval(
        self,
        doc_id: uuid.UUID,
    ) -> list[RetrievalChunk]:
        """
        Внутренний адаптер: get_chunks -> список RetrievalChunk с kind="clause".


        Для непрофессионального программиста:
        - Мы берём уже готовые клауза-чанки (dict) из get_chunks();
        - Превращаем каждый в объект RetrievalChunk с нормальным "паспортом";
        - В дальнейшем retrieval / LLM / checks будут работать именно с этим типом.
        """
        raw_chunks = await self.get_chunks(doc_id)


        retrieval_chunks: list[RetrievalChunk] = []
        for ch in raw_chunks:
            text = (ch.get("text") or "").strip()
            meta = ch.get("metadata") or {}
            if not text:
                continue


            rc = RetrievalChunk(
                id=str(ch.get("id") or f"{doc_id}:clause"),
                doc_id=meta.get("doc_id") or str(doc_id),
                kind="clause",
                clause_uid=meta.get("clause_uid"),
                level=meta.get("level"),
                text=text,
                token_count=meta.get("token_count") or count_tokens(text),
                path_titles=list(meta.get("path_titles") or []),
                start_page=meta.get("start_page"),
                end_page=meta.get("end_page"),
                element_ids=[str(e) for e in meta.get("element_ids") or []],
                summary=meta.get("summary"),
                meta={
                    k: v
                    for k, v in meta.items()
                    if k
                    not in {
                        "doc_id",
                        "clause_uid",
                        "level",
                        "path_titles",
                        "start_page",
                        "end_page",
                        "element_ids",
                        "token_count",
                        "summary",
                    }
                },
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
        Внутренний адаптер: get_sized_chunks -> список RetrievalChunk с kind="subclause".


        Для непрофессионального программиста:
        - get_sized_chunks уже умеет строить нормализованные под-чанки
          (subclause) в формате dict;
        - здесь мы аккуратно упаковываем их в RetrievalChunk, не меняя
          внешний интерфейс get_sized_chunks (он по-прежнему возвращает dict).
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


            rc = RetrievalChunk(
                id=str(ch.get("id") or f"{doc_id}:subclause"),
                doc_id=meta.get("doc_id") or str(doc_id),
                kind="subclause",
                clause_uid=meta.get("clause_uid"),
                level=meta.get("level"),
                text=text,
                token_count=meta.get("token_count") or count_tokens(text),
                path_titles=list(meta.get("path_titles") or []),
                start_page=meta.get("start_page"),
                end_page=meta.get("end_page"),
                element_ids=[str(e) for e in meta.get("element_ids") or []],
                summary=meta.get("summary"),
                meta={
                    k: v
                    for k, v in meta.items()
                    if k
                    not in {
                        "doc_id",
                        "clause_uid",
                        "level",
                        "path_titles",
                        "start_page",
                        "end_page",
                        "element_ids",
                        "token_count",
                        "summary",
                    }
                },
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
        Построить НОРМАЛИЗОВАННЫЕ чанки поверх листовых клауз.


        Для непрофессионального пользователя:
        - сначала каждая листовая клауза превращается в один крупный чанк (get_chunks);
        - затем мы берём эти большие куски и аккуратно делим их
          на более мелкие части по предложениям и абзацам;
        - цель: чтобы каждый чанк был удобного размера для нейросети,
          примерно около target_tokens, но не больше max_tokens;
        - небольшое перекрытие (overlap_ratio) нужно, чтобы смысл не терялся
          на стыках чанков: часть текста повторяется в соседнем чанке.


        ВАЖНО:
        - Это legacy-путь (CHUNKS v1), используется для:
        * документов без готовых snapshot'ов чанков;
        * вспомогательных задач (debug, header/snippet и т.п.).


        На выходе:
        - возвращается список словарей с полями:
          * "id" — уникальный идентификатор чанка,
          * "text" — текст чанка,
          * "metadata" — служебные данные (пункт договора, страницы, путь в структуре и т.п.).
        """


        # Политика длины клаузы:
        # - короткие клаузы (<= SHORT_CLAUSE_MAX_TOKENS) не режем вообще;
        # - очень длинные (>= LONG_CLAUSE_MIN_TOKENS) режем;
        # - средние оставляем целиком, чтобы не дробить нормальные пункты.
        SHORT_CLAUSE_MAX_TOKENS = int(target_tokens * 0.9)   # ~270 при target=300
        LONG_CLAUSE_MIN_TOKENS = int(max_tokens * 1.2)       # ~960 при max=800


        base_chunks = await self.get_chunks(doc_id)
        sized: List[Dict[str, Any]] = []


        total_pages: int | None = None
        for base in base_chunks:
            meta = base.get("metadata") or {}
            pos = meta.get("position_ratio")
            if pos is not None:
                total_pages = None
                break


        for base in base_chunks:
            text = base.get("text") or ""
            metadata = base.get("metadata") or {}


            if not text.strip():
                continue


            clause_uid = metadata.get("clause_uid")
            level = metadata.get("level")
            path_titles = metadata.get("path_titles") or []
            start_page = metadata.get("start_page")
            end_page = metadata.get("end_page")
            element_ids = metadata.get("element_ids") or []


            clause_token_count = count_tokens(text)


            if "position_ratio" in metadata:
                position_ratio = metadata.get("position_ratio")
            elif total_pages:
                position_ratio = self._calc_position_ratio(start_page, end_page, total_pages)
            else:
                position_ratio = None


            def _append_whole_clause_chunk() -> None:
                chunk_id = f"{doc_id}:{clause_uid or 'full'}:0"
                sized.append(
                    {
                        "id": chunk_id,
                        "text": text,
                        "metadata": {
                            "doc_id": str(doc_id),
                            "clause_uid": clause_uid,
                            "title": metadata.get("title"),
                            "level": level,
                            "path_titles": path_titles,
                            "start_page": start_page,
                            "end_page": end_page,
                            "element_ids": element_ids,
                            "token_count": clause_token_count,
                            "position_ratio": position_ratio,
                        },
                    }
                )


            if clause_token_count <= SHORT_CLAUSE_MAX_TOKENS:
                _append_whole_clause_chunk()
                continue


            if SHORT_CLAUSE_MAX_TOKENS < clause_token_count < LONG_CLAUSE_MIN_TOKENS:
                _append_whole_clause_chunk()
                continue


            sub_texts = split_text_to_sized_chunks(
                text=text,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
            )


            if not sub_texts:
                _append_whole_clause_chunk()
                continue


            for sub_idx, sub_text in enumerate(sub_texts):
                if not sub_text.strip():
                    continue


                sub_token_count = count_tokens(sub_text)
                chunk_id = f"{doc_id}:{clause_uid or 'full'}:{sub_idx}"


                sub_metadata = {
                    "doc_id": str(doc_id),
                    "clause_uid": clause_uid,
                    "title": metadata.get("title"),
                    "level": level,
                    "path_titles": path_titles,
                    "start_page": start_page,
                    "end_page": end_page,
                    "element_ids": element_ids,
                    "token_count": sub_token_count,
                    "position_ratio": position_ratio,
                }


                sized.append(
                    {
                        "id": chunk_id,
                        "text": sub_text,
                        "metadata": sub_metadata,
                    }
                )


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


        Для непрофессионального программиста:
        - section: крупные разделы договора (объединённые клаузы по заголовкам).
        - clause: исходные листовые клаузы (как в get_chunks()).
        - subclause: нормализованные под-чанки внутри клауз (как в get_sized_chunks()).


        ВАЖНО:
        - Внешний формат остаётся таким же, как был раньше:
            {
                "section": [ {id, text, metadata}, ... ],
                "clause":  [ {id, text, metadata}, ... ],
                "subclause": [ {id, text, metadata}, ... ],
            }
        - Внутри мы уже работаем с RetrievalChunk, чтобы иметь единый "паспорт"
          для всех уровней.
        """
        clause_chunks_rc = await self._get_clause_chunks_as_retrieval(doc_id)
        sub_chunks_rc = await self._get_sized_chunks_as_retrieval(
            doc_id=doc_id,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )


        clause_chunks_legacy = [rc.to_legacy_dict() for rc in clause_chunks_rc]
        section_chunks_legacy = build_section_chunks_from_clauses(
            doc_id=str(doc_id),
            clause_chunks=clause_chunks_legacy,
            max_tokens=1200,
        )


        def _with_summary_rc(chunks: List[RetrievalChunk]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for rc in chunks:
                if not rc.summary:
                    rc.summary = build_chunk_summary(rc.path_titles, rc.text)
                out.append(rc.to_legacy_dict())
            return out


        return {
            "section": section_chunks_legacy,
            "clause": _with_summary_rc(clause_chunks_rc),
            "subclause": _with_summary_rc(sub_chunks_rc),
        }


    async def get_retrieval_chunks_for_checks(
        self,
        doc_id: uuid.UUID,
        levels: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Удобный фасад для CheckRunner:
        вернуть плоский список чанков для checks.


        По умолчанию:
        - subclause: нормализованные под-чанки,
        - section: крупные разделы.


        ВАЖНО:
        - В V2_ONLY режиме читаем чанки только из CHUNKS v2 snapshot'ов.
        - Если snapshot отсутствует или повреждён, возвращаем пустой список.
        - On-the-fly legacy fallback через clause tree/layout больше не используется
        в основном checks path.
        """
        if levels is None:
            levels = ["subclause", "section"]


        snapshot_chunks = await self._load_chunks_from_snapshot(doc_id, levels)
        if snapshot_chunks:
            return snapshot_chunks


        logger.warning(
            "DocumentContentService.get_retrieval_chunks_for_checks: "
            "no v2 chunk snapshots available, returning empty list",
            extra={
                "doc_id": str(doc_id),
                "levels": levels,
            },
        )
        return []
    

    
    
    

    