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
  primary_source_stage?: PipelineStageCode | null;

  // Дополнительные стадии, использованные для derived/friendly view.
  derived_from_stages: PipelineStageCode[];

  // Короткая подпись для UI.
  preview_source_label?: string | null;
}

export interface StageRepresentationDTO {
  // Технический режим, в котором backend собрал текущую стадию.
  view_mode: StageViewMode;

  // Удобный флаг для UI, чтобы не вычислять вручную.
  is_canonical: boolean;

  // Короткая подпись режима.
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

/* ============================================================
 * SEGMENTS / REFS
 * ============================================================ */

export interface PipelineSegmentDTO {
  segment_id: string;
  segment_type: string;
  segment_title?: string | null;
  segment_order: number;
  is_primary: boolean;
  page_from?: number | null;
  page_to?: number | null;
}

export interface ChunkRefDTO {
  segment_id: string;
  chunk_index?: number | null;
  chunk_id?: string | null;
}

/**
 * Привязка секции STRUCTURE к исходному текстовому слою документа.
 * Используется для source-pane справа:
 * - какие чанки соответствуют секции;
 * - по каким страницам искать;
 * - какую цитату можно подсветить.
 */
export type SectionSourceMatchStrategy =
  | "chunk_refs"
  | "text_quote"
  | "page_window";

export interface SectionSourceMappingDTO {
  source_stage: PipelineStageCode;
  page_from?: number | null;
  page_to?: number | null;

  // legacy
  chunk_indices: number[];

  // v2 canonical
  chunk_refs: ChunkRefDTO[];
  segment_id?: string | null;

  match_text?: string | null;
  match_strategy: SectionSourceMatchStrategy;
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

  // v2 segment provenance
  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

  // Канонический текст секции из STRUCTURE / clause tree.
  structure_text?: string | null;

  // Обогащённый текст секции.
  enriched_text?: string | null;

  // UI-совместимое поле для показа текста секции.
  text_preview?: string | null;

  // Связь секции с исходным текстовым слоем.
  source_mapping?: SectionSourceMappingDTO | null;
}

export interface StructureSegmentPreviewDTO {
  segment: PipelineSegmentDTO;
  sections: StructureSectionPreviewDTO[];
  raw_json?: JsonValue | null;
}

export interface StructurePreviewDTO {
  type: "structure";

  // legacy flattened view
  sections: StructureSectionPreviewDTO[];

  // v2 canonical view
  segments: StructureSegmentPreviewDTO[];

  raw_json?: JsonValue | null;
}

export interface ChunkPreviewDTO {
  index: number;
  clause_uid: string;
  page_from: number | null;
  page_to: number | null;
  text: string;

  // v2 segment provenance
  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

  // optional stable ids/provenance
  chunk_id?: string | null;
}

export interface ChunksSegmentPreviewDTO {
  segment: PipelineSegmentDTO;
  chunks: ChunkPreviewDTO[];
  reconstructed_text: string;
  raw_json?: JsonValue | null;
}

export interface ChunksPreviewDTO {
  type: "chunks";

  // legacy flattened view
  chunks: ChunkPreviewDTO[];

  // v2 canonical view
  segments: ChunksSegmentPreviewDTO[];

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


