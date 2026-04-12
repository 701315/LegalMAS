// =============================================================
// src/api/documentPipelineView.ts
// API для document pipeline view:
// GET /api/v1/documents/{doc_id}/pipeline-view
// =============================================================

import client from "./client";
import type {
  DocumentPipelineViewResponseDTO,
  PipelineStageViewDTO,
  PipelineStageCode,
  StageViewMode,
} from "../types";

export async function getDocumentPipelineView(
  documentId: string,
  signal?: AbortSignal,
  viewMode?: StageViewMode,
): Promise<DocumentPipelineViewResponseDTO> {
  const { data } = await client.get<DocumentPipelineViewResponseDTO>(
    `/api/v1/documents/${documentId}/pipeline-view`,
    {
      signal,
      params: viewMode ? { view_mode: viewMode } : undefined,
    },
  );
  return data;
}

// Новый хелпер: грузит весь pipeline, возвращает только нужную стадию.
// Используется внутри modal при переключении view_mode.
export async function getStageView(
  documentId: string,
  stageCode: PipelineStageCode,
  viewMode: StageViewMode,
  signal?: AbortSignal,
): Promise<PipelineStageViewDTO | null> {
  const data = await getDocumentPipelineView(documentId, signal, viewMode);
  return data.stages.find((s) => s.code === stageCode) ?? null;
}

