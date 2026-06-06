# src/engine/content/chunk_exporter.py

"""
Экспорт документа в виде последовательности retrieval-visible чанков в Markdown.

ВАЖНО:
- chunk-view.md должен отражать ИМЕННО те чанки, которые реально видит retrieval,
  а не on-the-fly re-split поверх clause chunks.
- Поэтому источник истины здесь:
    DocumentContentService.get_retrieval_chunks_for_checks()
- Это устраняет рассинхрон:
    chunk-view != retrieval truth
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.document_repo import DocumentRepository
from engine.content.document_content_service import DocumentContentService
from storage.artifact_store import ArtifactPath, ArtifactStore


class ChunkExportService:
    """
    Сервис для выгрузки документа в виде последовательности retrieval-visible чанков.

    Используется в debug-инструментах и для внутренних проверок:
    собирает чанки, которые реально подаются в retrieval/checks,
    в один Markdown-файл и сохраняет его в MinIO.
    """

    def __init__(self, db: AsyncSession, store: ArtifactStore | None = None) -> None:
        self.db = db
        self.store = store or ArtifactStore()
        self.doc_repo = DocumentRepository(db)

    async def export_sized_chunks_markdown(
        self,
        *,
        doc_id: uuid.UUID,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> str:
        """
        Собрать retrieval-visible chunks документа в один Markdown-файл и сохранить в MinIO.

        ВАЖНО:
        - Раньше здесь использовался get_sized_chunks(), который повторно строил
          subclause chunks on-the-fly из clause chunks.
        - Это приводило к рассинхрону:
            chunk-view.md != реальные retrieval chunks
        - Теперь chunk-view строится напрямую из того же входа,
          который использует CheckRunner / retrieval runtime.

        Для непрофессионального пользователя:
        - для каждого чанка добавляем «шапку»:
          * индекс,
          * тип чанка (section/subclause/...),
          * effective_uid / clause_uid,
          * размер,
          * диапазон страниц,
          * retrieval_safe если есть;
        - ниже выводим текст чанка;
        - в конце каждого чанка ставим разделитель `---`.

        Возвращается строка вида s3://... — ссылка на файл в хранилище.
        """
        content = DocumentContentService(session=self.db)

        # Fix 1:
        # Берём РОВНО тот corpus, который реально используется retrieval/checks.
        # Явно задаём retrieval levels, чтобы chunk-view был retrieval truth.
        chunks = await content.get_retrieval_chunks_for_checks(
            doc_id=doc_id,
            levels=["subclause", "section"],
            filter_unsafe_chunks=False,
        )

        if not chunks or not any((ch.get("text") or "").strip() for ch in chunks):
            raise ValueError(f"No retrieval-visible chunks for document {doc_id}")

        # Проверяем, что документ существует.
        doc = await self.doc_repo.get_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        lines: list[str] = []
        lines.append(f"# Document {doc_id}")
        lines.append("")
        lines.append("> Source: retrieval runtime corpus (`get_retrieval_chunks_for_checks`)")  # noqa: E501
        lines.append("")

        for idx, ch in enumerate(chunks):
            meta = ch.get("metadata") or {}

            # Fix 5:
            # Для v2 canonical chunks основной UID — effective_uid.
            clause_uid = meta.get("effective_uid") or meta.get("clause_uid")
            chunk_kind = meta.get("chunk_kind") or "-"
            tokens = meta.get("token_count")
            start_page = meta.get("start_page")
            end_page = meta.get("end_page")
            retrieval_safe = meta.get("retrieval_safe")
            path = meta.get("path_titles") or []

            header_parts = [
                f"## CHUNK {idx}",
                f"(kind={chunk_kind}",
                f"clause={clause_uid or '-'}",
                f"tokens={tokens}",
                f"pages {start_page}–{end_page}",
            ]

            if retrieval_safe is not None:
                header_parts.append(f"retrieval_safe={retrieval_safe}")

            header = ", ".join(header_parts) + ")"
            lines.append(header)

            if path:
                lines.append(f"PATH: {' / '.join(str(p) for p in path if str(p).strip())}")

            summary = meta.get("summary")
            if summary:
                lines.append(f"SUMMARY: {summary}")

            lines.append("")
            lines.append(ch.get("text") or "")
            lines.append("")
            lines.append("---")
            lines.append("")

        md_text = "\n".join(lines)
        data = md_text.encode("utf-8")

        export_path = ArtifactPath.export(
            tenant_id=str(tenant_id),
            deal_id=str(deal_id),
            export_id=str(doc_id),
            filename=f"{doc_id}__chunks_view.md",
        )
        uri = self.store.put_file(export_path, data, content_type="text/markdown")
        return uri
    
    
