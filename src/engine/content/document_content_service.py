# src/engine/content/document_content_service.py

"""
DocumentContentService v3: тонкий фасад над clause tree + layout.

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
from db.repositories.document_version_repo import DocumentVersionRepository
from storage.artifact_store import ArtifactStore

from engine.retrieval.tokenization import count_tokens
from engine.content.clause_tree_builder import ClauseTreeBuilder
from engine.content.chunking import (
    build_chunk_summary,
    build_section_chunks_from_clauses,
    split_text_to_sized_chunks,
)


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
        self.storage = storage_client or ClauseTreeStorageClient()
        self.layout_storage = layout_client or LayoutStorageClient()

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
        Загрузить clause tree JSON по DocumentVersion.

        Если ссылки нет — вернёт None.
        """
        if not version.clause_tree_ref:
            return None
        return await self.storage.load_json(version.clause_tree_ref)

    async def _load_layout(self, version: DocumentVersion) -> Optional[Dict[str, Any]]:
        """
        Загрузить layout JSON (санитизированный, а если его нет — raw)
        по DocumentVersion.

        Для непрофессионального программиста:
        - Сначала пытаемся использовать sanitized layout (после PII),
          чтобы не светить персональные данные в чанкерах и LLM.
        - Если по каким-то причинам sanitized ещё нет, используем raw layout.
        """
        layout_ref = version.text_layout_sanitized_ref or version.text_layout_raw_ref
        if not layout_ref:
            return None
        return await self.layout_storage.load_json(layout_ref)

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

    async def get_chunks(self, doc_id: uuid.UUID) -> List[Dict[str, Any]]:
        """
        Построить чанки для Retrieval/Checks:

        - один чанк на каждую листовую клаузу в clause tree;
        - текст чанка — реальный текст клаузы, собранный по element_ids
          из layout (sanitized/raw);
        - если clause tree отсутствует или layout недоступен, вернуть один
          "пустой" чанк, чтобы пайплайн не падал.

        Для непрофессионального программиста:
        - "чанк" = кусок текста договора, обычно один пункт,
          который дальше анализируют на риски.
        """
        version = await self._get_latest_version(doc_id)
        if not version:
            return [
                {
                    "id": f"{doc_id}:full",
                    "text": "",
                    "metadata": {"doc_id": str(doc_id)},
                }
            ]

        tree = await self._load_clause_tree(version)
        layout = await self._load_layout(version)

        if not tree or not layout:
            # Нет структуры или текста — возвращаем один "пустой" чанк.
            return [
                {
                    "id": f"{doc_id}:full",
                    "text": "",
                    "metadata": {"doc_id": str(doc_id)},
                }
            ]

        leaf_chunks = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=doc_id,
            tree=tree,
            layout=layout,
        )

        if not leaf_chunks:
            return [
                {
                    "id": f"{doc_id}:full",
                    "text": "",
                    "metadata": {"doc_id": str(doc_id)},
                }
            ]

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
                # На всякий случай можно было бы добавить клаузы из дерева,
                # но сейчас у нас уже есть первые leaf_chunks.
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

    async def get_sized_chunks(
        self,
        doc_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> List[Dict[str, Any]]:
        """
        Построить НОРМАЛИЗОВАННЫЕ чанки поверх листовых клауз.

        Для непрофессионального программиста:
        - get_chunks() возвращает один крупный чанк на каждую листовую клаузу.
        - get_sized_chunks() берёт эти клаузы и, если они слишком длинные,
          аккуратно режет их по предложениям и абзацам.
        - Цель: чтобы каждый чанк был "удобного" размера для эмбеддингов и LLM,
          например около 300 слов, но не больше max_tokens.
        """
        base_chunks = await self.get_chunks(doc_id)

        sized: List[Dict[str, Any]] = []

        for base in base_chunks:
            text = base.get("text") or ""
            metadata = base.get("metadata") or {}

            # Если текста нет — пропускаем такой чанк.
            if not text.strip():
                continue

            clause_uid = metadata.get("clause_uid")
            level = metadata.get("level")
            path_titles = metadata.get("path_titles") or []
            start_page = metadata.get("start_page")
            end_page = metadata.get("end_page")
            element_ids = metadata.get("element_ids") or []

            # Режем текст клаузы на под-чанки.
            sub_texts = split_text_to_sized_chunks(
                text=text,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
            )

            # Если по какой-то причине сплит не сработал — сохраняем исходный чанк.
            if not sub_texts:
                sized.append(
                    {
                        "id": f"{doc_id}:{clause_uid or 'full'}:0",
                        "text": text,
                        "metadata": metadata,
                    }
                )
                continue

            # Собираем под-чанки с отдельными ID, но с той же метадатой.
            for sub_idx, sub_text in enumerate(sub_texts):
                if not sub_text.strip():
                    continue

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
                    "token_count": count_tokens(sub_text),
                }

                sized.append(
                    {
                        "id": chunk_id,
                        "text": sub_text,
                        "metadata": sub_metadata,
                    }
                )

        if not sized:
            return [
                {
                    "id": f"{doc_id}:full",
                    "text": "",
                    "metadata": {"doc_id": str(doc_id)},
                }
            ]

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

        Формат:
        {
            "section": [ {id, text, metadata}, ... ],
            "clause": [ {id, text, metadata}, ... ],
            "subclause": [ {id, text, metadata}, ... ],
        }
        """
        clause_chunks = await self.get_chunks(doc_id)
        sub_chunks = await self.get_sized_chunks(
            doc_id,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )
        section_chunks = build_section_chunks_from_clauses(
            doc_id=str(doc_id),
            clause_chunks=clause_chunks,
            max_tokens=1200,
        )

        def _with_summary(ch_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for ch in ch_list:
                meta = ch.get("metadata") or {}
                path_titles = meta.get("path_titles") or []
                text = ch.get("text") or ""
                if not meta.get("summary"):
                    meta["summary"] = build_chunk_summary(path_titles, text)
                out.append(
                    {
                        "id": ch.get("id"),
                        "text": text,
                        "metadata": meta,
                    }
                )
            return out

        return {
            "section": section_chunks,
            "clause": _with_summary(clause_chunks),
            "subclause": _with_summary(sub_chunks),
        }
    