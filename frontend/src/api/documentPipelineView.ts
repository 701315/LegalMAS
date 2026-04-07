// =============================================================
// src/api/documentPipelineView.ts
// API для document pipeline view:
// GET /api/v1/documents/{doc_id}/pipeline-view
// =============================================================

import client from "./client";
import type { DocumentPipelineViewResponseDTO } from "../types";

export async function getDocumentPipelineView(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentPipelineViewResponseDTO> {
  const { data } = await client.get<DocumentPipelineViewResponseDTO>(
    `/api/v1/documents/${documentId}/pipeline-view`,
    { signal },
  );
  return data;
}