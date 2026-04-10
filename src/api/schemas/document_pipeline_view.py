# src/api/schemas/document_pipeline_view.py

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

Дополнительно:
- StageViewMode — режим представления стадии для UI;
- StageProvenanceDTO — информация о происхождении данных в текущем представлении;
- StageRepresentationDTO — пояснение, является ли текущий вид каноническим
  или это более удобное производное представление.
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


class StageViewMode(str, Enum):
    """
    Режим отображения стадии в UI.

    canonical:
        Показывается точный результат этого этапа без дополнительных
        производных представлений.

    friendly:
        Показывается более удобный для чтения вид. Он может использовать
        данные соседних стадий, но при этом должен быть явно помечен как
        производный режим.
    """

    canonical = "canonical"
    friendly = "friendly"


class StageMetaDTO(BaseModel):
    page_count: int | None = None
    element_count: int | None = None
    chunk_count: int | None = None
    section_count: int | None = None
    source_file_name: str | None = None
    mime_type: str | None = None
    text_enriched: bool | None = None


class StageProvenanceDTO(BaseModel):
    """
    Информация о происхождении данных в текущем представлении стадии.

    primary_source_stage:
        Какая стадия является главным источником правды для этого представления.

    derived_from_stages:
        Какие дополнительные стадии были использованы для обогащения
        или построения "удобного вида".

    preview_source_label:
        Короткая человекочитаемая подпись для UI.
        Пример: "Текстовое превью из CHUNKS".
    """

    primary_source_stage: PipelineStageCode | None = None
    derived_from_stages: list[PipelineStageCode] = Field(default_factory=list)
    preview_source_label: str | None = None


class StageRepresentationDTO(BaseModel):
    """
    Описание текущего режима представления стадии.

    view_mode:
        Технический режим представления ("canonical" или "friendly").

    is_canonical:
        Явный флаг для фронта. Нужен, чтобы UI не вычислял это сам.

    label:
        Короткая подпись режима для пользователя.
        Примеры:
        - "Результат этапа"
        - "Удобный вид"

    description:
        Короткое пояснение, что именно показывается на экране.

    provenance:
        Источник данных для текущего представления.
    """

    view_mode: StageViewMode = StageViewMode.canonical
    is_canonical: bool = True
    label: str = "Результат этапа"
    description: str | None = None
    provenance: StageProvenanceDTO = Field(default_factory=StageProvenanceDTO)


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
    # Это стабильный технический идентификатор узла для UI.
    # Он нужен для React keys, выбора секции и другой UI-логики.
    id: str

    # Это доменный идентификатор клаузы документа.
    # Он нужен для связи structure -> canonical chunks -> checks/results.
    clause_uid: str | None = None

    title: str
    level: int = 1
    page_from: int | None = None
    page_to: int | None = None

    # Это текст для показа в STRUCTURE-view.
    # В canonical-режиме это должен быть текст самого stage STRUCTURE
    # (или пустая строка, если stage его не породил).
    # В friendly-режиме это поле может быть обогащено из CHUNKS.
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

    # Объясняет, в каком режиме показана стадия
    # и откуда взялись данные текущего представления.
    representation: StageRepresentationDTO = Field(
        default_factory=StageRepresentationDTO
    )


class DocumentPipelineViewResponseDTO(BaseModel):
    document_id: str
    document_version_id: str
    document_status: str

    # Общий режим, в котором был собран ответ.
    # Это удобно фронту, чтобы инициализировать переключатель.
    view_mode: StageViewMode

    stages: list[PipelineStageViewDTO] = Field(default_factory=list)

    