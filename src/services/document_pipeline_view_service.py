# src/services/document_pipeline_view_service.py

"""
Document pipeline view builder for a single document.

Сервис собирает «срез пайплайна» по одному документу: для текущей версии
подтягивает артефакты из стореджа и БД и упаковывает их в DTO для
frontend‑viewer’а.

Метод build(document_id):
- находит Document и его последнюю DocumentVersion;
- строит список стадий (SOURCE, PRIMARY, EXTRACT, PII, STRUCTURE, CHUNKS),
  каждая со статусом (ready/pending/missing), типом (pdf/layout/structure/chunks),
  базовой мета‑информацией (pages, counts) и lightweight‑превью.

Стадии:
- SOURCE    — исходный файл или сконвертированный PDF (presigned URL для просмотра/скачивания);
- PRIMARY   — одноязычный source после выбора основного языка;
- EXTRACT   — text layout после извлечения (raw или primary), превью по страницам;
- PII       — sanitized layout, основной вход для STRUCTURE/CHUNKS/checks;
- STRUCTURE — дерево секций/пунктов (clause tree), сплющенное в список секций;
- CHUNKS    — материализованные чанки (snapshot или fallback через DocumentContentService)
              с восстановленным текстом документа.

Сервис ничего не изменяет в пайплайне и не перезапускает стадии — он только
читает артефакты и возвращает удобное представление для UI.
"""


from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.document_pipeline_view import (
    ChunkPreviewDTO,
    ChunksPreviewDTO,
    DocumentPipelineViewResponseDTO,
    LayoutPagePreviewDTO,
    LayoutPreviewDTO,
    PdfPreviewDTO,
    PipelineStageCode,
    PipelineStageKind,
    PipelineStageStatus,
    PipelineStageViewDTO,
    StageMetaDTO,
    StructurePreviewDTO,
    StructureSectionPreviewDTO,
)
from core.exceptions import PermanentError, TransientError
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.document_content_service import DocumentContentService
from storage.artifact_store import ArtifactStore


