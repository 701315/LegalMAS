# src/engine/content/document_content_service.py

"""
DocumentContentService v2: выдаёт текстовые чанки и фрагменты
для Runner / HybridClassifier / CheckExecutor на основе clause tree + layout.

Простыми словами:

- В MinIO есть два типа артефактов:
  1) layout (text layout) — список маленьких текстовых кусочков (elements);
  2) clause tree — структура документа (пункты, подпункты, их иерархия).

- Этот сервис:
  - читает clause tree и layout по ссылкам из последней DocumentVersion;
  - собирает полный текст каждого пункта договора по element_ids;
  - отдаёт:
    * чанки по листовым клаузам (для проверок/LLM/эмбеддингов),
    * header (заголовки верхнего уровня) для L2,
    * snippet (первые несколько пунктов) для L3/L4.

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
    - Никаких глобальных синглтонов и кэшей здесь нет.
      Каждый воркер создаёт этот сервис в рамках одного UnitOfWork (db_uow).

    Что он умеет:

    - get_chunks(doc_id):
        вернуть список чанков по листовым клаузам:
          {
            "id": "<doc_id>:<clause_uid>",
            "text": "<полный текст клаузы>",
            "metadata": {
              "doc_id": ...,
              "clause_uid": ...,
              "title": ...,
              "level": ...,
              "start_page": ...,
              "end_page": ...,
              "element_ids": [...],
            }
          }

    - get_header_and_snippet(doc_id):
        вернуть:
          * header_text: заголовки верхнего уровня (для L2),
          * snippet_text: текст первых нескольких листовых клауз (для L3/L4).
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

    @staticmethod
    def _extract_root_children(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Извлечь список узлов верхнего уровня из clause tree JSON.

        Формат ClauseTree.to_dict():
          {
            "document_id": "...",
            "root": [ {...}, {...} ],
            ...
          }

        На всякий случай поддерживаем и формат:
          { "root": { "children": [ {...}, ... ] } }
        """
        raw_root = tree.get("root")

        if isinstance(raw_root, list):
            return raw_root

        if isinstance(raw_root, dict):
            children = raw_root.get("children")
            if isinstance(children, list):
                return children

        return []

    @staticmethod
    def _build_element_index(layout: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Построить индекс element_id → элемент layout'а.

        Это ускоряет сбор текста клаузы: вместо линейного поиска по всему
        списку elements мы обращаемся к нужному элементу напрямую по ключу.

        Формат элемента (см. build_text_layout_raw):
          {
            "element_id": str,
            "type": "heading" | "text" | "listitem",
            "text": str,
            "page": int,
            ...
          }
        """
        elements = layout.get("elements") or []
        index: Dict[str, Dict[str, Any]] = {}
        for el in elements:
            el_id = el.get("element_id")
            if el_id:
                index[el_id] = el
        return index

    # -------------------------------------------------------------------------
    # Публичные методы
    # -------------------------------------------------------------------------

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

        root_children = self._extract_root_children(tree)
        if not root_children:
            return [
                {
                    "id": f"{doc_id}:full",
                    "text": "",
                    "metadata": {"doc_id": str(doc_id)},
                }
            ]

        element_index = self._build_element_index(layout)

        chunks: List[Dict[str, Any]] = []
        for child in root_children:
            self._collect_leaf_chunks(doc_id, child, element_index, chunks)
        return chunks

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

        root_children = self._extract_root_children(tree)
        if not root_children:
            return None, None

        element_index = self._build_element_index(layout)

        # Header: заголовки верхнего уровня.
        header_titles: List[str] = []
        for child in root_children:
            title = child.get("title")
            if title:
                header_titles.append(title)
        header_text = "\n".join(header_titles) if header_titles else None

        # Snippet: первые несколько листовых клауз.
        leaf_chunks: List[Dict[str, Any]] = []
        for child in root_children:
            self._collect_leaf_chunks(doc_id, child, element_index, leaf_chunks)
            if len(leaf_chunks) >= max_leaf_clauses:
                break

        if not leaf_chunks:
            return header_text, None

        # --- Микрополитика длины сниппета ---
        # Идея:
        # - если первые 1–2 клаузы очень короткие, добавляем больше клауз в сниппет,
        #   чтобы L3/L4 видели достаточно контекста.
        MIN_CLAUSE_LEN = 80       # минимум символов для "осмысленной" клаузы
        EXTRA_CLAUSES = 5         # сколько максимум клауз можно взять в сниппет

        # Посчитаем суммарную длину первых двух клауз
        first_two = leaf_chunks[:2]
        first_two_len = sum(len(ch.get("text") or "") for ch in first_two)

        # Если короткие — расширяем окно до EXTRA_CLAUSES (если они есть)
        if first_two_len < MIN_CLAUSE_LEN:
            # Соберём дополнительные клаузы (если есть в дереве)
            extra_leaf_chunks: List[Dict[str, Any]] = []
            for child in root_children:
                self._collect_leaf_chunks(doc_id, child, element_index, extra_leaf_chunks)
                if len(extra_leaf_chunks) >= EXTRA_CLAUSES:
                    break
            leaf_chunks = extra_leaf_chunks or leaf_chunks

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

    # -------------------------------------------------------------------------
    # Внутренние helper-методы для обхода clause tree
    # -------------------------------------------------------------------------

    def _collect_leaf_chunks(
        self,
        doc_id: uuid.UUID,
        node: Dict[str, Any],
        element_index: Dict[str, Dict[str, Any]],
        out: List[Dict[str, Any]],
    ) -> None:
        """
        Рекурсивно обойти дерево и добавить чанки для всех листовых клауз
        (то есть узлов без children).

        Для каждой листовой клаузы:
        - берём все её element_ids,
        - находим соответствующие элементы в layout,
        - склеиваем их текст в одном чанке.
        """
        children = node.get("children") or []

        if not children:
            clause_uid = node.get("clause_uid")
            element_ids: List[str] = node.get("element_ids") or []

            # Собираем текст клаузы из элементов layout.
            texts: List[str] = []
            pages: List[int] = []

            last_page: int | None = None

            for el_id in element_ids:
                el = element_index.get(el_id)
                if not el:
                    continue

                raw_text = el.get("text") or ""
                text = raw_text.strip()
                if not text:
                    continue

                page = el.get("page")
                if isinstance(page, int):
                    pages.append(page)

                # Если элемент на новой странице — добавляем пустую строку,
                # чтобы L3/L4 видели разрыв.
                if last_page is not None and page is not None and page != last_page:
                    texts.append("")  # это превратится в лишний \n\n при склейке

                texts.append(text)
                last_page = page

            # Склеиваем блоки через двойной перевод строки, чтобы сохранить структуру
            full_text = "\n\n".join(t for t in texts if t).strip()

            start_page = min(pages) if pages else node.get("start_page")
            end_page = max(pages) if pages else node.get("end_page")

            metadata = {
                "doc_id": str(doc_id),
                "clause_uid": clause_uid,
                "title": node.get("title"),
                "level": node.get("level"),
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
            }

            out.append(
                {
                    "id": f"{doc_id}:{clause_uid}",
                    "text": full_text,
                    "metadata": metadata,
                }
            )
            return

        # Если у узла есть дети — спускаемся ниже по дереву.
        for child in children:
            self._collect_leaf_chunks(doc_id, child, element_index, out)
