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

export interface StageMetaDTO {
  page_count?: number | null;
  element_count?: number | null;
  chunk_count?: number | null;
  section_count?: number | null;
  source_file_name?: string | null;
  mime_type?: string | null;
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
  title: string;
  level: number;
  page_from?: number | null;
  page_to?: number | null;
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
}

export interface DocumentPipelineViewResponseDTO {
  document_id: string;
  document_version_id?: string | null;
  document_status: DocumentStatus | string;
  stages: PipelineStageViewDTO[];
}

