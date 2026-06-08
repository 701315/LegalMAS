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
  text_enriched?: boolean | null;
}

export interface StageProvenanceDTO {
  primary_source_stage?: PipelineStageCode | null;
  derived_from_stages: PipelineStageCode[];
  preview_source_label?: string | null;
}

export interface StageRepresentationDTO {
  view_mode: StageViewMode;
  is_canonical: boolean;
  label: string;
  description?: string | null;
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

export type SectionSourceMatchStrategy =
  | "chunk_refs"
  | "text_quote"
  | "page_window";

export interface SectionSourceMappingDTO {
  source_stage: PipelineStageCode;
  page_from?: number | null;
  page_to?: number | null;
  chunk_indices: number[];
  chunk_refs: ChunkRefDTO[];
  segment_id?: string | null;
  match_text?: string | null;
  match_strategy: SectionSourceMatchStrategy;
}

export interface StructureSectionPreviewDTO {
  id: string;
  clause_uid?: string | null;
  title: string;
  level: number;
  page_from?: number | null;
  page_to?: number | null;
  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;
  structure_text?: string | null;
  enriched_text?: string | null;
  text_preview?: string | null;
  source_mapping?: SectionSourceMappingDTO | null;
}

export interface StructureSegmentPreviewDTO {
  segment: PipelineSegmentDTO;
  sections: StructureSectionPreviewDTO[];
  raw_json?: JsonValue | null;
}

export interface StructurePreviewDTO {
  type: "structure";
  sections: StructureSectionPreviewDTO[];
  segments: StructureSegmentPreviewDTO[];
  raw_json?: JsonValue | null;
}

/* ============================================================
 * CHUNKS
 * ============================================================ */

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

  // ── честная идентичность чанка ──────────────────────────────
  //
  // chunk_kind: реальный уровень чанка из backend truth.
  //   "section"   — крупный раздел документа
  //   "clause"    — пункт / статья
  //   "subclause" — подпункт (это то, что реально видит RAG)
  //   Если null — старый artifact без этого поля.
  chunk_kind?: "section" | "clause" | "subclause" | string | null;

  // effective_uid: canonical identity чанка в retrieval pipeline.
  //   Именно этот uid используется в retrieval/checks при анализе рисков.
  //   clause_uid может быть display/raw uid и не совпадать с effective_uid.
  effective_uid?: string | null;

  // retrieval_safe: флаг доступности в retrieval pipeline.
  //   true  — чанк активно используется в RAG/checks
  //   false — чанк существует в artifact, но отфильтрован (unsafe)
  //   null  — информация недоступна
  retrieval_safe?: boolean | null;

  // backend-driven presentation
  display_title?: string | null;
  display_subtitle?: string | null;
  role?: "evidence" | "context" | string | null;
}

export interface ChunksSegmentPreviewDTO {
  segment: PipelineSegmentDTO;
  chunks: ChunkPreviewDTO[];
  reconstructed_text: string;
  raw_json?: JsonValue | null;
}

export interface ChunksPreviewDTO {
  type: "chunks";
  chunks: ChunkPreviewDTO[];
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
  representation: StageRepresentationDTO;
}

export interface DocumentPipelineViewResponseDTO {
  document_id: string;
  document_version_id?: string | null;
  document_status: DocumentStatus | string;
  view_mode: StageViewMode;
  stages: PipelineStageViewDTO[];
}

