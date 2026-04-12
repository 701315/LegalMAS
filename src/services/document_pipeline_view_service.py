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
    StageProvenanceDTO,
    StageRepresentationDTO,
    StageViewMode,
    StructurePreviewDTO,
    StructureSectionPreviewDTO,
    SectionSourceMappingDTO,
)

from core.exceptions import PermanentError, TransientError
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.document_content_service import DocumentContentService
from storage.artifact_store import ArtifactStore
from engine.content.chunk_snapshot_reader import ChunkSnapshotReader
from core.logging import get_logger

logger = get_logger(__name__)


class DocumentPipelineViewService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.ver_repo = DocumentVersionRepository(session)
        self.content_service = DocumentContentService(session=session)
        self.store = ArtifactStore()

    async def build(
        self,
        document_id: UUID,
        view_mode: StageViewMode = StageViewMode.canonical,
    ) -> DocumentPipelineViewResponseDTO:
        """
        Собирает срез пайплайна по документу.

        Параметр view_mode управляет только тем, как отображаются отдельные стадии
        (например, STRUCTURE / CHUNKS) для фронта:

        - "canonical" — показывается чистый результат этапа без дополнительных
          обогащений;
        - "friendly" — показывается более удобное для чтения представление
          (может использовать данные соседних этапов).

        Важно: сама бизнес-логика пайплайна от этого параметра не зависит,
        меняется только представление данных для UI.
        """
        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise ValueError("Document not found")

        version = await self.ver_repo.get_latest(document_id)
        if not version:
            raise ValueError("DocumentVersion not found")

        # view_mode уже валидный enum из FastAPI, можно использовать его напрямую
        mode_enum = view_mode

        # Пока режим влияет только на STRUCTURE/CHUNKS. Остальные стадии
        # всегда возвращаются в каноническом виде.
        structure_stage = await self._build_structure_stage(
            doc=doc,
            version=version,
            view_mode=mode_enum,
        )

        chunks_stage = await self._build_chunks_stage(
            doc=doc,
            version=version,
            view_mode=mode_enum,
        )

        stages: list[PipelineStageViewDTO] = [
            self._with_representation(
                self._build_source_stage(doc, version),
                stage_code=PipelineStageCode.SOURCE,
                view_mode=mode_enum,
                friendly_supported=False,
                canonical_description="Показывается исходный документ, который поступил в пайплайн.",
                friendly_description="Показывается тот же исходный документ в режиме удобного просмотра.",
            ),
            self._with_representation(
                self._build_primary_stage(doc, version),
                stage_code=PipelineStageCode.PRIMARY,
                view_mode=mode_enum,
                friendly_supported=False,
                canonical_description="Показывается результат этапа PRIMARY: одноязычный source.",
                friendly_description="Показывается тот же результат PRIMARY в режиме удобного просмотра.",
            ),
            self._with_representation(
                self._build_extract_stage(doc, version),
                stage_code=PipelineStageCode.EXTRACT,
                view_mode=mode_enum,
                friendly_supported=False,
                canonical_description="Показывается layout, полученный на этапе EXTRACT.",
                friendly_description="Показывается тот же layout EXTRACT в режиме удобного просмотра.",
            ),
            self._with_representation(
                self._build_pii_stage(doc, version),
                stage_code=PipelineStageCode.PII,
                view_mode=mode_enum,
                friendly_supported=False,
                canonical_description="Показывается layout после PII-санитизации.",
                friendly_description="Показывается тот же sanitized layout в режиме удобного просмотра.",
            ),
            # STRUCTURE и CHUNKS возвращаются уже с representation внутри самих методов
            structure_stage,
            chunks_stage,
        ]

        return DocumentPipelineViewResponseDTO(
            document_id=str(doc.id),
            document_version_id=str(version.id),
            document_status=doc.status,
            view_mode=mode_enum,
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

    def _stage_representation(
        self,
        *,
        stage_code: PipelineStageCode,
        view_mode: StageViewMode,
        friendly_supported: bool = False,
        friendly_description: str | None = None,
        canonical_description: str | None = None,
        derived_from_stages: list[PipelineStageCode] | None = None,
        preview_source_label: str | None = None,
    ) -> StageRepresentationDTO:
        """
        Строит единое описание режима представления стадии для UI.

        Логика:
        - canonical: всегда "Результат этапа";
        - friendly:
            - если у стадии реально есть отдельный friendly-режим,
              помечаем её как производное представление;
            - если friendly пока не поддержан, используем тот же результат,
              но явно говорим, что это "удобный просмотр" без других источников.
        """
        derived = derived_from_stages or []

        if view_mode == StageViewMode.canonical:
            return StageRepresentationDTO(
                view_mode=view_mode,
                is_canonical=True,
                label="Результат этапа",
                description=canonical_description
                or "Показывается точный результат этого этапа.",
                provenance=StageProvenanceDTO(
                    primary_source_stage=stage_code,
                    derived_from_stages=[],
                    preview_source_label=None,
                ),
            )

        if friendly_supported:
            return StageRepresentationDTO(
                view_mode=view_mode,
                is_canonical=False,
                label="Удобный вид",
                description=friendly_description
                or "Показывается более удобное для чтения представление.",
                provenance=StageProvenanceDTO(
                    primary_source_stage=stage_code,
                    derived_from_stages=derived,
                    preview_source_label=preview_source_label,
                ),
            )

        return StageRepresentationDTO(
            view_mode=view_mode,
            is_canonical=False,
            label="Удобный вид",
            description=(
                friendly_description
                or "Для этого этапа пока используется тот же результат, "
                   "но в режиме удобного просмотра."
            ),
            provenance=StageProvenanceDTO(
                primary_source_stage=stage_code,
                derived_from_stages=[],
                preview_source_label=None,
            ),
        )

    def _with_representation(
        self,
        stage: PipelineStageViewDTO,
        *,
        stage_code: PipelineStageCode,
        view_mode: StageViewMode,
        friendly_supported: bool = False,
        friendly_description: str | None = None,
        canonical_description: str | None = None,
        derived_from_stages: list[PipelineStageCode] | None = None,
        preview_source_label: str | None = None,
    ) -> PipelineStageViewDTO:
        """
        Возвращает ту же стадию, но с заполненным полем representation.

        Это отдельный helper, чтобы не дублировать конструирование
        StageRepresentationDTO в каждом _build_*_stage.
        """
        stage.representation = self._stage_representation(
            stage_code=stage_code,
            view_mode=view_mode,
            friendly_supported=friendly_supported,
            friendly_description=friendly_description,
            canonical_description=canonical_description,
            derived_from_stages=derived_from_stages,
            preview_source_label=preview_source_label,
        )
        return stage

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
                    text="\n".join(by_page.get(page_num, [])),
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

    def _extract_clause_tree_text(self, node: dict[str, Any]) -> str:
        """
        Достаёт canonical текст секции из clause tree с поддержкой нескольких ключей.

        Важно:
        - это source of truth для canonical STRUCTURE-view;
        - не зависит от CHUNKS;
        - должен быть безопасным для разных форматов tree.to_dict().
        """
        candidates = [
            node.get("text"),
            node.get("content"),
            node.get("body"),
            node.get("clauseText"),
            node.get("normalized_text"),
            node.get("raw_text"),
        ]

        for value in candidates:
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
            elif value is not None:
                text = str(value).strip()
                if text:
                    return text

        return ""


    async def _attach_structure_source_mapping(
        self,
        doc_id: UUID,
        sections: list[StructureSectionPreviewDTO],
    ) -> bool:
        """
        Привязывает STRUCTURE-секции к canonical clause-chunks по clause_uid.

        Инварианты:
        - используем только snapshot уровня "clause";
        - mapping строится только по clause_uid, без fuzzy/text fallback;
        - page_from/page_to берём из реально связанных чанков, а не из секции;
        - chunk_indices всегда дедуплицированы и отсортированы;
        - match_text — короткий preview, а не весь текст клаузы.
        """
        if not sections:
            return False

        reader = ChunkSnapshotReader(
            session=self.session,
            artifact_store=self.store,
        )

        clause_chunks = await reader.load(
            doc_id=doc_id,
            levels=["clause"],
        )
        if not clause_chunks:
            return False

        def _normalize_uid(value: Any) -> str | None:
            if value is None:
                return None
            uid = str(value).strip()
            return uid or None

        chunks_by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for raw_idx, ch in enumerate(clause_chunks):
            meta = ch.get("metadata") or {}
            uid = _normalize_uid(meta.get("clause_uid") or ch.get("clause_uid"))
            if not uid:
                continue

            # индекс в snapshot-е, нужен для chunk_indices
            ch["_pipeline_index"] = raw_idx
            chunks_by_uid[uid].append(ch)

        def _chunk_sort_key(ch: dict[str, Any]) -> tuple[float, int, str]:
            meta = ch.get("metadata") or {}
            pos = meta.get("position_ratio")
            start_page = meta.get("start_page")
            chunk_id = str(ch.get("id") or "")
            return (
                float(pos) if isinstance(pos, (int, float)) else 1.0,
                int(start_page) if isinstance(start_page, int) else 10**9,
                chunk_id,
            )

        for items in chunks_by_uid.values():
            items.sort(key=_chunk_sort_key)

        mapped_any = False

        for section in sections:
            section_uid = _normalize_uid(section.clause_uid)
            if not section_uid:
                continue

            chunks = chunks_by_uid.get(section_uid)
            if not chunks:
                # полезно залогировать, если хочешь проще отлавливать дырки:
                # logger.debug("No clause chunks for section", extra={"doc_id": str(doc_id), "clause_uid": section_uid})
                continue

            chunk_indices: list[int] = []
            parts: list[str] = []
            seen_chunk_ids: set[str] = set()
            page_values: list[int] = []

            for ch in chunks:
                chunk_id = str(ch.get("id") or "").strip()
                if chunk_id and chunk_id in seen_chunk_ids:
                    continue

                text = (ch.get("text") or "").strip()
                if not text:
                    continue

                parts.append(text)

                if chunk_id:
                    seen_chunk_ids.add(chunk_id)

                raw_idx = ch.get("_pipeline_index")
                if isinstance(raw_idx, int):
                    chunk_indices.append(raw_idx)

                meta = ch.get("metadata") or {}
                start_page = meta.get("start_page")
                end_page = meta.get("end_page")

                if isinstance(start_page, int):
                    page_values.append(start_page)
                if isinstance(end_page, int):
                    page_values.append(end_page)

            unique_indices = sorted(set(chunk_indices))
            if not unique_indices:
                continue

            full_text = "\n\n".join(parts).strip()
            if not full_text:
                continue

            # Короткий preview вместо полного текста
            match_text = full_text[:400]

            # ВАЖНО: не перетираем уже существующий mapping, если он был
            # заполнен более "богатой" логикой (например, после enrich).
            if not section.source_mapping or not section.source_mapping.chunk_indices:
                section.source_mapping = SectionSourceMappingDTO(
                    source_stage=PipelineStageCode.CHUNKS,
                    page_from=min(page_values) if page_values else section.page_from,
                    page_to=max(page_values) if page_values else section.page_to,
                    chunk_indices=unique_indices,
                    match_text=match_text,
                    match_strategy="chunk_refs",
                )
                mapped_any = True

        return mapped_any

    def _inherit_structure_from_children(
        self,
        sections: list[StructureSectionPreviewDTO],
    ) -> None:
        """
        Обогащает "групповые" секции (типа 6.1), у которых нет собственного enriched_text
        и source_mapping, за счёт их дочерних пунктов.

        Логика:
        - если у родителя нет enriched_text и/или source_mapping;
        - у дочерних секций есть enriched_text (или хотя бы structure_text) и/или mapping;
        - в родителя агрегируется:
          - enriched_text = конкатенация enriched_text детей (fallback: structure_text);
          - source_mapping:
              - chunk_indices = объединение индексов детей (без дубликатов);
              - match_text = тот же агрегированный текст;
              - match_strategy = "chunk_refs".
        """
        if not sections:
            return

        # Быстрый доступ: clause_uid -> секция.
        section_by_uid: dict[str, StructureSectionPreviewDTO] = {}
        for s in sections:
            if s.clause_uid:
                section_by_uid[s.clause_uid] = s

        # Собираем детей по родительскому uid: "6.1.1" -> parent "6.1".
        children_by_parent_uid: dict[str, list[StructureSectionPreviewDTO]] = defaultdict(list)
        for s in sections:
            uid = s.clause_uid
            if not uid:
                continue
            parts = uid.split(".")
            if len(parts) <= 1:
                continue  # верхний уровень (1, 2, 3, ...)
            parent_uid = ".".join(parts[:-1])
            children_by_parent_uid[parent_uid].append(s)

        for parent_uid, child_sections in children_by_parent_uid.items():
            parent = section_by_uid.get(parent_uid)
            if not parent:
                continue

            has_enriched_text = bool(parent.enriched_text and parent.enriched_text.strip())
            has_mapping = parent.source_mapping is not None

            # Если у родителя уже есть и enriched_text, и mapping — не трогаем.
            if has_enriched_text and has_mapping:
                continue

            child_texts: list[str] = []
            all_indices: list[int] = []

            for child in child_sections:
                # Для агрегата в первую очередь используем enriched_text детей,
                # если его нет — fallback на structure_text.
                if child.enriched_text and child.enriched_text.strip():
                    child_texts.append(child.enriched_text.strip())
                elif child.structure_text and child.structure_text.strip():
                    child_texts.append(child.structure_text.strip())

                if child.source_mapping and child.source_mapping.chunk_indices:
                    all_indices.extend(child.source_mapping.chunk_indices)

            if not child_texts and not all_indices:
                # У детей тоже нечего наследовать.
                continue

            aggregated_text = "\n\n".join(child_texts).strip() if child_texts else None

            # Если у родителя не было enriched_text — подставляем агрегированный.
            if not has_enriched_text and aggregated_text:
                parent.enriched_text = aggregated_text

            # Если не было mapping — создаём агрегированный.
            if not has_mapping and all_indices:
                unique_indices = sorted(set(all_indices))
                parent.source_mapping = SectionSourceMappingDTO(
                    source_stage=PipelineStageCode.CHUNKS,
                    page_from=parent.page_from,
                    page_to=parent.page_to,
                    chunk_indices=unique_indices,
                    match_text=aggregated_text,
                    match_strategy="chunk_refs",
                )


    async def _build_structure_stage(
        self,
        doc,
        version,
        view_mode: StageViewMode = StageViewMode.canonical,
    ) -> PipelineStageViewDTO:
        artifact_ref = version.clause_tree_ref

        if not artifact_ref:
            return self._with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.STRUCTURE,
                    title="STRUCTURE: дерево документа",
                    description="Структурированное дерево секций, пунктов и подпунктов документа.",
                    available=False,
                    kind=PipelineStageKind.structure,
                    status=PipelineStageStatus.pending,
                    artifact_ref=None,
                    meta=self._base_meta(doc),
                    preview=None,
                ),
                stage_code=PipelineStageCode.STRUCTURE,
                view_mode=view_mode,
                friendly_supported=True,
                canonical_description=(
                    "Показывается чистый результат этапа STRUCTURE: "
                    "дерево секций и пунктов без обогащения текстом из CHUNKS."
                ),
                friendly_description=(
                    "Показывается удобное для чтения представление дерева STRUCTURE. "
                    "Отдельное friendly-представление применяется, когда артефакт доступен."
                ),
                derived_from_stages=[PipelineStageCode.CHUNKS],
                preview_source_label="Текстовое превью из CHUNKS",
            )

        try:
            payload = self.store.get_json(artifact_ref)
        except PermanentError:
            return self._with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.STRUCTURE,
                    title="STRUCTURE: дерево документа",
                    description="Артефакт clause tree ожидается, но отсутствует в сторедже.",
                    available=False,
                    kind=PipelineStageKind.structure,
                    status=PipelineStageStatus.missing,
                    artifact_ref=artifact_ref,
                    meta=self._base_meta(doc),
                    preview=None,
                ),
                stage_code=PipelineStageCode.STRUCTURE,
                view_mode=view_mode,
                friendly_supported=True,
                canonical_description=(
                    "Показывается чистый результат этапа STRUCTURE: "
                    "дерево секций и пунктов без обогащения текстом из CHUNKS."
                ),
                friendly_description=(
                    "Показывается удобное для чтения представление дерева STRUCTURE. "
                    "Отдельное friendly-представление применяется, когда артефакт доступен."
                ),
                derived_from_stages=[PipelineStageCode.CHUNKS],
                preview_source_label="Текстовое превью из CHUNKS",
            )
        except TransientError:
            return self._with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.STRUCTURE,
                    title="STRUCTURE: дерево документа",
                    description="Структурированный артефакт временно недоступен.",
                    available=False,
                    kind=PipelineStageKind.structure,
                    status=PipelineStageStatus.pending,
                    artifact_ref=artifact_ref,
                    meta=self._base_meta(doc),
                    preview=None,
                ),
                stage_code=PipelineStageCode.STRUCTURE,
                view_mode=view_mode,
                friendly_supported=True,
                canonical_description=(
                    "Показывается чистый результат этапа STRUCTURE: "
                    "дерево секций и пунктов без обогащения текстом из CHUNKS."
                ),
                friendly_description=(
                    "Показывается удобное для чтения представление дерева STRUCTURE. "
                    "Отдельное friendly-представление применяется, когда артефакт доступен."
                ),
                derived_from_stages=[PipelineStageCode.CHUNKS],
                preview_source_label="Текстовое превью из CHUNKS",
            )

        sections: list[StructureSectionPreviewDTO] = []

        root_nodes = self._iter_structure_root_nodes(payload)
        for idx, node in enumerate(root_nodes):
            self._flatten_clause_tree(
                node,
                sections,
                level=1,
                path_indices=[idx],
            )

        text_enriched = False
        source_mapped = False

        # source_mapping нужен и для canonical, и для friendly:
        try:
            source_mapped = await self._attach_structure_source_mapping(
                doc_id=doc.id,
                sections=sections,
            )
        except Exception as e:
            logger.warning(
                "PIPELINE_VIEW STRUCTURE: source mapping attach failed",
                extra={
                    "doc_id": str(doc.id),
                    "error": str(e),
                },
            )

        # Обогащаем текст секций из canonical chunk snapshot только в friendly-режиме.
        # Canonical должен сохранять собственный text_preview из clause tree.
        if view_mode == StageViewMode.friendly:
            try:
                text_enriched = await self._enrich_structure_with_text(
                    doc_id=doc.id,
                    sections=sections,
                )
            except Exception as e:
                logger.warning(
                    "PIPELINE_VIEW STRUCTURE: text enrichment failed, using clause-tree text only",
                    extra={
                        "doc_id": str(doc.id),
                        "error": str(e),
                    },
                )

        # После source_mapping и text_enriched наследуем данные для "групповых" секций
        # вроде 6.1, у которых нет собственного текста и mapping.
        try:
            self._inherit_structure_from_children(sections)
        except Exception as e:
            logger.warning(
                "PIPELINE_VIEW STRUCTURE: inherit from children failed",
                extra={
                    "doc_id": str(doc.id),
                    "error": str(e),
                },
            )

        # После всех обогащений приводим text_preview к единой семантике
        # в зависимости от view_mode:
        #
        # canonical:
        #   text_preview = structure_text
        # friendly:
        #   text_preview = enriched_text (если есть) иначе structure_text.
        for s in sections:
            if view_mode == StageViewMode.canonical:
                s.text_preview = s.structure_text or ""
            else:
                s.text_preview = (s.enriched_text or s.structure_text or "").strip()

        preview = StructurePreviewDTO(
            type="structure",
            sections=sections,
            raw_json=payload,
        )

        meta = self._base_meta(doc)
        meta.section_count = len(sections)
        meta.text_enriched = text_enriched

        logger.info(
            "PIPELINE_VIEW STRUCTURE",
            extra={
                "doc_id": str(doc.id),
                "clause_tree_ref": artifact_ref,
                "sections_len": len(sections),
                "payload_type": type(payload).__name__,
                "text_enriched": text_enriched,
                "source_mapped": source_mapped,
                "view_mode": view_mode.value,
            },
        )

        stage = PipelineStageViewDTO(
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

        return self._with_representation(
            stage,
            stage_code=PipelineStageCode.STRUCTURE,
            view_mode=view_mode,
            friendly_supported=True,
            canonical_description=(
                "Показывается чистый результат этапа STRUCTURE: "
                "дерево секций и пунктов без обогащения текстом из CHUNKS."
            ),
            friendly_description=(
                "Показывается удобное для чтения представление дерева STRUCTURE, "
                "обогащённое текстом из canonical snapshot CHUNKS."
            ),
            derived_from_stages=[PipelineStageCode.CHUNKS],
            preview_source_label="Текстовое превью из CHUNKS",
        )
    
    def _flatten_clause_tree(
        self,
        node: dict[str, Any],
        acc: list[StructureSectionPreviewDTO],
        *,
        level: int,
        path_indices: list[int],
    ) -> None:
        """
        Преобразует один узел clause tree в плоскую секцию для STRUCTURE-view
        и рекурсивно обрабатывает его дочерние узлы.

        Важно:
        - id секции строится детерминированно из clause_uid и пути в дереве:
        "<clause_uid or 'noid'>#<path_str>";
        - clause_uid прокидывается явно в DTO;
        - structure_text = text из clause tree;
        - text_preview в canonical = structure_text (friendly переопределит).
        """

        def _normalize_uid(value: Any) -> str | None:
            if value is None:
                return None
            uid = str(value).strip()
            return uid or None

        def _normalize_title(value: Any) -> str:
            if value is None:
                return "Untitled section"
            title = str(value).strip()
            return title or "Untitled section"

        def _normalize_int(value: Any) -> int | None:
            if value is None:
                return None
            if isinstance(value, int):
                return value
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return None

        clause_uid = _normalize_uid(
            node.get("clauseUid") or node.get("clause_uid")
        )

        title = _normalize_title(
            node.get("title")
            or node.get("label")
            or node.get("name")
        )

        page_from = _normalize_int(
            node.get("startPage")
            or node.get("start_page")
            or node.get("page_from")
        )
        page_to = _normalize_int(
            node.get("endPage")
            or node.get("end_page")
            or node.get("page_to")
        )

        if page_from is not None and page_to is None:
            page_to = page_from
        if page_to is not None and page_from is None:
            page_from = page_to
        if (
            page_from is not None
            and page_to is not None
            and page_to < page_from
        ):
            page_from, page_to = page_to, page_from

        text = self._extract_clause_tree_text(node)

        node_level = _normalize_int(node.get("level"))
        effective_level = node_level if node_level is not None else level

        path_str = ".".join(str(i) for i in path_indices) if path_indices else "0"
        base_id = clause_uid or "noid"
        node_id = f"{base_id}#{path_str}"

        acc.append(
            StructureSectionPreviewDTO(
                id=node_id,
                title=title,
                level=effective_level,
                page_from=page_from,
                page_to=page_to,
                structure_text=text,
                enriched_text="",
                text_preview=text,
                clause_uid=clause_uid,
            )
        )

        children = node.get("children")
        if not isinstance(children, list):
            return

        for idx, child in enumerate(children):
            if not isinstance(child, dict):
                continue

            self._flatten_clause_tree(
                child,
                acc,
                level=effective_level + 1,
                path_indices=path_indices + [idx],
            )

    def _iter_structure_root_nodes(
        self,
        payload: Any,
    ) -> list[dict[str, Any]]:
        """
        Нормализованный доступ к корневым узлам clause tree для STRUCTURE‑view.

        Поддерживаем форматы:
        - {"root": [ {...}, {...} ]}
        - {"root": { "children": [ {...}, ... ] }}
        - [ {...}, {...} ]
        - fallback: одиночный dict как один узел.
        """
        nodes: list[dict[str, Any]] = []

        if isinstance(payload, dict):
            raw_root = payload.get("root")

            if isinstance(raw_root, list):
                nodes = [n for n in raw_root if isinstance(n, dict)]
            elif isinstance(raw_root, dict):
                children = raw_root.get("children")
                if isinstance(children, list):
                    nodes = [n for n in children if isinstance(n, dict)]
            else:
                # fallback: воспринимаем payload как один узел дерева
                nodes = [payload]

        elif isinstance(payload, list):
            nodes = [n for n in payload if isinstance(n, dict)]

        return nodes


    async def _enrich_structure_with_text(
        self,
        doc_id: UUID,
        sections: list[StructureSectionPreviewDTO],
    ) -> bool:
        """
        Обогащает STRUCTURE-секции canonical текстом из snapshot уровня "clause".

        Инварианты:
        - enrichment идёт только по clause_uid;
        - structure_text остаётся source of truth из clause tree;
        - enriched_text = текст из clause-level chunks;
        - source_mapping отражает только реально связанные clause chunks;
        - никаких fuzzy/text fallback здесь нет.
        """
        if not sections:
            return False

        reader = ChunkSnapshotReader(
            session=self.session,
            artifact_store=self.store,
        )

        clause_chunks = await reader.load(
            doc_id=doc_id,
            levels=["clause"],
        )
        if not clause_chunks:
            return False

        def _normalize_uid(value: Any) -> str | None:
            if value is None:
                return None
            uid = str(value).strip()
            return uid or None

        chunks_by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for raw_idx, ch in enumerate(clause_chunks):
            meta = ch.get("metadata") or {}
            uid = _normalize_uid(meta.get("clause_uid") or ch.get("clause_uid"))
            if not uid:
                continue

            ch["_pipeline_index"] = raw_idx
            chunks_by_uid[uid].append(ch)

        def _chunk_sort_key(ch: dict[str, Any]) -> tuple[float, int, str]:
            meta = ch.get("metadata") or {}
            pos = meta.get("position_ratio")
            start_page = meta.get("start_page")
            chunk_id = str(ch.get("id") or "")
            return (
                float(pos) if isinstance(pos, (int, float)) else 1.0,
                int(start_page) if isinstance(start_page, int) else 10**9,
                chunk_id,
            )

        for items in chunks_by_uid.values():
            items.sort(key=_chunk_sort_key)

        enriched_any = False

        for section in sections:
            section_uid = _normalize_uid(section.clause_uid)
            if not section_uid:
                continue

            chunks = chunks_by_uid.get(section_uid)
            if not chunks:
                continue

            parts: list[str] = []
            seen_ids: set[str] = set()
            chunk_indices: list[int] = []
            page_values: list[int] = []

            for ch in chunks:
                chunk_id = str(ch.get("id") or "").strip()
                if chunk_id and chunk_id in seen_ids:
                    continue

                text = (ch.get("text") or "").strip()
                if not text:
                    continue

                parts.append(text)

                if chunk_id:
                    seen_ids.add(chunk_id)

                raw_idx = ch.get("_pipeline_index")
                if isinstance(raw_idx, int):
                    chunk_indices.append(raw_idx)

                meta = ch.get("metadata") or {}
                start_page = meta.get("start_page")
                end_page = meta.get("end_page")

                if isinstance(start_page, int):
                    page_values.append(start_page)
                if isinstance(end_page, int):
                    page_values.append(end_page)

            full_text = "\n\n".join(parts).strip()
            if not full_text:
                continue

            unique_indices = sorted(set(chunk_indices))

            # enriched_text — это "friendly" текст из canonical clause snapshot
            section.enriched_text = full_text

            # Для текущего UI friendly-preview должен показывать enriched_text.
            section.text_preview = full_text

            # source_mapping создаём только если реально есть индексы snapshot'а.
            if unique_indices:
                match_text = full_text[:400]
                section.source_mapping = SectionSourceMappingDTO(
                    source_stage=PipelineStageCode.CHUNKS,
                    page_from=min(page_values) if page_values else section.page_from,
                    page_to=max(page_values) if page_values else section.page_to,
                    chunk_indices=unique_indices,
                    match_text=match_text,
                    match_strategy="chunk_refs",
                )

            enriched_any = True

        return enriched_any


    async def _build_chunks_stage(
        self,
        doc,
        version,
        view_mode: StageViewMode = StageViewMode.canonical,
    ) -> PipelineStageViewDTO:
        artifact_ref = version.chunks_ref
        raw_snapshot: dict[str, Any] | list[Any] | None = None
        chunks: list[ChunkPreviewDTO] = []

        if artifact_ref:
            try:
                snapshot = self.store.get_json(artifact_ref)
                raw_snapshot = snapshot
                chunks = self._extract_chunks_from_snapshot(snapshot)
            except PermanentError:
                return self._with_representation(
                    PipelineStageViewDTO(
                        code=PipelineStageCode.CHUNKS,
                        title="CHUNKS: materialized chunks",
                        description="Snapshot чанков ожидается, но отсутствует в сторедже.",
                        available=False,
                        kind=PipelineStageKind.chunks,
                        status=PipelineStageStatus.missing,
                        artifact_ref=artifact_ref,
                        meta=self._base_meta(doc),
                        preview=None,
                    ),
                    stage_code=PipelineStageCode.CHUNKS,
                    view_mode=view_mode,
                    friendly_supported=False,
                    canonical_description=(
                        "Показывается результат этапа CHUNKS: материализованные чанки документа."
                    ),
                    friendly_description=(
                        "Показывается тот же набор чанков в режиме удобного просмотра. "
                        "Отдельное friendly-представление для CHUNKS пока не реализовано."
                    ),
                )
            except TransientError:
                return self._with_representation(
                    PipelineStageViewDTO(
                        code=PipelineStageCode.CHUNKS,
                        title="CHUNKS: materialized chunks",
                        description="Snapshot чанков временно недоступен.",
                        available=False,
                        kind=PipelineStageKind.chunks,
                        status=PipelineStageStatus.pending,
                        artifact_ref=artifact_ref,
                        meta=self._base_meta(doc),
                        preview=None,
                    ),
                    stage_code=PipelineStageCode.CHUNKS,
                    view_mode=view_mode,
                    friendly_supported=False,
                    canonical_description=(
                        "Показывается результат этапа CHUNKS: материализованные чанки документа."
                    ),
                    friendly_description=(
                        "Показывается тот же набор чанков в режиме удобного просмотра. "
                        "Отдельное friendly-представление для CHUNKS пока не реализовано."
                    ),
                )

        if not chunks:
            fallback_chunks = await self._load_chunks_fallback(doc.id)
            chunks = fallback_chunks

        if not chunks:
            meta = self._base_meta(doc)
            meta.chunk_count = 0
            return self._with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description="Чанки для документа пока недоступны.",
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=artifact_ref,
                    meta=meta,
                    preview=None,
                ),
                stage_code=PipelineStageCode.CHUNKS,
                view_mode=view_mode,
                friendly_supported=False,
                canonical_description=(
                    "Показывается результат этапа CHUNKS: материализованные чанки документа."
                ),
                friendly_description=(
                    "Показывается тот же набор чанков в режиме удобного просмотра. "
                    "Отдельное friendly-представление для CHUNKS пока не реализовано."
                ),
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

        # На данном этапе view_mode не влияет на содержимое CHUNKS,
        # но параметр прокинут для совместимости и будущих расширений.
        logger.info(
            "PIPELINE_VIEW CHUNKS",
            extra={
                "doc_id": str(doc.id),
                "chunks_ref": artifact_ref,
                "chunk_count": len(chunks),
                "view_mode": view_mode.value,
            },
        )

        stage = PipelineStageViewDTO(
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

        return self._with_representation(
            stage,
            stage_code=PipelineStageCode.CHUNKS,
            view_mode=view_mode,
            friendly_supported=False,
            canonical_description=(
                "Показывается результат этапа CHUNKS: материализованные чанки документа."
            ),
            friendly_description=(
                "Показывается тот же набор чанков в режиме удобного просмотра. "
                "Отдельное friendly-представление для CHUNKS пока не реализовано."
            ),
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
            raw = snapshot.get("chunks") or snapshot

            # Форматы:
            # 1) "chunks": [ {...}, {...} ]
            # 2) "chunks": { "section": [...], "clause": [...], "subclause": [...] }
            if isinstance(raw, list):
                items = raw
            elif isinstance(raw, dict):
                items: list[dict[str, Any]] = []
                for lvl_items in raw.values():
                    if isinstance(lvl_items, list):
                        items.extend(lvl_items)
            else:
                return result

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
    

    