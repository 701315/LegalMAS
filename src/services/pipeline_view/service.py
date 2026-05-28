# src/services/pipeline_view/service.py

"""
DocumentPipelineViewService — фасад-оркестратор.

Собирает срез пайплайна по одному документу: для текущей версии
подтягивает артефакты из стореджа и БД и упаковывает их в DTO для
frontend-viewer'а.

Вся тяжёлая логика разнесена по stage-билдерам:
- stage_source.py, stage_primary.py, stage_extract.py, stage_pii.py
- stage_structure.py (StructureStageBuilder)
- stage_chunks.py (ChunksStageBuilder)
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.document_pipeline_view import (
    DocumentPipelineViewResponseDTO,
    PipelineStageCode,
    PipelineStageViewDTO,
    StageMetaDTO,
    StageViewMode,
)
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from services.pipeline_view.representation import with_representation
from services.pipeline_view.stage_chunks import ChunksStageBuilder
from services.pipeline_view.stage_extract import build_extract_stage
from services.pipeline_view.stage_pii import build_pii_stage
from services.pipeline_view.stage_primary import build_primary_stage
from services.pipeline_view.stage_source import build_source_stage
from services.pipeline_view.stage_structure import StructureStageBuilder
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


class DocumentPipelineViewService:
    """
    Фасад: собирает стадии пайплайна из отдельных stage-билдеров.

    Сервис ничего не изменяет в пайплайне и не перезапускает стадии —
    он только читает артефакты и возвращает удобное представление для UI.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.ver_repo = DocumentVersionRepository(session)
        self.segment_repo = DocumentSegmentRepository(session)
        self.store = ArtifactStore()

        # Stage builders
        self._structure_builder = StructureStageBuilder(session, self.store)
        self._chunks_builder = ChunksStageBuilder(session, self.store)

    async def build(
        self,
        document_id: UUID,
        view_mode: StageViewMode = StageViewMode.canonical,
    ) -> DocumentPipelineViewResponseDTO:
        """
        Собирает срез пайплайна по документу.

        view_mode управляет отображением стадий для фронта:
        - "canonical" — чистый результат этапа;
        - "friendly" — удобное для чтения представление.
        """
        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise PipelineViewNotFoundError("Document not found")

        version = await self.ver_repo.get_latest(document_id)
        if not version:
            raise PipelineViewNotFoundError("DocumentVersion not found")

        base_meta = self._base_meta(doc)
        segments = await self.segment_repo.list_by_version(version.id)

        # Async stages
        structure_stage = await self._structure_builder.build(
            doc=doc,
            version=version,
            base_meta=base_meta,
            segments=segments,
            view_mode=view_mode,
        )
        chunks_stage = await self._chunks_builder.build(
            doc=doc,
            version=version,
            base_meta=base_meta,
            view_mode=view_mode,
        )

        # Sync stages
        stages: list[PipelineStageViewDTO] = [
            self._with_simple_repr(
                build_source_stage(doc, version, base_meta, self.store),
                PipelineStageCode.SOURCE,
                view_mode,
            ),
            self._with_simple_repr(
                build_primary_stage(doc, version, base_meta, self.store),
                PipelineStageCode.PRIMARY,
                view_mode,
            ),
            self._with_simple_repr(
                build_extract_stage(doc, version, base_meta, self.store),
                PipelineStageCode.EXTRACT,
                view_mode,
            ),
            self._with_simple_repr(
                build_pii_stage(doc, version, base_meta, self.store),
                PipelineStageCode.PII,
                view_mode,
            ),
            structure_stage,
            chunks_stage,
        ]

        return DocumentPipelineViewResponseDTO(
            document_id=str(doc.id),
            document_version_id=str(version.id),
            document_status=doc.status,
            view_mode=view_mode,
            stages=stages,
        )

    @staticmethod
    def _base_meta(doc) -> StageMetaDTO:
        return StageMetaDTO(
            page_count=doc.page_count,
            element_count=None,
            chunk_count=None,
            section_count=None,
            source_file_name=doc.filename,
            mime_type=doc.source_filetype,
        )

    @staticmethod
    def _with_simple_repr(
        stage: PipelineStageViewDTO,
        code: PipelineStageCode,
        view_mode: StageViewMode,
    ) -> PipelineStageViewDTO:
        """Добавляет representation для простых стадий (SOURCE, PRIMARY, EXTRACT, PII)."""
        return with_representation(
            stage,
            stage_code=code,
            view_mode=view_mode,
            friendly_supported=False,
        )


class PipelineViewNotFoundError(Exception):
    """Pipeline view cannot be built because the document or its version does not exist."""

    pass
