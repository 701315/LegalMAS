# src/api/schemas/document_pipeline_view.py

"""
Pydantic DTO-схемы для представления пайплайна обработки документа
в UI (Document Pipeline View).

Используются в API, отдающем пошаговый прогресс документа:
- какие стадии уже выполнены (SOURCE, PRIMARY, EXTRACT, PII, STRUCTURE, CHUNKS);
- статус каждой стадии (ready/missing/pending) и тип артефакта (pdf/layout/structure/chunks);
- метаданные по стадии (количество страниц/элементов/кусков, имя исходного файла, MIME-тип);
- превью артефактов: PDF, layout (страницы с текстом и счётчиками элементов),
  структура (заголовки/разделы) и чанки (фрагменты текста с привязкой к страницам).

Основные модели:
- PipelineStageCode, PipelineStageStatus, PipelineStageKind — enum-коды стадий и их статусов;
- StageMetaDTO — агрегированные метаданные по стадии;
- PdfPreviewDTO / LayoutPreviewDTO / StructurePreviewDTO / ChunksPreviewDTO —
  типизированные превью различных артефактов;
- PipelineStageViewDTO — одна стадия пайплайна с метаданными и превью;
- DocumentPipelineViewResponseDTO — ответ API с состоянием всех стадий для одного документа.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineStageCode(str, Enum):
    SOURCE = "SOURCE"
    PRIMARY = "PRIMARY"
    EXTRACT = "EXTRACT"
    PII = "PII"
    STRUCTURE = "STRUCTURE"
    CHUNKS = "CHUNKS"


class PipelineStageStatus(str, Enum):
    ready = "ready"
    missing = "missing"
    pending = "pending"


class PipelineStageKind(str, Enum):
    pdf = "pdf"
    layout = "layout"
    structure = "structure"
    chunks = "chunks"


class StageMetaDTO(BaseModel):
    page_count: int | None = None
    element_count: int | None = None
    chunk_count: int | None = None
    section_count: int | None = None
    source_file_name: str | None = None
    mime_type: str | None = None


class PdfPreviewDTO(BaseModel):
    type: Literal["pdf"] = "pdf"
    inline_url: str | None = None
    download_url: str | None = None


class LayoutPagePreviewDTO(BaseModel):
    page: int
    text: str
    element_count: int = 0


class LayoutPreviewDTO(BaseModel):
    type: Literal["layout"] = "layout"
    pages: list[LayoutPagePreviewDTO] = Field(default_factory=list)
    raw_json: dict[str, Any] | list[Any] | None = None


class StructureSectionPreviewDTO(BaseModel):
    id: str
    title: str
    level: int = 1
    page_from: int | None = None
    page_to: int | None = None
    text_preview: str = ""


class StructurePreviewDTO(BaseModel):
    type: Literal["structure"] = "structure"
    sections: list[StructureSectionPreviewDTO] = Field(default_factory=list)
    raw_json: dict[str, Any] | list[Any] | None = None


class ChunkPreviewDTO(BaseModel):
    index: int
    clause_uid: str = ""
    page_from: int | None = None
    page_to: int | None = None
    text: str


class ChunksPreviewDTO(BaseModel):
    type: Literal["chunks"] = "chunks"
    chunks: list[ChunkPreviewDTO] = Field(default_factory=list)
    reconstructed_text: str = ""
    raw_json: dict[str, Any] | list[Any] | None = None


PipelinePreviewDTO = (
    PdfPreviewDTO
    | LayoutPreviewDTO
    | StructurePreviewDTO
    | ChunksPreviewDTO
)


class PipelineStageViewDTO(BaseModel):
    code: PipelineStageCode
    title: str
    description: str
    available: bool
    kind: PipelineStageKind
    status: PipelineStageStatus
    artifact_ref: str | None = None
    meta: StageMetaDTO = Field(default_factory=StageMetaDTO)
    preview: PipelinePreviewDTO | None = None


class DocumentPipelineViewResponseDTO(BaseModel):
    document_id: str
    document_version_id: str
    document_status: str
    stages: list[PipelineStageViewDTO] = Field(default_factory=list)