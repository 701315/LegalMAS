# src/engine/content/chunk_exporter.py

"""
Экспорт документа в виде последовательности чанков в Markdown.

Модуль берёт нормализованные чанки (sized chunks) по документу,
склеивает их в один .md‑файл с понятными заголовками и путями
по структуре документа и сохраняет файл в MinIO.
Этот файл используется в debug-инструментах и для ручной проверки,
как система разрезала документ на части.
"""

from __future__ import annotations

import uuid
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from engine.content.document_content_service import DocumentContentService
from storage.artifact_store import ArtifactStore, ArtifactPath
from db.repositories.document_repo import DocumentRepository


class ChunkExportService:
    """
    Сервис для выгрузки документа в виде последовательности чанков.

    Используется в debug-инструментах и для внутренних проверок:
    собирает все sized-чанки документа в один Markdown-файл и
    сохраняет его в MinIO, возвращая S3-URI.
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
        Собрать все sized-чанки документа в один Markdown-файл и сохранить в MinIO.

        Для непрофессионального пользователя:
        - берём уже посчитанные чанки нормального размера (get_sized_chunks);
        - для каждого чанка добавляем «шапку» с номером, пунктом договора,
          примерным размером и диапазоном страниц;
        - ниже выводим сам текст чанка;
        - в конце каждого чанка ставим разделитель `---`.

        Это нужно, чтобы юрист или аналитик мог глазами увидеть,
        как система разрезала документ на части, и проверить,
        не потерялся ли смысл на стыках чанков.

        Важно:
        - сюда уже должны прийти корректные tenant_id и deal_id,
          обычно их берут из объекта Deal (сделка по документу).

        Возвращается строка вида s3://... — ссылка на файл в хранилище.
        """
        # Для непрофессионального программиста:
        # - DocumentContentService умеет доставать "нормализованные чанки" по документу,
        # - здесь мы просто просим у него готовый список чанков.
        content = DocumentContentService(session=self.db)
        chunks = await content.get_sized_chunks(doc_id)

        if not chunks or not any((ch.get("text") or "").strip() for ch in chunks):
            raise ValueError(f"No sized chunks for document {doc_id}")        

        # Проверяем, что документ существует (на случай расхождений в БД).
        doc = await self.doc_repo.get_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        # Строим человекочитаемый Markdown.
        lines: List[str] = []
        lines.append(f"# Document {doc_id}")
        lines.append("")

        for idx, ch in enumerate(chunks):
            meta = ch.get("metadata") or {}
            clause_uid = meta.get("clause_uid")
            tokens = meta.get("token_count")
            start_page = meta.get("start_page")
            end_page = meta.get("end_page")
            path = meta.get("path_titles") or []

            lines.append(
                f"## CHUNK {idx} "
                f"(clause {clause_uid or '-'}, tokens={tokens}, "
                f"pages {start_page}–{end_page})"
            )
            if path:
                lines.append(f"PATH: {' / '.join(path)}")

            lines.append("")
            lines.append(ch.get("text") or "")
            lines.append("")
            lines.append("---")
            lines.append("")

        md_text = "\n".join(lines)
        data = md_text.encode("utf-8")

        # Для непрофессионального программиста:
        # - ArtifactPath.export строит "правильный" путь в MinIO:
        #   tenants/{tenant_id}/deals/{deal_id}/exports/{doc_id}/{doc_id}__chunks_view.md
        # - tenant_id и deal_id мы уже получили снаружи (из Deal).
        export_path = ArtifactPath.export(
            tenant_id=str(tenant_id),
            deal_id=str(deal_id),
            export_id=str(doc_id),
            filename=f"{doc_id}__chunks_view.md",
        )
        uri = self.store.put_file(export_path, data, content_type="text/markdown")
        return uri
    
    