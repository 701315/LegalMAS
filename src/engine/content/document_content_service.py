# src/engine/content/document_content_service.py

"""
DocumentContentService: предоставляет текстовые чанки и фрагменты
для Runner / HybridClassifier / CheckExecutor на основе clause tree.

Основные задачи:
- загрузить clause tree JSON из хранилища по clause_tree_ref;
- построить чанки по листовым клауза (clause_uid + full_text);
- дать header (заголовки верхнего уровня) и snippet (первые клаузы)
  для L2/L3 классификаторов.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.document import DocumentVersion
from db.repositories.document_version_repo import DocumentVersionRepository
from storage.artifact_store import ArtifactStore


class ClauseTreeStorageClientProtocol:
    """
    Простейший протокол для клиента хранения, который умеет читать JSON
    по URI вида s3://bucket/path/to/file.json.
    """

    async def load_json(self, uri: str) -> dict[str, Any]:
        raise NotImplementedError


class ClauseTreeStorageClient(ClauseTreeStorageClientProtocol):
    """
    Адаптер поверх ArtifactStore, реализующий load_json(uri).
    """

    def __init__(self, store: ArtifactStore | None = None) -> None:
        # ArtifactStore сам подтянет settings (MINIO_*)
        self.store = store or ArtifactStore()

    async def load_json(self, uri: str) -> dict[str, Any]:
        # ArtifactStore.get_json уже умеет принимать полный s3://... путь
        # и сам вырезает префикс s3://{bucket}/
        # Обёртка async нужна, чтобы не менять интерфейс DocumentContentService.
        from anyio.to_thread import run_sync

        def _get() -> dict[str, Any]:
            return self.store.get_json(uri)

        return await run_sync(_get)


class DocumentContentService:
    def __init__(
        self,
        session: AsyncSession,
        storage_client: ClauseTreeStorageClientProtocol,
    ) -> None:
        self.session = session
        self.versions = DocumentVersionRepository(session)
        self.storage = storage_client

    async def _get_latest_version(self, doc_id: uuid.UUID) -> DocumentVersion | None:
        """
        Получить последнюю версию документа (по version_num).
        """
        return await self.versions.get_latest(doc_id)

    async def _load_clause_tree(self, doc_id: uuid.UUID) -> dict[str, Any] | None:
        """
        Загрузить clause tree JSON по document_id.
        """
        version = await self._get_latest_version(doc_id)
        if not version or not version.clause_tree_ref:
            return None

        return await self.storage.load_json(version.clause_tree_ref)

    async def get_chunks(self, doc_id: uuid.UUID) -> list[dict[str, Any]]:
        """
        Построить чанки для Retrieval/Checks:
        - один чанк на каждую листовую клаузу в clause tree;
        - если clause tree отсутствует, вернуть список из одного
          пустого чанка, чтобы не ломать пайплайн.
        """
        tree = await self._load_clause_tree(doc_id)
        if not tree:
            # Fallback: один пустой чанк, чтобы CheckExecutor не упал.
            return [
                {
                    "id": f"{doc_id}:full",
                    "text": "",
                    "metadata": {
                        "doc_id": str(doc_id),
                    },
                }
            ]

        root = tree.get("root")
        if not root:
            return [
                {
                    "id": f"{doc_id}:full",
                    "text": "",
                    "metadata": {
                        "doc_id": str(doc_id),
                    },
                }
            ]

        chunks: list[dict[str, Any]] = []
        self._collect_leaf_chunks(doc_id, root, chunks)
        return chunks

    def _collect_leaf_chunks(
        self,
        doc_id: uuid.UUID,
        node: dict[str, Any],
        out: list[dict[str, Any]],
    ) -> None:
        """
        Рекурсивно обойти дерево и добавить чанки для всех листовых клауз
        (node.children == []).
        """
        children = node.get("children") or []

        if not children:
            clause_uid = node.get("clause_uid")
            full_text = node.get("full_text") or ""
            metadata = {
                "doc_id": str(doc_id),
                "clause_uid": clause_uid,
                "title": node.get("title"),
                "level": node.get("level"),
                "start_page": node.get("start_page"),
                "end_page": node.get("end_page"),
                "element_ids": node.get("element_ids") or [],
            }
            out.append(
                {
                    "id": f"{doc_id}:{clause_uid}",
                    "text": full_text,
                    "metadata": metadata,
                }
            )
            return

        for child in children:
            self._collect_leaf_chunks(doc_id, child, out)

    async def get_header_and_snippet(
        self,
        doc_id: uuid.UUID,
        max_snippet_len: int = 1500,
        max_leaf_clauses: int = 3,
    ) -> tuple[str | None, str | None]:
        """
        Вернуть:
        - header_text: заголовки верхнего уровня (level 1) склеенные построчно;
        - snippet_text: текст первых нескольких листовых клауз, склеенный
          и обрезанный по длине.
        """
        tree = await self._load_clause_tree(doc_id)
        if not tree:
            return None, None

        root = tree.get("root") or {}
        root_children: list[dict[str, Any]] = root.get("children") or []
        if not root_children:
            return None, None

        # Header: заголовки верхнего уровня (level == 1)
        header_titles: list[str] = []
        for child in root_children:
            title = child.get("title")
            if title:
                header_titles.append(title)
        header_text = "\n".join(header_titles) if header_titles else None

        # Snippet: первые несколько листовых клауз в порядке обхода
        leaf_chunks: list[dict[str, Any]] = []
        for child in root_children:
            self._collect_leaf_chunks(doc_id, child, leaf_chunks)
            if len(leaf_chunks) >= max_leaf_clauses:
                break

        snippet_text = " ".join(chunk["text"] for chunk in leaf_chunks).strip()
        if snippet_text and len(snippet_text) > max_snippet_len:
            snippet_text = snippet_text[:max_snippet_len]

        return header_text, (snippet_text or None)