class DocumentPipelineViewService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.ver_repo = DocumentVersionRepository(session)
        self.content_service = DocumentContentService(session=session)
        self.store = ArtifactStore()

    async def build(self, document_id: UUID) -> DocumentPipelineViewResponseDTO:
        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise ValueError("Document not found")

        version = await self.ver_repo.get_latest(document_id)
        if not version:
            raise ValueError("DocumentVersion not found")

        stages: list[PipelineStageViewDTO] = [
            self._build_source_stage(doc, version),
            self._build_primary_stage(doc, version),
            self._build_extract_stage(doc, version),
            self._build_pii_stage(doc, version),
            self._build_structure_stage(doc, version),
            await self._build_chunks_stage(doc, version),
        ]

        return DocumentPipelineViewResponseDTO(
            document_id=str(doc.id),
            document_version_id=str(version.id),
            document_status=doc.status,
            stages=stages,
        )

    def _base_meta(self, doc) -> StageMetaDTO:
        return StageMetaDTO(
            page_count=doc.page_count,
            element_count=None,
            chunk_count=None,
            section_count=None,
            source_file_name=doc.filename,
            mime_type=doc.source_filetype,
        )

    def _status_from_presence(self, artifact_ref: str | None) -> PipelineStageStatus:
        return (
            PipelineStageStatus.ready
            if artifact_ref
            else PipelineStageStatus.pending
        )

    def _build_source_stage(self, doc, version) -> PipelineStageViewDTO:
        artifact_ref = version.converted_pdf_ref or version.original_ref
        if not artifact_ref:
            return PipelineStageViewDTO(
                code=PipelineStageCode.SOURCE,
                title="SOURCE: исходный документ",
                description=(
                    "Исходный документ для обработки: оригинал или PDF после "
                    "конвертации офисного формата."
                ),
                available=False,
                kind=PipelineStageKind.pdf,
                status=PipelineStageStatus.pending,
                artifact_ref=None,
                meta=self._base_meta(doc),
                preview=None,
            )

        try:
            url = self.store.get_presigned_get_url(artifact_ref)
        except PermanentError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.SOURCE,
                title="SOURCE: исходный документ",
                description="Исходный PDF ожидается, но отсутствует в сторедже.",
                available=False,
                kind=PipelineStageKind.pdf,
                status=PipelineStageStatus.missing,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )
        except TransientError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.SOURCE,
                title="SOURCE: исходный документ",
                description="Исходный PDF временно недоступен.",
                available=False,
                kind=PipelineStageKind.pdf,
                status=PipelineStageStatus.pending,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )

        preview = PdfPreviewDTO(
            type="pdf",
            inline_url=url,
            download_url=url,
        )

        return PipelineStageViewDTO(
            code=PipelineStageCode.SOURCE,
            title="SOURCE: исходный документ",
            description=(
                "Исходный документ для обработки: оригинал или PDF после "
                "конвертации офисного формата."
            ),
            available=True,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.ready,
            artifact_ref=artifact_ref,
            meta=self._base_meta(doc),
            preview=preview,
        )

    def _build_primary_stage(self, doc, version) -> PipelineStageViewDTO:
        artifact_ref = version.primary_source_ref
        if not artifact_ref:
            return PipelineStageViewDTO(
                code=PipelineStageCode.PRIMARY,
                title="PRIMARY: одноязычный source",
                description=(
                    "Документ после выбора основного языка сделки, "
                    "используемый как основной вход в downstream-пайплайн."
                ),
                available=False,
                kind=PipelineStageKind.pdf,
                status=PipelineStageStatus.pending,
                artifact_ref=None,
                meta=self._base_meta(doc),
                preview=None,
            )

        try:
            url = self.store.get_presigned_get_url(artifact_ref)
        except PermanentError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.PRIMARY,
                title="PRIMARY: одноязычный source",
                description="Primary-source PDF ожидается, но отсутствует в сторедже.",
                available=False,
                kind=PipelineStageKind.pdf,
                status=PipelineStageStatus.missing,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )
        except TransientError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.PRIMARY,
                title="PRIMARY: одноязычный source",
                description="Primary-source PDF временно недоступен.",
                available=False,
                kind=PipelineStageKind.pdf,
                status=PipelineStageStatus.pending,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )

        preview = PdfPreviewDTO(
            type="pdf",
            inline_url=url,
            download_url=url,
        )

        return PipelineStageViewDTO(
            code=PipelineStageCode.PRIMARY,
            title="PRIMARY: одноязычный source",
            description=(
                "Документ после выбора основного языка сделки, "
                "используемый как основной вход в downstream-пайплайн."
            ),
            available=True,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.ready,
            artifact_ref=artifact_ref,
            meta=self._base_meta(doc),
            preview=preview,
        )


    def _build_extract_stage(self, doc, version) -> PipelineStageViewDTO:
        artifact_ref = version.layout_primary_ref or version.text_layout_raw_ref

        if not artifact_ref:
            return PipelineStageViewDTO(
                code=PipelineStageCode.EXTRACT,
                title="EXTRACT: layout после извлечения",
                description="Текстовый layout после extract: primary-language layout или raw multilingual layout.",
                available=False,
                kind=PipelineStageKind.layout,
                status=PipelineStageStatus.pending,
                artifact_ref=None,
                meta=self._base_meta(doc),
                preview=None,
            )

        try:
            layout = self.store.get_json(artifact_ref)
        except PermanentError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.EXTRACT,
                title="EXTRACT: layout после извлечения",
                description="Артефакт extract-layout ожидается, но отсутствует в сторедже.",
                available=False,
                kind=PipelineStageKind.layout,
                status=PipelineStageStatus.missing,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )
        except TransientError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.EXTRACT,
                title="EXTRACT: layout после извлечения",
                description="Артефакт extract-layout временно недоступен.",
                available=False,
                kind=PipelineStageKind.layout,
                status=PipelineStageStatus.pending,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )

        return self._build_layout_stage_from_payload(
            code=PipelineStageCode.EXTRACT,
            title="EXTRACT: layout после извлечения",
            description="Текстовый layout после extract: primary-language layout или raw multilingual layout.",
            artifact_ref=artifact_ref,
            layout=layout,
            doc=doc,
        )

    def _build_pii_stage(self, doc, version) -> PipelineStageViewDTO:
        artifact_ref = (
            version.layout_primary_sanitized_ref
            or version.text_layout_sanitized_ref
        )

        if not artifact_ref:
            return PipelineStageViewDTO(
                code=PipelineStageCode.PII,
                title="PII: sanitized layout",
                description="Layout после PII-санитизации. Это основной downstream-layout для структуры, chunking и checks.",
                available=False,
                kind=PipelineStageKind.layout,
                status=PipelineStageStatus.pending,
                artifact_ref=None,
                meta=self._base_meta(doc),
                preview=None,
            )

        try:
            layout = self.store.get_json(artifact_ref)
        except PermanentError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.PII,
                title="PII: sanitized layout",
                description="Артефакт sanitized layout ожидается, но отсутствует в сторедже.",
                available=False,
                kind=PipelineStageKind.layout,
                status=PipelineStageStatus.missing,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )
        except TransientError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.PII,
                title="PII: sanitized layout",
                description="Sanitized layout временно недоступен.",
                available=False,
                kind=PipelineStageKind.layout,
                status=PipelineStageStatus.pending,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )

        return self._build_layout_stage_from_payload(
            code=PipelineStageCode.PII,
            title="PII: sanitized layout",
            description="Layout после PII-санитизации. Это основной downstream-layout для структуры, chunking и checks.",
            artifact_ref=artifact_ref,
            layout=layout,
            doc=doc,
        )

    def _build_layout_stage_from_payload(
        self,
        *,
        code: PipelineStageCode,
        title: str,
        description: str,
        artifact_ref: str,
        layout: dict[str, Any] | list[Any],
        doc,
    ) -> PipelineStageViewDTO:
        if not isinstance(layout, dict):
            layout = {"raw": layout, "elements": []}

        elements = layout.get("elements") or []
        by_page: dict[int, list[str]] = defaultdict(list)
        count_by_page: dict[int, int] = defaultdict(int)

        for el in elements:
            if not isinstance(el, dict):
                continue
            page = el.get("page")
            text = el.get("text") or ""
            if not isinstance(page, int):
                continue
            count_by_page[page] += 1
            if text:
                by_page[page].append(str(text))

        pages: list[LayoutPagePreviewDTO] = []
        all_pages = sorted(set(count_by_page.keys()) | set(by_page.keys()))
        for page_num in all_pages:
            pages.append(
                LayoutPagePreviewDTO(
                    page=page_num,
                    text="\n".join(by_page.get(page_num, []))[:4000],
                    element_count=count_by_page.get(page_num, 0),
                )
            )

        preview = LayoutPreviewDTO(
            type="layout",
            pages=pages,
            raw_json=layout,
        )

        meta = self._base_meta(doc)
        meta.element_count = len(elements)

        return PipelineStageViewDTO(
            code=code,
            title=title,
            description=description,
            available=True,
            kind=PipelineStageKind.layout,
            status=PipelineStageStatus.ready,
            artifact_ref=artifact_ref,
            meta=meta,
            preview=preview,
        )

    def _build_structure_stage(self, doc, version) -> PipelineStageViewDTO:
        artifact_ref = version.clause_tree_ref

        if not artifact_ref:
            return PipelineStageViewDTO(
                code=PipelineStageCode.STRUCTURE,
                title="STRUCTURE: дерево документа",
                description="Структурированное дерево секций, пунктов и подпунктов документа.",
                available=False,
                kind=PipelineStageKind.structure,
                status=PipelineStageStatus.pending,
                artifact_ref=None,
                meta=self._base_meta(doc),
                preview=None,
            )

        try:
            payload = self.store.get_json(artifact_ref)
        except PermanentError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.STRUCTURE,
                title="STRUCTURE: дерево документа",
                description="Артефакт clause tree ожидается, но отсутствует в сторедже.",
                available=False,
                kind=PipelineStageKind.structure,
                status=PipelineStageStatus.missing,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )
        except TransientError:
            return PipelineStageViewDTO(
                code=PipelineStageCode.STRUCTURE,
                title="STRUCTURE: дерево документа",
                description="Структурированный артефакт временно недоступен.",
                available=False,
                kind=PipelineStageKind.structure,
                status=PipelineStageStatus.pending,
                artifact_ref=artifact_ref,
                meta=self._base_meta(doc),
                preview=None,
            )

        sections: list[StructureSectionPreviewDTO] = []

        if isinstance(payload, dict):
            self._flatten_clause_tree(payload, sections, level=1)
        elif isinstance(payload, list):
            for idx, node in enumerate(payload, start=1):
                if isinstance(node, dict):
                    self._flatten_clause_tree(node, sections, level=1, fallback_index=idx)

        preview = StructurePreviewDTO(
            type="structure",
            sections=sections,
            raw_json=payload,
        )

        meta = self._base_meta(doc)
        meta.section_count = len(sections)

        return PipelineStageViewDTO(
            code=PipelineStageCode.STRUCTURE,
            title="STRUCTURE: дерево документа",
            description="Структурированное дерево секций, пунктов и подпунктов документа.",
            available=True,
            kind=PipelineStageKind.structure,
            status=PipelineStageStatus.ready,
            artifact_ref=artifact_ref,
            meta=meta,
            preview=preview,
        )

    def _flatten_clause_tree(
        self,
        node: dict[str, Any],
        acc: list[StructureSectionPreviewDTO],
        *,
        level: int,
        fallback_index: int | None = None,
    ) -> None:
        node_id = (
            node.get("clauseUid")
            or node.get("clause_uid")
            or node.get("id")
            or node.get("uid")
            or f"section_{fallback_index or len(acc) + 1}"
        )
        title = (
            node.get("title")
            or node.get("label")
            or node.get("name")
            or "Untitled section"
        )
        page_from = node.get("startPage") or node.get("page_from")
        page_to = node.get("endPage") or node.get("page_to") or page_from
        text = node.get("text") or ""
        if not isinstance(text, str):
            text = str(text)

        acc.append(
            StructureSectionPreviewDTO(
                id=str(node_id),
                title=str(title),
                level=int(node.get("level") or level),
                page_from=page_from if isinstance(page_from, int) else None,
                page_to=page_to if isinstance(page_to, int) else None,
                text_preview=text[:500],
            )
        )

        children = node.get("children") or []
        if isinstance(children, list):
            for idx, child in enumerate(children, start=1):
                if isinstance(child, dict):
                    self._flatten_clause_tree(
                        child,
                        acc,
                        level=level + 1,
                        fallback_index=idx,
                    )

    async def _build_chunks_stage(self, doc, version) -> PipelineStageViewDTO:
        artifact_ref = version.chunks_ref
        raw_snapshot: dict[str, Any] | list[Any] | None = None
        chunks: list[ChunkPreviewDTO] = []

        if artifact_ref:
            try:
                snapshot = self.store.get_json(artifact_ref)
                raw_snapshot = snapshot
                chunks = self._extract_chunks_from_snapshot(snapshot)
            except PermanentError:
                return PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description="Snapshot чанков ожидается, но отсутствует в сторедже.",
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.missing,
                    artifact_ref=artifact_ref,
                    meta=self._base_meta(doc),
                    preview=None,
                )
            except TransientError:
                return PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description="Snapshot чанков временно недоступен.",
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=artifact_ref,
                    meta=self._base_meta(doc),
                    preview=None,
                )

        if not chunks:
            fallback_chunks = await self._load_chunks_fallback(doc.id)
            chunks = fallback_chunks

        if not chunks:
            meta = self._base_meta(doc)
            meta.chunk_count = 0
            return PipelineStageViewDTO(
                code=PipelineStageCode.CHUNKS,
                title="CHUNKS: materialized chunks",
                description="Чанки для документа пока недоступны.",
                available=False,
                kind=PipelineStageKind.chunks,
                status=PipelineStageStatus.pending,
                artifact_ref=artifact_ref,
                meta=meta,
                preview=None,
            )

        reconstructed_text = "\n\n".join(
            chunk.text for chunk in chunks if chunk.text.strip()
        )

        preview = ChunksPreviewDTO(
            type="chunks",
            chunks=chunks,
            reconstructed_text=reconstructed_text,
            raw_json=raw_snapshot,
        )

        meta = self._base_meta(doc)
        meta.chunk_count = len(chunks)

        return PipelineStageViewDTO(
            code=PipelineStageCode.CHUNKS,
            title="CHUNKS: materialized chunks",
            description="Материализованный snapshot чанков документа для retrieval, checks и viewer.",
            available=True,
            kind=PipelineStageKind.chunks,
            status=PipelineStageStatus.ready,
            artifact_ref=artifact_ref,
            meta=meta,
            preview=preview,
        )

    async def _load_chunks_fallback(self, doc_id: UUID) -> list[ChunkPreviewDTO]:
        result: list[ChunkPreviewDTO] = []

        try:
            if hasattr(self.content_service, "get_chunks"):
                payload = await self.content_service.get_chunks(doc_id=doc_id)
            elif hasattr(self.content_service, "get_sized_chunks"):
                payload = await self.content_service.get_sized_chunks(doc_id=doc_id)
            else:
                return result
        except Exception:
            return result

        if not isinstance(payload, list):
            return result

        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                continue

            text = item.get("text") or ""
            if not isinstance(text, str) or not text.strip():
                continue

            meta = item.get("metadata") or {}

            clause_uid = (
                item.get("clause_uid")
                or meta.get("clause_uid")
                or ""
            )
            page_from = (
                item.get("page_from")
                or meta.get("page_from")
                or item.get("page")
                or meta.get("page")
            )
            page_to = (
                item.get("page_to")
                or meta.get("page_to")
                or item.get("page")
                or meta.get("page")
            )

            result.append(
                ChunkPreviewDTO(
                    index=idx,
                    clause_uid=str(clause_uid) if clause_uid else "",
                    page_from=page_from if isinstance(page_from, int) else None,
                    page_to=page_to if isinstance(page_to, int) else None,
                    text=text[:4000],
                )
            )

        return result

    def _extract_chunks_from_snapshot(
        self,
        snapshot: dict[str, Any] | list[Any],
    ) -> list[ChunkPreviewDTO]:
        result: list[ChunkPreviewDTO] = []

        if isinstance(snapshot, dict):
            items = snapshot.get("chunks") or []
        elif isinstance(snapshot, list):
            items = snapshot
        else:
            return result

        if not isinstance(items, list):
            return result

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            text = item.get("text") or ""
            if not isinstance(text, str) or not text.strip():
                continue

            meta = item.get("metadata") or {}
            clause_uid = (
                item.get("clause_uid")
                or meta.get("clause_uid")
                or ""
            )
            page_from = (
                item.get("page_from")
                or meta.get("page_from")
                or item.get("page")
                or meta.get("page")
            )
            page_to = (
                item.get("page_to")
                or meta.get("page_to")
                or item.get("page")
                or meta.get("page")
            )

            result.append(
                ChunkPreviewDTO(
                    index=idx,
                    clause_uid=str(clause_uid) if clause_uid else "",
                    page_from=page_from if isinstance(page_from, int) else None,
                    page_to=page_to if isinstance(page_to, int) else None,
                    text=text[:4000],
                )
            )

        return result
    

    