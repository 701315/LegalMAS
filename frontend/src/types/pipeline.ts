// =============================================================
// src/types/pipeline.ts
// Типы для document pipeline view.
// =============================================================

import type { JsonValue } from "./common";
import type { DocumentStatus } from "./documents";

export type PipelineStageCode =
  | "SOURCE"
  | "PRIMARY"
  | "EXTRACT"
  | "PII"
  | "STRUCTURE"
  | "CHUNKS";

export type PipelineStageStatus = "ready" | "missing" | "pending";

export type PipelineStageKind = "pdf" | "layout" | "structure" | "chunks";

export type StageViewMode = "canonical" | "friendly";

export interface StageMetaDTO {
  page_count?: number | null;
  element_count?: number | null;
  chunk_count?: number | null;
  section_count?: number | null;
  source_file_name?: string | null;
  mime_type?: string | null;

  // Для STRUCTURE friendly-view backend может явно показывать,
  // было ли выполнено обогащение текста из CHUNKS.
  text_enriched?: boolean | null;
}

export interface StageProvenanceDTO {
  // Основной источник правды для текущего представления.
  // Например, для STRUCTURE friendly это всё ещё "STRUCTURE",
  // а CHUNKS может быть указан в derived_from_stages.
  primary_source_stage?: PipelineStageCode | null;

  // Дополнительные стадии, использованные для derived/friendly view.
  derived_from_stages: PipelineStageCode[];

  // Короткая подпись для UI.
  // Пример: "Текстовое превью из CHUNKS".
  preview_source_label?: string | null;
}

export interface StageRepresentationDTO {
  // Технический режим, в котором backend собрал текущую стадию.
  view_mode: StageViewMode;

  // Удобный флаг для UI, чтобы не вычислять вручную.
  is_canonical: boolean;

  // Короткая подпись режима.
  // Примеры: "Результат этапа", "Удобный вид".
  label: string;

  // Человеко-понятное описание текущего представления.
  description?: string | null;

  // Информация о происхождении данных в этом представлении.
  provenance: StageProvenanceDTO;
}

export interface PdfPreviewDTO {
  type: "pdf";
  inline_url?: string | null;
  download_url?: string | null;
}

export interface LayoutPagePreviewDTO {
  page: number;
  text: string;
  element_count: number;
}

export interface LayoutPreviewDTO {
  type: "layout";
  pages: LayoutPagePreviewDTO[];
  raw_json?: JsonValue | null;
}

export interface StructureSectionPreviewDTO {
  id: string;

  // Доменный идентификатор клаузы.
  // Нужен для связи structure -> chunks -> checks.
  clause_uid?: string | null;

  title: string;
  level: number;
  page_from?: number | null;
  page_to?: number | null;

  // Текст для показа в STRUCTURE-view.
  // В canonical это текст stage STRUCTURE.
  // В friendly может быть обогащён из CHUNKS.
  text_preview?: string | null;
}

export interface StructurePreviewDTO {
  type: "structure";
  sections: StructureSectionPreviewDTO[];
  raw_json?: JsonValue | null;
}

export interface ChunkPreviewDTO {
  index: number;
  clause_uid?: string | null;
  page_from?: number | null;
  page_to?: number | null;
  text: string;
}

export interface ChunksPreviewDTO {
  type: "chunks";
  chunks: ChunkPreviewDTO[];
  reconstructed_text?: string | null;
  raw_json?: JsonValue | null;
}

export type PipelineStagePreview =
  | PdfPreviewDTO
  | LayoutPreviewDTO
  | StructurePreviewDTO
  | ChunksPreviewDTO
  | null;

export interface PipelineStageViewDTO {
  code: PipelineStageCode;
  title: string;
  description: string;
  available: boolean;
  kind: PipelineStageKind;
  status: PipelineStageStatus;
  artifact_ref?: string | null;
  meta?: StageMetaDTO | null;
  preview?: PipelineStagePreview;

  // Новое поле backend: объясняет,
  // в каком режиме показана стадия и откуда взялись данные.
  representation: StageRepresentationDTO;
}

export interface DocumentPipelineViewResponseDTO {
  document_id: string;
  document_version_id?: string | null;
  document_status: DocumentStatus | string;

  // Общий режим, в котором backend собрал весь ответ.
  view_mode: StageViewMode;

  stages: PipelineStageViewDTO[];
}

